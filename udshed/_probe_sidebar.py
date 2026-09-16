import frappe

def exec():
	for w in frappe.get_all("Workspace Sidebar", fields=["name", "module", "app"], order_by="name"):
		print(w)
	print("---")
	# liste les Workspace Sidebar pour inscription
	ws = frappe.get_all("Workspace Sidebar", filters={"name": ["like", "inscription%"]}, fields=["name"])
	print("inscription sidebars:", ws)