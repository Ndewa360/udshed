import frappe

STAFF = [
	"System Manager", "Workspace Manager", "Coordonateur", "Script Manager",
	"Teacher", "Enseignant", "Planning Manager", "Registration Manager",
	"Agent de scolarité", "Comptable", "Udshed Financial Admin",
]

def exec():
	# 1. Attribuer les rôles staff SAUF student aux workspaces natifs (roles=[])
	for name in ["Build", "Users", "Website", "Integrations", "Welcome Workspace"]:
		ws = frappe.get_doc("Workspace", name)
		ws.set("roles", [])
		for role in STAFF:
			ws.append("roles", {"role": role})
		if not ws.get("type"):
			ws.set("type", "Workspace")
		ws.save(ignore_permissions=True)
		print(name, "->", [r.role for r in ws.roles])

	# 2. default_workspace pour le user test
	user = frappe.get_doc("User", "matricule.student@ndewa.edu")
	user.db_set("default_workspace", "Inscription - Reinscription")
	print("default_workspace:", frappe.db.get_value("User", "matricule.student@ndewa.edu", "default_workspace"))

	frappe.db.commit()