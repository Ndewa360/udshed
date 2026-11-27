# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""API de l'interface : file « À faire » et préférences de notification."""

import frappe
from frappe import _
from frappe.utils import cint

from udshed.notifications.attentes import a_faire


@frappe.whitelist()
def mes_taches():
	"""Actions qui attendent l'utilisateur connecté (et celles en retard dans son périmètre)."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Connexion requise."), frappe.PermissionError)
	return a_faire(frappe.session.user)


@frappe.whitelist()
def mes_preferences():
	"""Notifications facultatives, avec les canaux choisis par l'utilisateur."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Connexion requise."), frappe.PermissionError)
	prefs = {p.regle: p for p in frappe.get_all("Preference Notification", filters={"utilisateur": user},
												 fields=["regle", "application", "email", "sms"])}
	res = []
	for r in frappe.get_all("Regle Notification", filters={"actif": 1},
							fields=["code", "libelle", "categorie", "obligatoire", "canal_application", "canal_email",
									"canal_sms"], order_by="categorie asc, libelle asc"):
		p = prefs.get(r.code)
		res.append({**r, "pref_application": cint(p.application) if p else 1, "pref_email": cint(p.email) if p else 1,
					"pref_sms": cint(p.sms) if p else 1})
	return res


@frappe.whitelist(methods=["POST"])
def programmer_publication(session, publier_le=None):
	"""Programme (ou annule) la publication d'une session : décision humaine prise d'avance,
	exécutée par la tâche horaire. Mêmes droits que la publication immédiate."""
	from frappe.utils import get_datetime, now_datetime

	from udshed.api.saisie_notes import _verifier_droit_session

	_verifier_droit_session(session)
	if frappe.db.get_value("Session Examen", session, "statut") != "Brouillon":
		frappe.throw(_("Cette session est déjà publiée."))
	if publier_le:
		if get_datetime(publier_le) <= now_datetime():
			frappe.throw(_("Choisissez une date future."))
		frappe.db.set_value("Session Examen", session, {"publier_le": publier_le, "programme_par": frappe.session.user})
	else:
		frappe.db.set_value("Session Examen", session, {"publier_le": None, "programme_par": None})
	return {"publier_le": publier_le or None}


@frappe.whitelist(methods=["POST"])
def enregistrer_preference(regle, application=1, email=1, sms=1):
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Connexion requise."), frappe.PermissionError)
	if not frappe.db.exists("Regle Notification", regle):
		frappe.throw(_("Notification inconnue."))
	if cint(frappe.db.get_value("Regle Notification", regle, "obligatoire")):
		frappe.throw(_("Cette notification est obligatoire : elle ne peut pas être désactivée."))
	nom = frappe.db.get_value("Preference Notification", {"utilisateur": user, "regle": regle}, "name")
	doc = frappe.get_doc("Preference Notification", nom) if nom else frappe.new_doc("Preference Notification")
	doc.update({"utilisateur": user, "regle": regle, "application": cint(application), "email": cint(email),
				"sms": cint(sms)})
	doc.save(ignore_permissions=True)
	return {"ok": True}
