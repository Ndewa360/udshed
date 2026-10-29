import frappe

def exec():
    frappe.set_user("matricule.student@ndewa.edu")
    print("User roles:", frappe.get_roles())
    print("Has permission Session Inscription Candidate read:", frappe.has_permission("Session Inscription Candidate", "read"))
    print("Has permission Session Inscription Candidate:", frappe.has_permission("Session Inscription Candidate"))