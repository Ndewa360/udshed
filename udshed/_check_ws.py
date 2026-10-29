import frappe

def exec():
    ws = frappe.get_doc("Workspace", "Inscription - Reinscription")
    print("shortcuts:", [(s.label, s.type, s.link_to) for s in ws.shortcuts])