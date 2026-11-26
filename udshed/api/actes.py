"""Actes académiques : demandes, délivrance, téléchargement, vérification.

Étudiant (espace étudiant) :
  mes_documents()          modèles actifs, disponibilité, actes déjà obtenus
  obtenir(modele, motif)   libre-service → disponible tout de suite ;
						   sinon → demande à traiter par un responsable
  telecharger(acte)        PDF de SON acte (disponible / prêt à retirer)
Responsables (Responsable Diplomation, scolarité) :
  delivrer(acte)           signature électronique → disponible ;
						   signature manuscrite → prêt à retirer (imprimer, signer)
  refuser(acte, motif) / marquer_retire(acte)
Public :
  verifier(code)           authenticité d'un acte (QR code)
Éditeur :
  apercu_modele / enregistrer_layout / variables_modele
"""

import json
import secrets

import frappe

from udshed.utils.etablissement import nom_etudiant
from frappe import _
from frappe.utils import now_datetime

from udshed.utils import actes as moteur

ROLES_ACTES = {"System Manager", "Responsable Diplomation", "Registration Manager", "Agent de scolarité"}
ROLES_MODELES = {"System Manager", "Responsable Diplomation"}


def _exiger(roles):
	if not (set(frappe.get_roles()) & roles):
		frappe.throw(_("Action réservée aux responsables des actes académiques."), frappe.PermissionError)


def _mon_etudiant():
	from udshed.api.etudiant import _mon_etudiant as moi

	return moi()


def _repondre_pdf(contenu, nom):
	frappe.response["filename"] = nom
	frappe.response["filecontent"] = contenu
	frappe.response["type"] = "download"
	frappe.response["content_type"] = "application/pdf"


def _nouveau_code():
	while True:
		code = secrets.token_hex(6).upper()
		if not frappe.db.exists("Acte Academique", {"code_verification": code}):
			return code


def _figer(acte):
	"""Fige les données imprimées (nom, filière, niveau…) au moment de la délivrance."""
	modele = frappe.get_doc("Modele Acte", acte.modele)
	ctx = moteur.contexte(acte.student, modele, acte)
	donnees = {k: dict(v) if isinstance(v, dict) else v for k, v in ctx.items()}
	return json.dumps(donnees, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------- #
#  Étudiant
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def mes_documents():
	s = _mon_etudiant()
	modeles = frappe.get_all("Modele Acte", filters={"actif": 1},
							 fields=["name", "titre", "type_acte", "libre_service", "mode_signature", "condition"],
							 order_by="libre_service desc, titre asc")
	res = []
	for m in modeles:
		possible, message = moteur.verifier_condition(frappe.get_cached_doc("Modele Acte", m.name), s.name)
		actes = frappe.get_all("Acte Academique", filters={"student": s.name, "modele": m.name},
							   fields=["name", "statut", "creation", "motif_refus", "academic_year"],
							   order_by="creation desc", limit=5)
		res.append({**m, "possible": possible, "message": message, "actes": actes})
	return res


@frappe.whitelist()
def obtenir(modele, motif=None):
	s = _mon_etudiant()
	m = frappe.get_doc("Modele Acte", modele)
	if not m.actif:
		frappe.throw(_("Ce document n'est plus délivré."))
	possible, message = moteur.verifier_condition(m, s.name)
	if not possible:
		frappe.throw(message)
	annee = frappe.db.get_single_value("Udshed Setting", "current_year")
	if not m.libre_service:
		en_cours = frappe.db.get_value("Acte Academique", {"student": s.name, "modele": m.name,
														   "statut": ["in", ["Demandé", "Prêt à retirer"]]}, "name")
		if en_cours:
			frappe.throw(_("Une demande est déjà en cours pour ce document ({0}).").format(en_cours))
	acte = frappe.get_doc({
		"doctype": "Acte Academique", "student": s.name, "modele": m.name, "academic_year": annee,
		"motif_demande": motif, "demande_par": frappe.session.user, "demande_le": now_datetime(),
		"code_verification": _nouveau_code(),
		"statut": "Disponible" if m.libre_service else "Demandé",
		"signe_electroniquement": 1 if (m.libre_service and m.mode_signature == "Électronique") else 0,
	})
	acte.insert(ignore_permissions=True)
	if m.libre_service:
		acte.db_set({"traite_le": now_datetime(), "donnees": _figer(acte)})
	else:
		_notifier_responsables(acte)
	return {"name": acte.name, "statut": acte.statut}


@frappe.whitelist()
def telecharger(acte):
	doc = frappe.get_doc("Acte Academique", acte)
	staff = bool(set(frappe.get_roles()) & ROLES_ACTES)
	if not staff:
		if doc.student != _mon_etudiant().name:
			frappe.throw(_("Ce document ne vous appartient pas."), frappe.PermissionError)
		if doc.statut != "Disponible":
			frappe.throw(_("Ce document n'est pas encore disponible (statut : {0}).").format(doc.statut))
	modele = frappe.get_doc("Modele Acte", doc.modele)
	_repondre_pdf(moteur.pdf(modele, doc.student, doc), f"{doc.type_acte}-{doc.name}.pdf".replace(" ", "_"))


# ---------------------------------------------------------------------- #
#  Responsables
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def delivrer(acte):
	_exiger(ROLES_ACTES)
	doc = frappe.get_doc("Acte Academique", acte)
	if doc.statut != "Demandé":
		frappe.throw(_("Seule une demande peut être délivrée (statut : {0}).").format(doc.statut))
	modele = frappe.get_doc("Modele Acte", doc.modele)
	possible, message = moteur.verifier_condition(modele, doc.student)
	if not possible:
		frappe.throw(_("Condition non remplie : {0}").format(message))
	electronique = modele.mode_signature == "Électronique"
	doc.db_set({"statut": "Disponible" if electronique else "Prêt à retirer",
				"signe_electroniquement": 1 if electronique else 0,
				"traite_par": frappe.session.user, "traite_le": now_datetime()})
	doc.reload()
	doc.db_set("donnees", _figer(doc))
	_notifier_etudiant(doc, _("Votre document « {0} » est disponible au téléchargement.").format(doc.type_acte)
					   if electronique else
					   _("Votre document « {0} » est signé : vous pouvez le retirer à la scolarité.").format(doc.type_acte))
	return {"statut": doc.statut}


@frappe.whitelist()
def refuser(acte, motif):
	_exiger(ROLES_ACTES)
	if not (motif or "").strip():
		frappe.throw(_("Indiquez le motif du refus."))
	doc = frappe.get_doc("Acte Academique", acte)
	if doc.statut != "Demandé":
		frappe.throw(_("Seule une demande peut être refusée."))
	doc.db_set({"statut": "Refusé", "motif_refus": motif, "traite_par": frappe.session.user, "traite_le": now_datetime()})
	_notifier_etudiant(doc, _("Votre demande de « {0} » a été refusée : {1}").format(doc.type_acte, motif))


@frappe.whitelist()
def marquer_retire(acte):
	_exiger(ROLES_ACTES)
	doc = frappe.get_doc("Acte Academique", acte)
	if doc.statut != "Prêt à retirer":
		frappe.throw(_("Le document n'est pas prêt à être retiré."))
	doc.db_set("statut", "Retiré")
	doc.add_comment("Comment", _("Document original remis à l'étudiant."))


def _notifier_etudiant(acte, message):
	user = frappe.db.get_value("Student", acte.student, "utilisateur")
	from udshed.utils.compte_etudiant import notifier_etudiant

	notifier_etudiant(user, message)


def _notifier_responsables(acte):
	users = set()
	for role in ("Responsable Diplomation", "Agent de scolarité"):
		users.update(frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent"))
	nom = nom_etudiant(acte.student)
	for user in users:
		if user in ("Administrator", "Guest") or not frappe.db.get_value("User", user, "enabled"):
			continue
		frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert",
						"subject": _("Demande de {0} : {1}").format(acte.type_acte, nom),
						"document_type": "Acte Academique", "document_name": acte.name}).insert(ignore_permissions=True)


