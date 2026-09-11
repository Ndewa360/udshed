import frappe

def exec():
	rows = frappe.db.sql(
		"SELECT parenttype, parent FROM `tabHas Role` WHERE role = 'Student'", as_dict=True
	)
	print("remaining 'Student' rows:", rows)
	frappe.db.sql("UPDATE `tabHas Role` SET role = 'student' WHERE role = 'Student'")
	frappe.db.commit()
	print("committed")

	ws = frappe.get_doc("Workspace", "Inscription - Reinscription")
	print("workspace roles now:", [(r.role) for r in ws.roles])

	di = frappe.get_doc("Desktop Icon", "Inscription - Reinscription")
	print("desktop icon roles now:", [(r.role) for r in di.roles])