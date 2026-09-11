import frappe
import traceback

try:
    email = "matricule.student@ndewa.edu"
    if frappe.db.exists("User", email):
        frappe.delete_doc("User", email, force=1, ignore_permissions=True)
    u = frappe.new_doc("User")
    u.email = email
    u.first_name = "Etudiant"
    u.last_name = "Test"
    u.username = "STU-9999"
    u.append("roles", {"role": "Student"})
    u.flags.ignore_permissions = True
    u.flags.ignore_mandatory = True
    u.insert()
    frappe.db.commit()
    print("OK user created:", u.name, "username:", u.username)
except Exception:
    traceback.print_exc()
    frappe.db.rollback()