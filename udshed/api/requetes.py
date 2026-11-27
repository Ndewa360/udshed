"""Requêtes et réclamations des étudiants (DocType « Requete Etudiant »).

Étudiant (espace étudiant) : mes_requetes(), soumettre(...).
Scolarité : repondre(requete, reponse, statut), note_concernee(requete)
— une réclamation de note se traite par une « Correction Note » motivée
(udshed/utils/correction_note.py), liée à la requête.
"""

import frappe

from udshed.utils.etablissement import nom_etudiant
from frappe import _
from frappe.utils import now_datetime

ROLES_TRAITEMENT = {"System Manager", "Registration Manager", "Agent de scolarité", "Coordonateur",
					"Responsable Diplomation"}
STATUTS_FINAUX = ("Répondue", "Rejetée", "Clôturée")


def _mon_etudiant():
	from udshed.api.etudiant import _mon_etudiant as moi

	return moi()


def _types():
	return (frappe.get_meta("Requete Etudiant").get_field("type_requete").options or "").split("\n")


@frappe.whitelist()
def mes_requetes():
	s = _mon_etudiant()
	requetes = frappe.get_all("Requete Etudiant", filters={"student": s.name},
							  fields=["name", "type_requete", "objet", "statut", "reponse", "creation"],
							  order_by="creation desc")
	matieres = []
	for r in frappe.get_all("Resultat Academique", filters={"student": s.name},
							fields=["teaching_unit", "ue_name", "academic_year"], order_by="academic_year desc"):
		matieres.append({"value": r.teaching_unit, "label": f"{r.ue_name or r.teaching_unit} ({r.academic_year})"})
	return {"requetes": requetes, "types": _types(), "matieres": matieres}


@frappe.whitelist()
def soumettre(type_requete, objet, description, matiere=None, piece_jointe=None):
	s = _mon_etudiant()
	if type_requete not in _types():
		frappe.throw(_("Type de requête inconnu."))
	if type_requete == "Réclamation de note" and not matiere:
		frappe.throw(_("Indiquez la matière concernée par la réclamation."))
	annee = frappe.db.get_value("Teaching Unit", matiere, "academic_year") if matiere else None
	doc = frappe.get_doc({
		"doctype": "Requete Etudiant", "student": s.name, "type_requete": type_requete, "objet": objet,
		"description": description, "teaching_unit": matiere or None, "academic_year": annee,
		"piece_jointe": piece_jointe or None, "statut": "Soumise",
	})
	doc.insert(ignore_permissions=True)
	_notifier_traitants(doc)
	return {"name": doc.name}


def _exiger_traitement():
	if not (set(frappe.get_roles()) & ROLES_TRAITEMENT):
		frappe.throw(_("Action réservée à la scolarité."), frappe.PermissionError)


@frappe.whitelist()
def prendre_en_charge(requete):
	_exiger_traitement()
	doc = frappe.get_doc("Requete Etudiant", requete)
	from udshed.utils import perimetre

	perimetre.exiger_etudiant(doc.student)
	if doc.statut == "Soumise":
		doc.db_set({"statut": "En traitement", "traite_par": frappe.session.user})
	return {"statut": doc.statut}


@frappe.whitelist()
def repondre(requete, reponse, statut="Répondue"):
	_exiger_traitement()
	if statut not in STATUTS_FINAUX:
		frappe.throw(_("Statut de réponse invalide."))
	if not (reponse or "").strip():
		frappe.throw(_("Rédigez la réponse à l'étudiant."))
	doc = frappe.get_doc("Requete Etudiant", requete)
	from udshed.utils import perimetre

	perimetre.exiger_etudiant(doc.student)
	doc.db_set({"reponse": reponse, "statut": statut, "traite_par": frappe.session.user, "traite_le": now_datetime()})
	user = frappe.db.get_value("Student", doc.student, "utilisateur")
	from udshed.utils.compte_etudiant import notifier_etudiant

	notifier_etudiant(user, _("Réponse à votre requête « {0} » : {1}").format(doc.objet, statut), reponse)
	return {"statut": statut}


@frappe.whitelist()
def note_concernee(requete):
	"""Note (Session Examen Note) visée par une réclamation : la scolarité y
	lance « Demander une correction » ; la correction est rattachée à la requête."""
	_exiger_traitement()
	doc = frappe.get_doc("Requete Etudiant", requete)
	if not doc.teaching_unit:
		frappe.throw(_("Aucune matière n'est indiquée sur cette requête."))
	note = frappe.db.get_value("Session Examen Note", {"student": doc.student, "teaching_unit": doc.teaching_unit},
							   "name", order_by="modified desc")
	if not note:
		frappe.throw(_("Aucune note trouvée pour cet étudiant dans cette matière."))
	if doc.statut == "Soumise":
		doc.db_set({"statut": "En traitement", "traite_par": frappe.session.user})
	return note


def lier_correction(correction):
	"""Rattache une correction appliquée à la réclamation ouverte correspondante."""
	req = frappe.db.get_value("Requete Etudiant", {
		"student": correction.student, "teaching_unit": correction.teaching_unit,
		"type_requete": "Réclamation de note", "statut": ["in", ["Soumise", "En traitement"]],
	}, "name")
	if req:
		frappe.db.set_value("Requete Etudiant", req, "correction_note", correction.name)
	return req


def _notifier_traitants(doc):
	from udshed.utils import perimetre

	# Agents de scolarité de la filière de l'étudiant (et scolarité centrale).
	users = set(perimetre.destinataires(("Agent de scolarité", "Registration Manager"),
										 perimetre.filiere_etudiant(doc.student)))
	nom = nom_etudiant(doc.student)
	for user in users:
		if user in ("Administrator", "Guest") or not frappe.db.get_value("User", user, "enabled"):
			continue
		frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert",
						"subject": _("Nouvelle requête ({0}) : {1} — {2}").format(doc.type_requete, nom, doc.objet),
						"document_type": "Requete Etudiant", "document_name": doc.name}).insert(ignore_permissions=True)
