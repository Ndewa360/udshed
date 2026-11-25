"""Rôle « Responsable Diplomation » (actes académiques, jury de diplomation).

Créé avant la synchronisation des DocTypes qui lui donnent des permissions.
"""

import frappe


def execute():
	if not frappe.db.exists("Role", "Responsable Diplomation"):
		frappe.get_doc({"doctype": "Role", "role_name": "Responsable Diplomation", "desk_access": 1}).insert(
			ignore_permissions=True
		)
