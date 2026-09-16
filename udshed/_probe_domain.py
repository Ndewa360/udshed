import frappe

def exec():
    print("active domains:", frappe.get_active_domains())
    from frappe.desk.desk_views import DeskViews
    dv = DeskViews()
    print("restricted_pages count:", len(dv.restricted_pages or []))
    ap = DeskViews.get_allowed_pages(cache=False, user="matricule.student@ndewa.edu")
    print("allowed_pages student:", sorted(ap.keys())[:60])
    print("-------------- sidebar DB -------------")
    ws = frappe.get_doc("Workspace", "Inscription - Reinscription")
    print("links:", [(l.label, l.link_type, l.link_to) for l in ws.links])
    print("shortcuts:", [(s.label, s.type, s.link_to) for s in ws.shortcuts])
    items = frappe.get_all("Workspace Sidebar Item", fields=["label","link_type","link_to","idx"], filters={"parent":"Inscription - Reinscription"}, order_by="idx")
    for it in items:
        print(it)