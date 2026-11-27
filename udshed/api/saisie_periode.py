"""Saisie des notes : confirmation par l'enseignant et dérogations (doyen / vice-doyen).

Enseignant :
  confirmer_saisie(...)      déclare sa saisie terminée (pendant la période)
  demander_derogation(...)   après la date limite : demande de réouverture au doyen / vice-doyen
Doyen / vice-doyen de la faculté :
  decider_derogation(name, accorder, valable_jusqu_au, commentaire)
"""

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from udshed.utils import perimetre
from udshed.utils import periode_saisie as ps


def _contexte(academic_year, filiere, niveau, semestre, teaching_unit, type_dexamen):
	from udshed.api import saisie_notes

	saisie_notes._verifier_acces_enseignant(teaching_unit)
	perimetre.exiger_filiere(filiere)
	semestre = saisie_notes._semestre_effectif({"semestre": semestre, "teaching_unit": teaching_unit})
	mode = saisie_notes._mode_saisie(type_dexamen)
	mode = mode if mode in ps.TYPES else "examen"
	return semestre, mode


def _faculte(filiere):
	return frappe.db.get_value("Field of study", filiere, "faculte") if filiere else None


def _notifier(users, sujet, message, nom):
	for user in {u for u in users if u and u not in ("Administrator", "Guest")}:
		frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert", "subject": sujet,
						"email_content": message, "document_type": "Derogation Saisie",
						"document_name": nom}).insert(ignore_permissions=True)
		email = frappe.db.get_value("User", user, "email")
		if email:
			# L'e-mail est un plus : sans compte d'envoi configuré, la notification suffit.
			try:
				frappe.sendmail(recipients=[email], subject=sujet, message=f"<p>{frappe.utils.escape_html(message)}</p>",
								reference_doctype="Derogation Saisie", reference_name=nom, delayed=True)
			except Exception:
				frappe.log_error(title="udshed: e-mail de dérogation de saisie")


@frappe.whitelist()
def confirmer_saisie(academic_year, filiere, niveau, semestre, teaching_unit, type_dexamen=None, session_examen=None):
	semestre, mode = _contexte(academic_year, filiere, niveau, semestre, teaching_unit, type_dexamen)
	e = ps.exiger_saisie_ouverte(academic_year, semestre, teaching_unit, filiere, mode, session_examen)
	nom = ps.confirmation(academic_year, semestre, teaching_unit, e.type_evaluation, filiere, niveau)
	doc = frappe.get_doc("Confirmation Saisie", nom.name) if nom else frappe.new_doc("Confirmation Saisie")
	doc.update({"academic_year": academic_year, "semestre": semestre, "filiere": filiere, "niveau": niveau,
				"teaching_unit": teaching_unit, "type_evaluation": e.type_evaluation,
				"enseignant": ps._enseignant(), "confirme_par": frappe.session.user, "confirme_le": now_datetime()})
	doc.save(ignore_permissions=True)
	return {"name": doc.name, "confirme_le": doc.confirme_le}


@frappe.whitelist()
def demander_derogation(academic_year, filiere, niveau, semestre, teaching_unit, motif, type_dexamen=None,
						session_examen=None):
	semestre, mode = _contexte(academic_year, filiere, niveau, semestre, teaching_unit, type_dexamen)
	if not (motif or "").strip():
		frappe.throw(_("Indiquez le motif de la demande."))
	e = ps.etat(academic_year, semestre, teaching_unit, filiere, mode, session_examen, niveau)
	if not e.fermee_apres_limite or e.derogation:
		frappe.throw(_("La saisie n'est pas fermée : aucune dérogation n'est nécessaire."))
	if e.demande:
		frappe.throw(_("Une demande est déjà en attente : {0}.").format(e.demande))
	faculte = _faculte(filiere)
	doc = frappe.get_doc({
		"doctype": "Derogation Saisie", "teaching_unit": teaching_unit, "type_evaluation": e.type_evaluation,
		"academic_year": academic_year, "semestre": semestre, "session_examen": session_examen, "filiere": filiere,
		"niveau": niveau, "faculte": faculte, "statut": "Demandée", "enseignant": ps._enseignant(),
		"demande_par": frappe.session.user, "demande_le": now_datetime(), "motif": motif,
	}).insert(ignore_permissions=True)
	direction = frappe.db.get_value("Faculty", faculte, ["doyen", "vice_doyen"], as_dict=True) if faculte else None
	destinataires = [direction.doyen, direction.vice_doyen] if direction else []
	if not any(destinataires):
		frappe.msgprint(_("Aucun doyen ni vice-doyen n'est renseigné pour cette faculté : prévenez l'administration."))
	_notifier(destinataires, _("Demande de réouverture de saisie : {0}").format(doc.intitule or teaching_unit),
			  _("{0} demande à saisir à nouveau les notes ({1}) : {2}").format(
				  frappe.utils.get_fullname(frappe.session.user), e.type_evaluation.lower(), motif), doc.name)
	return {"name": doc.name}


@frappe.whitelist()
def decider_derogation(name, accorder, valable_jusqu_au=None, commentaire=None):
	doc = frappe.get_doc("Derogation Saisie", name)
	roles = set(frappe.get_roles())
	if frappe.session.user != "Administrator" and "System Manager" not in roles and not perimetre.est_doyen_de(doc.faculte):
		frappe.throw(_("Seuls le doyen et le vice-doyen de la faculté décident des dérogations."), frappe.PermissionError)
	if doc.statut != "Demandée":
		frappe.throw(_("Cette demande a déjà été traitée ({0}).").format(doc.statut))
	accorder = frappe.utils.cint(accorder)
	if accorder:
		if not valable_jusqu_au or get_datetime(valable_jusqu_au) <= now_datetime():
			frappe.throw(_("Indiquez jusqu'à quand la saisie est rouverte (date future)."))
	doc.db_set({"statut": "Accordée" if accorder else "Refusée", "valable_jusqu_au": valable_jusqu_au if accorder else None,
				"commentaire": commentaire, "decide_par": frappe.session.user, "decide_le": now_datetime()})
	user = frappe.db.get_value("Teacher", doc.enseignant, "user") or doc.demande_par
	message = (_("Votre saisie ({0}) est rouverte jusqu'au {1}.").format(doc.type_evaluation.lower(), ps._jolie(valable_jusqu_au))
			   if accorder else _("Votre demande de réouverture ({0}) a été refusée.").format(doc.type_evaluation.lower()))
	if commentaire:
		message += " " + commentaire
	_notifier([user], _("Dérogation de saisie : {0}").format(doc.intitule or doc.teaching_unit), message, doc.name)
	return {"statut": doc.statut}