# ---------------------------------------------------------------------- #
#  Vérification publique
# ---------------------------------------------------------------------- #
@frappe.whitelist(allow_guest=True)
def verifier(code=None):
	"""Authenticité d'un acte : informations minimales, aucune donnée sensible."""
	from udshed.utils import securite

	code = (code or "").strip().upper()
	ip = securite.ip_client()
	securite.verifier_tentatives("verifier-acte", ip, 60, 15 * 60)
	acte = frappe.db.get_value("Acte Academique", {"code_verification": code},
							   ["name", "student", "type_acte", "statut", "traite_le", "academic_year", "donnees"],
							   as_dict=True) if code else None
	if not acte or acte.statut not in ("Disponible", "Prêt à retirer", "Retiré"):
		securite.enregistrer_echec("verifier-acte", ip, 15 * 60)
		return {"valide": False}
	donnees = json.loads(acte.donnees or "{}")
	etudiant = donnees.get("etudiant") or {}
	return {
		"valide": True, "numero": acte.name, "type": acte.type_acte,
		"etudiant": etudiant.get("nom_complet"), "matricule": etudiant.get("matricule"),
		"formation": " ".join(x for x in [etudiant.get("niveau"), etudiant.get("filiere")] if x),
		"date": frappe.utils.format_date(acte.traite_le) if acte.traite_le else "",
		"annee": acte.academic_year or "",
		"etablissement": (donnees.get("etablissement") or {}).get("nom"),
	}


# ---------------------------------------------------------------------- #
#  Éditeur de modèles
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def variables_modele():
	_exiger(ROLES_MODELES)
	return [{"cle": c, "libelle": l} for c, l in moteur.catalogue_variables()]


@frappe.whitelist()
def enregistrer_layout(modele, layout):
	_exiger(ROLES_MODELES)
	data = json.loads(layout) if isinstance(layout, str) else layout
	if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
		frappe.throw(_("Disposition invalide."))
	frappe.db.set_value("Modele Acte", modele, "layout", json.dumps(data, ensure_ascii=False))
	frappe.get_doc("Modele Acte", modele).add_comment("Info", _("Disposition modifiée avec l'éditeur."))
	return {"ok": True}


@frappe.whitelist()
def apercu_modele(modele, student=None, layout=None):
	"""PDF d'aperçu (données d'un étudiant réel ou du premier étudiant trouvé)."""
	_exiger(ROLES_MODELES | {"Registration Manager", "Agent de scolarité"})
	m = frappe.get_doc("Modele Acte", modele)
	if layout:
		m.layout = layout
	student = student or frappe.db.get_value("Student", {}, "name", order_by="creation desc")
	if not student:
		frappe.throw(_("Aucun étudiant pour l'aperçu."))
	_repondre_pdf(moteur.pdf(m, student, None, signer=True), f"apercu-{m.name}.pdf".replace(" ", "_"))
