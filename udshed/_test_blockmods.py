import frappe
import traceback

def dump():
    user_email = "matricule.student@ndewa.edu"
    modules_to_block = [
        "Automation", "Contacts", "Core", "Desk", "Email", "Geo",
        "Integrations", "Printing", "Website", "Workflow",
    ]

    u = frappe.get_doc("User", user_email)
    u.block_modules = []
    for m in modules_to_block:
        u.append("block_modules", {"module": m})
    u.save(ignore_permissions=True)
    print("block_modules set:", [b.module for b in u.block_modules])

    frappe.clear_cache(user=user_email)

    frappe.set_user(user_email)
    uu = frappe.get_user()
    uu.build_permissions()
    print("\ncan_read (%d):" % len(uu.can_read))
    for c in sorted(uu.can_read):
        print("  -", c)
    print("\nallow_modules:", sorted(uu.allow_modules))
    print("permitted_modules:", sorted(uu.permitted_modules))

    from frappe.desk.desk_views import DeskViews
    from frappe.desk.desktop import get_workspaces
    wks = get_workspaces()
    print("\nWorkspaces (get_workspaces):", [p.get("name") for p in wks.get("pages", [])])

    allowed_pages = [d.name for d in wks.get("pages")]
    from frappe.boot import get_sidebar_items
    sidebar = get_sidebar_items(allowed_pages)
    print("\nSidebar items:")
    for k, v in sidebar.items():
        labels = [x.get("label") for x in v.get("items", [])]
        print(f"  - {k}: {labels}")
    frappe.set_user("Administrator")

frappe.set_user("Administrator")
try:
    dump()
except Exception:
    traceback.print_exc()