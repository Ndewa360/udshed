import frappe

frappe.connect()

sidebars = frappe.get_all("Workspace Sidebar", fields=["name", "standard", "app", "title"])
print("=== Workspace Sidebars ===")
for s in sidebars:
    print(s)

workspaces = frappe.get_all("Workspace", fields=["name", "module", "app", "is_hidden", "public"])
print("\n=== Workspaces ===")
for w in workspaces:
    print(w)

frappe.destroy()
