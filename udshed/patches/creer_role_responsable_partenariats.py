"""Rôle « Responsable des partenariats » (conventions, vacations, attestations des enseignants).

pre_model_sync : le rôle doit exister avant la synchronisation des permissions des DocTypes."""

import frappe


def execute():
	if not frappe.db.exists("Role", "Responsable des partenariats"):
		frappe.get_doc({"doctype": "Role", "role_name": "Responsable des partenariats", "desk_access": 1}).insert(
			ignore_permissions=True)
