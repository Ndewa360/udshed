"""Automatisations : règles de notification du catalogue, calendrier académique
alimenté par les objets déjà existants, ancienne page d'appel (renommée) retirée."""

import frappe


def execute():
	from udshed.notifications import synchroniser_catalogue
	from udshed.notifications.evenements import SOURCES_JALON, synchroniser_jalon

	synchroniser_catalogue()
	if frappe.db.exists("Page", "appel-seance"):
		frappe.delete_doc("Page", "appel-seance", force=True, ignore_permissions=True)
	# Le décorateur des automatismes s'abstient pendant une migration : on lève le drapeau le temps du report.
	en_migration = frappe.flags.in_migrate
	frappe.flags.in_migrate = False
	try:
		for doctype in SOURCES_JALON:
			for nom in frappe.get_all(doctype, pluck="name"):
				synchroniser_jalon(frappe.get_doc(doctype, nom))
	finally:
		frappe.flags.in_migrate = en_migration
