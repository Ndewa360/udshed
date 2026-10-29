import frappe

def exec():
	ss = frappe.get_doc("System Settings")
	print("before:", ss.get("allow_login_using_user_name"))
	ss.set("allow_login_using_user_name", 1)
	ss.save(ignore_permissions=True)
	print("after:", frappe.db.get_value("System Settings", None, "allow_login_using_user_name"))

	stale = frappe.db.sql(
		"SELECT r.parent FROM `tabHas Role` r JOIN `tabRole` ro ON ro.name = r.role WHERE r.role = 'Student'",
		as_list=1,
	)
	print("users with role 'Student' (uppercase):", stale)

	bad = frappe.db.sql("SELECT name, username, enabled FROM `tabUser` WHERE username IS NOT NULL AND name LIKE '%student%'", as_dict=True)
	print("student users with username:", bad)

	# Check test user roles
	roles = frappe.get_roles("matricule.student@ndewa.edu")
	print("test user roles:", roles)
	print("test user username:", frappe.db.get_value("User", "matricule.student@ndewa.edu", "username"))
	print("test user default_workspace:", frappe.db.get_value("User", "matricule.student@ndewa.edu", "default_workspace"))
	print("test user user_type:", frappe.db.get_value("User", "matricule.student@ndewa.edu", "user_type"))