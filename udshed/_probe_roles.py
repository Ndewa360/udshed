import frappe

def exec():
	# Quel rôle existe réellement en DB ?
	for r in ["Student", "student"]:
		row = frappe.db.get_value("Role", r, ["name", "is_custom", "desk_access"])
		print(r, "->", row)
	# Où sont stockés les rôles du workspace ?
	rows = frappe.db.sql("SELECT parenttype, parent, role FROM `tabHas Role` WHERE role IN ('Student','student')", as_dict=True)
	for r in rows:
		print(r)
	# def du champ roles du workspace
	meta = frappe.get_meta("Workspace")
	print("Has Role child table? ", "Workspace Role" in [f.options for f in meta.get("fields") if f.fieldtype=="Table"])
	ws = frappe.get_doc("Workspace", "Inscription - Reinscription")
	print("workspace roles:", [(r.role) for r in ws.roles])