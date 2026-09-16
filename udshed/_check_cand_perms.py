import frappe

def exec():
    doctype = "Session Inscription Candidate"
    perms = frappe.get_all("DocPerm", fields=["role", "read", "write", "create", "delete", "submit", "cancel", "amend", "report", "import", "export", "print", "email", "share"], filters={"parent": doctype})
    for p in perms:
        print(p)