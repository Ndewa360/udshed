"""Rôles de gouvernance : Doyen, Vice-Doyen, Directeur des Affaires Académiques.

pre_model_sync : les rôles doivent exister avant la synchronisation des permissions des DocTypes."""

import frappe

ROLES = ("Doyen", "Vice-Doyen", "Directeur des Affaires Académiques")


def execute():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
