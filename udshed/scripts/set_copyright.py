import frappe


def execute():
	frappe.connect()
	ws = frappe.get_single("Website Settings")
	ws.copyright = "UDSHED"
	ws.app_logo = "/assets/udshed/images/logo.png"
	ws.save()
	frappe.db.commit()
	print("Copyright updated to:", ws.copyright)
	print("App logo updated to:", ws.app_logo)
