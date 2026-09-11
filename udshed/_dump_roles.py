import frappe

def dump():
    print("=== Tous les rôles en base ===")
    for r in frappe.db.sql("SELECT name, desk_access FROM `tabRole` ORDER BY name", as_dict=True):
        print(f"  '{r.name}' | desk_access={r.desk_access}")

    print("\n=== Rôles du user test ===")
    for r in frappe.db.sql("""
        SELECT rr.parent AS user, rr.role FROM `tabHas Role` rr
        JOIN `tabUser` u ON u.name = rr.parent
        WHERE u.name = %s
    """, ("matricule.student@ndewa.edu",), as_dict=True):
        print("  ", r.user, "->", repr(r.role))

    print("\n=== Workspace 'Inscription - Reinscription' roles exacts ===")
    doc = frappe.get_doc("Workspace", "Inscription - Reinscription")
    print("  ", [repr(r.role) for r in doc.roles])

frappe.set_user("Administrator")
dump()