# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

CHAMPS_IDENTITE = ("school_name", "school_logo")


class UdshedSetting(Document):
	def on_update(self):
		if any(self.has_value_changed(champ) for champ in CHAMPS_IDENTITE):
			synchroniser_identite_site()


def synchroniser_identite_site():
	"""Nom et logo de l'établissement repris par Frappe (page de connexion,
	barre du desk, titre des pages) : une seule identité configurée."""
	s = frappe.get_single("Udshed Setting")
	nom = (s.school_name or "").strip()
	logo = (s.school_logo or "").strip()
	# Un logo en fichier privé n'est pas lisible sur la page de connexion.
	logo_public = logo if logo and not logo.startswith("/private/") else ""

	ws = frappe.get_single("Website Settings")
	modifie = False
	if nom and ws.app_name != nom:
		ws.app_name = nom
		modifie = True
	if logo_public and ws.app_logo != logo_public:
		ws.app_logo = logo_public
		modifie = True
	if modifie:
		ws.flags.ignore_permissions = True
		ws.save()
	if logo_public and frappe.db.get_single_value("Navbar Settings", "app_logo") != logo_public:
		frappe.db.set_single_value("Navbar Settings", "app_logo", logo_public)
	frappe.clear_cache()
