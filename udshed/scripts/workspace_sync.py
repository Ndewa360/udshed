import frappe, json, os

def fix_workspace_visibility():
    """Fix workspace visibility - run via bench console:
    bench --site [site-name] console
    >>> import udshed.scripts.workspace_sync as wsf
    >>> wsf.fix_workspace_visibility()
    """
    site = frappe.local.site
    app_name = "udshed"
    app_path = frappe.get_app_path(app_name)

    # Step 1: Force-sync workspace JSON files to DB
    print(f"\n{'='*60}")
    print(f"FIX WORKSPACE VISIBILITY - Site: {site}")
    print(f"{'='*60}\n")

    print("STEP 1: Syncing workspace records from JSON files...")
    ws_dir = os.path.join(app_path, app_name, "workspace")
    if os.path.exists(ws_dir):
        for ws_subdir in os.listdir(ws_dir):
            ws_json = os.path.join(ws_dir, ws_subdir, f"{ws_subdir}.json")
            if os.path.exists(ws_json):
                from frappe.modules.import_file import import_file_by_path
                import_file_by_path(ws_json, force=True, ignore_version=True)
                frappe.db.commit()
                print(f"  ✅ Synced: {ws_json}")

    # Step 2: Sync workspace_sidebar JSON files
    print("\nSTEP 2: Syncing workspace sidebars...")
    sb_dir = os.path.join(app_path, "workspace_sidebar")
    if os.path.exists(sb_dir):
        for fname in sorted(os.listdir(sb_dir)):
            if fname.endswith(".json"):
                sb_path = os.path.join(sb_dir, fname)
                from frappe.modules.import_file import import_file_by_path
                import_file_by_path(sb_path, force=True, ignore_version=True)
                frappe.db.commit()
                print(f"  ✅ Synced sidebar: {fname}")

    # Step 3: Sync desktop_icon JSON files
    print("\nSTEP 3: Syncing desktop icons...")
    icon_dir = os.path.join(app_path, "desktop_icon")
    if os.path.exists(icon_dir):
        for fname in sorted(os.listdir(icon_dir)):
            if fname.endswith(".json"):
                icon_path = os.path.join(icon_dir, fname)
                from frappe.modules.import_file import import_file_by_path
                import_file_by_path(icon_path, force=True, ignore_version=True)
                frappe.db.commit()
                print(f"  ✅ Synced icon: {fname}")

    # Step 4: Auto-generate desktop icons and sidebars
    print("\nSTEP 4: Auto-generating desktop icons and sidebars...")
    from frappe.desk.doctype.desktop_icon.desktop_icon import create_desktop_icons
    from frappe.desk.doctype.workspace_sidebar.workspace_sidebar import create_workspace_sidebar_for_workspaces
    create_desktop_icons()
    frappe.db.commit()
    print("  ✅ Desktop icons auto-generated")
    create_workspace_sidebar_for_workspaces()
    frappe.db.commit()
    print("  ✅ Workspace sidebars auto-generated")

    # Step 5: Verify the workspace
    print(f"\nSTEP 5: Verification...")
    ws_name = "Inscription - Reinscription"
    if frappe.db.exists("Workspace", ws_name):
        ws = frappe.get_doc("Workspace", ws_name)
        print(f"  ✅ Workspace '{ws_name}' exists in DB")
        print(f"     public: {ws.public}")
        print(f"     is_hidden: {ws.is_hidden}")
        print(f"     sequence_id: {ws.sequence_id}")
        print(f"     module: {ws.module}")
        print(f"     roles: {[r.role for r in ws.roles]}")
    else:
        print(f"  ❌ Workspace '{ws_name}' NOT found in DB!")

    if frappe.db.exists("Workspace Sidebar", ws_name):
        print(f"  ✅ Workspace Sidebar '{ws_name}' exists")
    else:
        print(f"  ❌ Workspace Sidebar '{ws_name}' NOT found!")

    if frappe.db.exists("Desktop Icon", ws_name):
        icon = frappe.get_doc("Desktop Icon", ws_name)
        print(f"  ✅ Desktop Icon '{ws_name}' exists")
        print(f"     link_type: {icon.link_type}")
        print(f"     sidebar: {icon.sidebar}")
    else:
        print(f"  ❌ Desktop Icon '{ws_name}' NOT found!")

    print(f"\n{'='*60}")
    print("FIX COMPLETE")
    print(f"{'='*60}")
    print("\nNow refresh your Frappe desktop (Ctrl+F5 or Cmd+Shift+R).")
    print("If the workspace still doesn't appear, run 'bench migrate' and try again.")


