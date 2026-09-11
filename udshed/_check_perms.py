import frappe

def dump_user_perms(email):
    print(f"\n========== TESTS pour user: {email} ==========")
    if not frappe.db.exists("User", email):
        print("user n'existe pas -> on crée un user test sans l'enregistrer")
        u = frappe.new_doc("User")
        u.email = email
        u.first_name = "Test"
        u.username = "teststudent"
        u.roles = [{"role": "Student"}]
        u.flags.ignore_permissions = True
        u.flags.ignore_mandatory = True
    else:
        u = frappe.get_doc("User", email)

    user = frappe.get_user()
    user.doc = u
    frappe.set_user(email)
    user.build_permissions()

    print("allow_modules:", sorted(user.allow_modules))
    print("can_read (subset):", sorted(user.can_read)[:60])

    # workspaces perm is_permitted
    for name in ["Build", "Inscription - Reinscription", "Configuration", "Users", "Website", "Integrations", "Welcome Workspace", "Planning Académique", "Gestion des Notes"]:
        try:
            from frappe.desk.desktop import Workspace
            ws = Workspace({"name": name, "public": 1})
            print(f"  workspace {name}: is_permitted={ws.is_permitted()} | module={ws.doc.module}")
        except frappe.PermissionError:
            print(f"  workspace {name}: PERMISSION ERROR (module not allowed) | module={frappe.get_cached_doc('Workspace', name).module}")
        except Exception as e:
            print(f"  workspace {name}: ERREUR {type(e).__name__}: {e}")

dump_user_perms("etudiant.test@ndewa.edu")