import frappe

def exec():
    ws = frappe.get_doc("Workspace", "Inscription - Reinscription")
    
    # Check if shortcut already exists
    existing = [s for s in ws.shortcuts if s.label == "Se réinscrire"]
    if existing:
        print("Shortcut 'Se réinscrire' already exists")
        return
    
    ws.append("shortcuts", {
        "label": "Se réinscrire",
        "type": "Page",
        "link_to": "reinscription_etudiant",
        "icon": "user-plus"
    })
    ws.save()
    frappe.db.commit()
    print("Shortcut 'Se réinscrire' added successfully")