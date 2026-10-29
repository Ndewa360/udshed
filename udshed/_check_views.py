import frappe
import traceback

def dump():
    frappe.set_user("matricule.student@ndewa.edu")
    print("session.user:", frappe.session.user)
    print("roles:", frappe.get_roles())

    try:
        from frappe.desk.desktop import Desktop
        d = Desktop()
        wks = d.workspaces
        print("\nWorkspaces visibles (Desktop.workspaces):")
        for w in wks or []:
            print("   -", w)
    except Exception:
        traceback.print_exc()

    try:
        from frappe.desk.doctype.workspace.workspace import get_workspaces
        wss = get_workspaces()
        print("\nWorkspaces (get_workspaces):", [p.get("name") for p in (wss or {}).get("pages", [])])

        from frappe.boot import get_sidebar_items
        sidebar = get_sidebar_items(wss)
        print("\nSidebar items:")
        for k, v in sidebar.items():
            labels = [x.get("label") for x in v.get("items", [])]
            print(f"   - {k}: {labels}")
    except Exception:
        traceback.print_exc()

frappe.set_user("Administrator")
dump()