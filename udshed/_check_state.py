import frappe

print("=== ROLES ===")
print("role Student exists:", frappe.db.exists("Role", "Student"))
r = frappe.get_doc("Role", "Student")
print("Student desk_access:", r.desk_access)

print("\n=== SYSTEM SETTINGS ===")
print("allow_login_using_user_name:", frappe.db.get_single_value("System Settings", "allow_login_using_user_name"))

print("\n=== WORKSPACES ===")
rows = frappe.db.sql("SELECT name, module, title, public, sequence_id FROM tabWorkspace ORDER BY sequence_id ASC", as_dict=True)
for row in rows:
    roles = [x.role for x in frappe.get_list("Has Role", filters={"parent": row.name}, fields=["role"])]
    print(f"- {row.name} | module={row.module} | public={row.public} | roles={roles}")

print("\n=== PAGES having role Student ===")
pages = frappe.db.sql("SELECT parent FROM `tabHas Role` WHERE role='Student' AND parenttype='Page'", as_dict=True)
print(pages)

print("\n=== REPORTS having role Student ===")
reps = frappe.db.sql("SELECT parent FROM `tabHas Role` WHERE role='Student' AND parenttype='Report'", as_dict=True)
print(reps)