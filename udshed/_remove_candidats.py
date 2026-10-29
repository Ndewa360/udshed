import frappe

def exec():
    ws = frappe.get_doc("Workspace", "Inscription - Reinscription")
    
    # Remove "Candidats" shortcut
    ws.shortcuts = [s for s in ws.shortcuts if s.label != "Candidats"]
    ws.save()
    frappe.db.commit()
    print("Removed 'Candidats' shortcut")
    
    # Verify
    ws = frappe.get_doc("Workspace", "Inscription - Reinscription")
    print("Remaining shortcuts:", [(s.label, s.type, s.link_to) for s in ws.shortcuts])