import frappe

def dump():
    user = "matricule.student@ndewa.edu"
    roles = frappe.get_roles(user)
    print("roles user:", roles)

    frappe.set_user(user)
    u = frappe.get_user()
    u.build_permissions()
    can_read = sorted(u.can_read)
    allow_modules = sorted(u.allow_modules)
    frappe.set_user("Administrator")

    print("\n=== doctypes can_read et par quel DOCPERM (role explicite) ===")
    for dt in can_read:
        if dt in ("Address", "Background Task", "ToDo", "File", "Communication", "Event", "Comment"):
            continue
        perms = frappe.db.get_all("DocPerm", filters={"parent": dt, "role": ["in", ['All', 'Guest', 'Desk User', 'student', 'System Manager']]}, fields=["role", "read", "write", "create", "delete"], limit_page_length=50)
        if perms:
            print(f"\n{dt}:")
            for p in perms:
                print(f"   role={p.role!r} read={p.read} write={p.write} create={p.create} delete={p['delete']}")
        else:
            print(f"\n{dt}: (aucun DocPerm explicite pour All/Guest/Desk User/student)")

    print("\n=== map modules des doctypes can_read ===")
    from collections import Counter
    c = Counter()
    for dt in can_read:
        try:
            c[frappe.get_meta(dt).module] += 1
        except Exception:
            c["??"] += 1
    for m, n in sorted(c.items()):
        print(f"  {m}: {n}")

    print("\n=== allow_modules:", allow_modules)

frappe.set_user("Administrator")
dump()