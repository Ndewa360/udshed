# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Frais de scolarité : barème, échéances, paiements et blocages administratifs.

- Le barème (« Frais Scolarite ») fixe, par année, filière et niveau, des tranches
  avec leur échéance. À l'inscription et à la réinscription, les échéances de
  l'étudiant (« Echeance Etudiant ») sont créées automatiquement.
- Chaque paiement (« Paiement Etudiant ») met à jour son échéance ; l'étudiant
  reçoit une confirmation.
- Une échéance passée non soldée devient « En retard ». Si le blocage est activé
  dans les réglages, elle bloque les actes, les relevés et la réinscription,
  sauf décision du comptable (« Ne pas bloquer l'étudiant ») ou exonération.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from udshed.notifications import emettre

ROLES_FINANCES = ("System Manager", "Comptable", "Registration Manager")


# ---------------------------------------------------------------------- #
#  Échéances
# ---------------------------------------------------------------------- #
def _paye(echeance, sauf=None):
	filtres = {"echeance": echeance}
	if sauf:
		filtres["name"] = ["!=", sauf]
	return flt(sum(frappe.get_all("Paiement Etudiant", filters=filtres, pluck="montant")))


def calculer_echeance(doc, sauf=None):
	if not doc.filiere and doc.student:
		doc.filiere = frappe.db.get_value("Student", doc.student, "filiere")
	doc.montant_paye = _paye(doc.name, sauf) if not doc.is_new() else flt(doc.montant_paye)
	doc.reste = max(flt(doc.montant) - flt(doc.montant_paye), 0)
	if cint(doc.exoneree):
		doc.statut = "Exonérée"
	elif doc.reste <= 0:
		doc.statut = "Payée"
	elif getdate(doc.date_echeance) < getdate(nowdate()):
		doc.statut = "En retard"
	else:
		doc.statut = "À payer"


def recalculer(echeance, sauf=None):
	doc = frappe.get_doc("Echeance Etudiant", echeance)
	calculer_echeance(doc, sauf)
	doc.save(ignore_permissions=True)
	return doc


def mettre_a_jour_retards(jour=None):
	jour = getdate(jour or nowdate())
	noms = frappe.get_all("Echeance Etudiant", filters={"statut": "À payer", "date_echeance": ["<", jour]}, pluck="name")
	for nom in noms:
		frappe.db.set_value("Echeance Etudiant", nom, "statut", "En retard")
	return len(noms)


def generer_echeances(student, academic_year, filiere=None, niveau=None):
	"""Crée les échéances du barème qui s'appliquent à l'étudiant (sans doublon)."""
	creees = []
	if not (student and academic_year):
		return creees
	for f in frappe.get_all("Frais Scolarite", filters={"academic_year": academic_year, "actif": 1},
							fields=["name", "libelle", "montant", "date_echeance", "filiere", "niveau"]):
		if f.filiere and f.filiere != filiere:
			continue
		if f.niveau and (f.niveau or "").strip().lower() != (niveau or "").strip().lower():
			continue
		if frappe.db.exists("Echeance Etudiant", {"student": student, "frais": f.name}):
			continue
		doc = frappe.get_doc({"doctype": "Echeance Etudiant", "student": student, "academic_year": academic_year,
							  "frais": f.name, "libelle": f.libelle, "montant": f.montant,
							  "date_echeance": f.date_echeance, "filiere": filiere})
		doc.insert(ignore_permissions=True)
		creees.append(doc.name)
	return creees


def apres_inscription(doc, method=None):
	"""Inscription Academique créée : échéances de l'année."""
	try:
		student = frappe.db.get_value("Student", {"matricule": doc.matricule}, "name") if doc.matricule else None
		generer_echeances(student, doc.annee_academique, doc.filiere, doc.classe)
	except Exception:
		frappe.log_error(title="udshed: échéances à l'inscription")


def apres_reinscription(doc, method=None):
	try:
		generer_echeances(doc.student, doc.academic_year, doc.filiere, doc.niveau)
	except Exception:
		frappe.log_error(title="udshed: échéances à la réinscription")


# ---------------------------------------------------------------------- #
#  Paiements
# ---------------------------------------------------------------------- #
def valider_paiement(doc):
	if flt(doc.montant) <= 0:
		frappe.throw(_("Le montant doit être positif."))
	e = frappe.db.get_value("Echeance Etudiant", doc.echeance, ["student", "montant", "name"], as_dict=True)
	if not e:
		frappe.throw(_("Échéance introuvable."))
	if e.student != doc.student:
		frappe.throw(_("Cette échéance n'appartient pas à cet étudiant."))
	reste = flt(e.montant) - _paye(e.name, sauf=None if doc.is_new() else doc.name)
	if flt(doc.montant) - reste > 0.005:
		frappe.throw(_("Le montant dépasse le reste à payer ({0}).").format(
			frappe.format(reste, {"fieldtype": "Currency"})))
	if doc.is_new():
		doc.enregistre_par = frappe.session.user


def apres_paiement(doc):
	e = recalculer(doc.echeance)
	s = frappe.db.get_value("Student", doc.student, ["utilisateur", "email", "phone"], as_dict=True) or {}
	emettre("paiement_recu", [{"user": s.get("utilisateur"), "email": s.get("email"), "phone": s.get("phone")}],
			_("Paiement enregistré : {0}").format(frappe.format(doc.montant, {"fieldtype": "Currency"})),
			_("{0} — reste à payer : {1}.").format(e.libelle, frappe.format(e.reste, {"fieldtype": "Currency"})),
			lien="/app/mon-espace-etudiant", reference=("Paiement Etudiant", doc.name), cle=doc.name)


# ---------------------------------------------------------------------- #
#  Blocages
# ---------------------------------------------------------------------- #
def blocage_actif():
	return cint(frappe.db.get_single_value("Udshed Setting", "activer_blocage_frais"))


def blocages(student):
	if not (student and blocage_actif()):
		return []
	return frappe.get_all("Echeance Etudiant", filters={"student": student, "statut": "En retard", "blocage_leve": 0,
														"exoneree": 0},
						  fields=["name", "libelle", "reste", "date_echeance"], order_by="date_echeance asc")


def exiger_aucun_blocage(student, action):
	"""Refuse `action` à un étudiant en retard de paiement (le personnel n'est pas concerné)."""
	if not student or set(frappe.get_roles()) & set(ROLES_FINANCES + ("Agent de scolarité", "Responsable Diplomation")):
		return
	lignes = blocages(student)
	if lignes:
		detail = ", ".join(f"{l.libelle} ({frappe.format(l.reste, {'fieldtype': 'Currency'})})" for l in lignes)
		frappe.throw(_("{0} est suspendu(e) : frais de scolarité en retard — {1}. Régularisez votre situation "
					   "auprès du service financier.").format(action, detail), title=_("Situation financière"))


# ---------------------------------------------------------------------- #
#  API
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def mes_frais():
	"""Situation financière de l'étudiant connecté."""
	student = frappe.db.get_value("Student", {"utilisateur": frappe.session.user}, "name")
	if not student:
		frappe.throw(_("Réservé aux étudiants."), frappe.PermissionError)
	return situation(student)


@frappe.whitelist()
def situation_etudiant(student):
	if not set(frappe.get_roles()) & set(ROLES_FINANCES + ("Agent de scolarité",)):
		frappe.throw(_("Accès réservé au service financier et à la scolarité."), frappe.PermissionError)
	from udshed.utils import perimetre

	perimetre.exiger_etudiant(student)
	return situation(student)


def situation(student):
	echeances = frappe.get_all("Echeance Etudiant", filters={"student": student},
							   fields=["name", "libelle", "academic_year", "montant", "montant_paye", "reste",
									   "date_echeance", "statut"], order_by="date_echeance asc")
	paiements = frappe.get_all("Paiement Etudiant", filters={"student": student},
							   fields=["name", "echeance", "montant", "date_paiement", "mode", "reference"],
							   order_by="date_paiement desc")
	return {"echeances": echeances, "paiements": paiements, "blocages": [b.name for b in blocages(student)],
			"total_du": sum(flt(e.reste) for e in echeances if e.statut != "Exonérée")}


@frappe.whitelist()
def recu(paiement):
	"""Reçu PDF d'un paiement (service financier ou l'étudiant lui-même)."""
	from frappe.utils.pdf import get_pdf

	from udshed.utils.etablissement import etablissement

	p = frappe.get_doc("Paiement Etudiant", paiement)
	proprietaire = frappe.db.get_value("Student", p.student, "utilisateur") == frappe.session.user
	if not (proprietaire or set(frappe.get_roles()) & set(ROLES_FINANCES)):
		frappe.throw(_("Accès refusé."), frappe.PermissionError)
	e = frappe.get_doc("Echeance Etudiant", p.echeance)
	etab = etablissement()
	esc = frappe.utils.escape_html
	nom = frappe.db.get_value("Student", p.student, "nom") or p.student
	html = f"""<div style="font-family:Helvetica,Arial,sans-serif;font-size:13px;padding:24px">
	<h2 style="margin:0">{esc(etab.nom or "")}</h2><p style="color:#666;margin:2px 0 18px">{esc(_("Reçu de paiement"))} {esc(p.name)}</p>
	<table style="width:100%;border-collapse:collapse">
	<tr><td style="padding:6px 0;width:40%">{esc(_("Étudiant"))}</td><td><b>{esc(nom)}</b> ({esc(p.student)})</td></tr>
	<tr><td style="padding:6px 0">{esc(_("Objet"))}</td><td>{esc(e.libelle)} — {esc(e.academic_year)}</td></tr>
	<tr><td style="padding:6px 0">{esc(_("Montant reçu"))}</td><td><b>{esc(frappe.format(p.montant, {"fieldtype": "Currency"}))}</b></td></tr>
	<tr><td style="padding:6px 0">{esc(_("Date"))}</td><td>{esc(frappe.format(p.date_paiement, {"fieldtype": "Date"}))}</td></tr>
	<tr><td style="padding:6px 0">{esc(_("Mode"))}</td><td>{esc(p.mode)}{(" — " + esc(p.reference)) if p.reference else ""}</td></tr>
	<tr><td style="padding:6px 0">{esc(_("Reste à payer sur cette échéance"))}</td><td>{esc(frappe.format(e.reste, {"fieldtype": "Currency"}))}</td></tr>
	</table></div>"""
	frappe.local.response.filename = f"recu-{p.name}.pdf"
	frappe.local.response.filecontent = get_pdf(html)
	frappe.local.response.type = "pdf"