def diagnose():
    """Diagnose workspace visibility issues."""
    print("\n=== WORKSPACE DIAGNOSTIC ===\n")

    all_ws = frappe.get_all("Workspace", fields=["name", "public", "is_hidden", "module", "sequence_id"])
    print(f"Total workspaces in DB: {len(all_ws)}")
    for ws in all_ws:
        print(f"  - {ws.name} (public={ws.public}, hidden={ws.is_hidden}, module={ws.module}, seq={ws.sequence_id})")

    print(f"\nCurrent user: {frappe.session.user}")
    print(f"User roles: {frappe.get_roles()}")

    target = "Inscription - Reinscription"
    if frappe.db.exists("Workspace", target):
        ws = frappe.get_doc("Workspace", target)
        print(f"\n=== TARGET: {target} ===")
        print(f"  public: {ws.public}")
        print(f"  is_hidden: {ws.is_hidden}")
        print(f"  sequence_id: {ws.sequence_id}")
        print(f"  module: {ws.module}")
        print(f"  app: {ws.app}")
        print(f"  roles: {[r.role for r in ws.roles]}")
        user_roles = set(frappe.get_roles())
        ws_roles = set(r.role for r in ws.roles)
        if ws_roles & user_roles:
            print(f"  ✅ User has matching role: {ws_roles & user_roles}")
        else:
            print(f"  ❌ User has NO matching role!")
            print(f"     User roles: {user_roles}")
            print(f"     Required roles: {ws_roles}")
    else:
        print(f"\n❌ Workspace '{target}' does NOT exist in database!")
        print("   Run fix_workspace_visibility() to create it.")

    if frappe.db.exists("Workspace Sidebar", target):
        sidebar = frappe.get_doc("Workspace Sidebar", target)
        print(f"\n=== SIDEBAR: {target} ===")
        print(f"  items count: {len(sidebar.items)}")
        print(f"  module: {sidebar.module}")
    else:
        print(f"\n❌ Workspace Sidebar '{target}' NOT found!")

    if frappe.db.exists("Desktop Icon", target):
        icon = frappe.get_doc("Desktop Icon", target)
        print(f"\n=== DESKTOP ICON: {target} ===")
        print(f"  link_type: {icon.link_type}")
        print(f"  link_to: {icon.link_to}")
        print(f"  sidebar: {icon.sidebar}")
        print(f"  hidden: {icon.hidden}")
        print(f"  roles: {[r.role for r in icon.roles]}")
        print(f"  app_name: {icon.app_name}")
        user_roles = set(frappe.get_roles())
        icon_roles = set(r.role for r in icon.roles)
        if icon_roles & user_roles:
            print(f"  ✅ User has matching role: {icon_roles & user_roles}")
        else:
            print(f"  ❌ User has NO matching role for icon!")
    else:
        print(f"\n❌ Desktop Icon '{target}' NOT found!")

    print(f"\n=== MODULE INFO ===")
    if frappe.db.exists("Module Def", "Udshed"):
        mod = frappe.get_doc("Module Def", "Udshed")
        print(f"  Module 'Udshed': app_name = {mod.app_name}")
    else:
        print(f"  ❌ Module 'Udshed' does not exist!")

    print(f"\nDiagnostic complete.")
