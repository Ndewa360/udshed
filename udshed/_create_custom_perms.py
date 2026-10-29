import frappe

def exec():
    doctype = "Session Inscription Candidate"
    
    # Check if Custom DocPerms already exist
    existing = frappe.get_all("Custom DocPerm", fields=["role"], filters={"parent": doctype})
    if existing:
        print("Custom DocPerms already exist:", [e.role for e in existing])
        return
    
    # Define perms to preserve for each role
    perms_data = [
        {"role": "Guest", "read": 1, "write": 0, "create": 1, "delete": 0, "submit": 0, "cancel": 0, "amend": 0, "report": 0, "import": 0, "export": 0, "print": 0, "email": 0, "share": 0},
        {"role": "Coordonateur", "read": 1, "write": 1, "create": 0, "delete": 0, "submit": 0, "cancel": 0, "amend": 0, "report": 0, "import": 0, "export": 0, "print": 0, "email": 0, "share": 0},
        {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "submit": 0, "cancel": 0, "amend": 0, "report": 1, "import": 0, "export": 1, "print": 1, "email": 1, "share": 1},
        {"role": "Agent de scolarité", "read": 1, "write": 1, "create": 0, "delete": 0, "submit": 0, "cancel": 0, "amend": 0, "report": 0, "import": 0, "export": 0, "print": 0, "email": 0, "share": 0},
        {"role": "student", "read": 0, "write": 0, "create": 0, "delete": 0, "submit": 0, "cancel": 0, "amend": 0, "report": 0, "import": 0, "export": 0, "print": 0, "email": 0, "share": 0},
    ]
    
    for p in perms_data:
        doc = frappe.get_doc({
            "doctype": "Custom DocPerm",
            "parent": doctype,
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role": p["role"],
            "read": p["read"],
            "write": p["write"],
            "create": p["create"],
            "delete": p["delete"],
            "submit": p["submit"],
            "cancel": p["cancel"],
            "amend": p["amend"],
            "report": p["report"],
            "import": p["import"],
            "export": p["export"],
            "print": p["print"],
            "email": p["email"],
            "share": p["share"]
        })
        doc.insert(ignore_permissions=True)
        print(f"Created Custom DocPerm for {p['role']}")
    
    frappe.db.commit()
    print("All Custom DocPerms created")