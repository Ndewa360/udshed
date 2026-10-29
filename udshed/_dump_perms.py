import frappe
import traceback

def dump():
    print("=== Rôles desk_access=1 ===")
    for r in frappe.db.sql("SELECT name FROM `tabRole` WHERE desk_access=1 ORDER BY name", as_dict=True):
        print("  ", r.name)

    print("\n=== can_read du user etudiant matricule.student@ndewa.edu ===")
    frappe.set_user("matricule.student@ndewa.edu")
    u = frappe.get_user()
    u.build_permissions()
    cr = sorted(u.can_read)
    print("  can_read (%d):" % len(cr))
    for c in cr:
        print("    -", c)
    print("  allow_modules:", sorted(u.allow_modules))
    frappe.set_user("Administrator")

    print("\n=== Workspaces + roles actuels ===")
    for w in frappe.get_all("Workspace", fields=["name", "module", "for_user"], order_by="name"):
        try:
            doc = frappe.get_cached_doc("Workspace", w.name)
            roles = [r.role for r in doc.roles]
        except Exception:
            roles = "ERR"
        print(f"  {w.name} | module={w.module} | for_user={w.for_user} | roles={roles}")

frappe.set_user("Administrator")
try:
    dump()
except Exception:
    traceback.print_exc()