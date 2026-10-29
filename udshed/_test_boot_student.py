import frappe

def exec():
	frappe.set_user("matricule.student@ndewa.edu")
	print("roles:", frappe.get_roles())
	print("user:", frappe.session.user)

	from frappe.boot import get_bootinfo
	bi = get_bootinfo()
	print("--- workspace_sidebar_item keys:", list(bi.get("workspace_sidebar_item", {}).keys()))
	for k, v in bi.get("workspace_sidebar_item", {}).items():
		if isinstance(v, list):
			print("  ", k, "->", [i.get("label") for i in v])
		else:
			print("  ", k, "->", [i.get("label") for i in v.get("items", [])])
	print("module_wise_workspaces:", bi.get("module_wise_workspaces"))
	print("desktop_icons_by_type:", "present" if bi.get("desktop_icons_by_type") else "absent")
	print("app_data:", bi.get("app_data"))
	print("workspaces pages:", [(p.get("name")) for p in bi.get("workspaces", {}).get("pages", [])])
	print("home_page:", bi.get("home_page"))