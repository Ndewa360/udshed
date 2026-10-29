import frappe

def exec():
	# 1. Synchroniser les Has Role du workspace et desktop icon: Student -> student
	rows = frappe.db.sql(
		"SELECT parenttype, parent FROM `tabHas Role` WHERE role = 'Student'", as_dict=True
	)
	print("Has Role 'Student' fixes needed:", len(rows))
	frappe.db.sql("UPDATE `tabHas Role` SET role = 'student' WHERE role = 'Student'")
	print("done")

	# 2. Recharger le workspace depuis son JSON (source de vérité, developer mode)
	if frappe.conf.developer_mode:
		from frappe.modules.utils import sync_customizations, sync_for
		from frappe.utils.modules import get_doc_path

		path = get_doc_path("udshed", "udshed", "workspace", "inscription___reinscription", "inscription___reinscription.json")
		import json
		with open(path) as f:
			data = json.load(f)
		print("json roles:", data.get("roles"))

	ws = frappe.get_doc("Workspace", "Inscription - Reinscription")
	print("workspace roles now:", [(r.role) for r in ws.roles])

	# 3. Desktop icon roles
	try:
		di = frappe.get_doc("Desktop Icon", "Inscription - Reinscription")
		print("desktop icon roles:", [(r.role) for r in di.roles])
	except Exception as e:
		print("desktop icon err:", e)