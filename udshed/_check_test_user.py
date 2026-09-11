import frappe

email = "matricule.student@ndewa.edu"
print("Student exists:", frappe.db.exists("Student", "STU-9999"))
print("User exists:", frappe.db.exists("User", email))
if frappe.db.exists("User", email):
    u = frappe.get_doc("User", email)
    print("user.name:", u.name)
    print("user.username:", u.username)
    print("user.roles:", [r.role for r in u.roles])
if frappe.db.exists("Student", "STU-9999"):
    s = frappe.get_doc("Student", "STU-9999")
    print("student.utilisateur:", s.utilisateur)