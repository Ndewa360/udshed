import frappe
import traceback


def dump():
    SEP = "=" * 72

    perm_flags = [
        "read", "write", "create", "delete",
        "submit", "cancel", "amend",
        "report", "export", "import",
        "print", "email", "share", "select",
        "mask", "impersonate",
    ]

    def fmt_flags(row):
        return [f for f in perm_flags if row.get(f)]

    # ------------------------------------------------------------------ #
    # 0. Discover tables containing 'DocPerm'                            #
    # ------------------------------------------------------------------ #
    print(SEP)
    print("0. Tables contenant 'DocPerm'")
    print(SEP)
    docperm_tables = frappe.db.sql(
        "SHOW TABLES LIKE '%DocPerm%'", as_list=True
    )
    table_names = [row[0] for row in docperm_tables] if docperm_tables else []
    for t in table_names:
        print(f"  - {t}")
    if not table_names:
        print("  (aucune table trouvée)")
        return

    # Show columns of each table
    for tname in table_names:
        cols = frappe.db.sql(f"SHOW COLUMNS FROM `{tname}`", as_list=True)
        col_names = [c[0] for c in cols] if cols else []
        print(f"\n  Colonnes de `{tname}`: {col_names}")
        cnt = frappe.db.sql(f"SELECT COUNT(*) FROM `{tname}`", as_list=True)
        print(f"  Nombre de lignes: {cnt[0][0] if cnt else '?'}")

    # Query each table for student role
    print()
    print(SEP)
    print("1. Toutes les permissions pour le rôle 'student' (toutes tables DocPerm)")
    print(SEP)

    all_student_perms = []
    for tname in table_names:
        try:
            perms = frappe.db.sql(f"""
                SELECT '{tname}' AS _table, dp.*
                FROM `{tname}` dp
                WHERE dp.role = 'student'
                ORDER BY dp.parent
            """, as_dict=True)
            if perms:
                print(f"\n  Table `{tname}`: {len(perms)} règles pour 'student'\n")
                current_parent = None
                for p in perms:
                    parent = p.get("parent")
                    if parent != current_parent:
                        current_parent = parent
                        print(f"  --- DocType: {current_parent} (table: {tname}) ---")
                    flags = fmt_flags(p)
                    level = str(p.get("permlevel", "?"))
                    print(
                        f"    permlevel={level:<4s} "
                        f"flags=[{', '.join(flags)}]  "
                        f"if_owner={p.get('if_owner', 0)}"
                    )
                all_student_perms.extend(perms)
            else:
                print(f"  Table `{tname}`: aucune règle pour 'student'")
        except Exception as e:
            print(f"  Table `{tname}`: ERREUR - {e}")

    if not all_student_perms:
        print("\n  >> Aucune permission DocPerm/Custom DocPerm pour 'student' dans aucune table.")
        print("  >> Les permissions proviennent probablement de permissions implicites")
        print("  >> (guest, Everyone, ou permissions de base du DocType).")
        print("  >> Vérification via FrappeUser.build_permissions() ci-dessus (section 2)")

    # ------------------------------------------------------------------ #
    # 2. Roles de l'utilisateur matricule.student@ndewa.edu              #
    # ------------------------------------------------------------------ #
    print()
    print(SEP)
    print("2. Rôles de l'utilisateur 'matricule.student@ndewa.edu'")
    print(SEP)

    user_email = "matricule.student@ndewa.edu"

    user_exists = frappe.db.sql(
        "SELECT name, enabled, user_type FROM `tabUser` WHERE name = %s",
        (user_email,), as_dict=True,
    )
    if not user_exists:
        print(f"  Utilisateur '{user_email}' introuvable en base !")
    else:
        u0 = user_exists[0]
        print(f"  User: {u0.name}  enabled={u0.enabled}  type={u0.user_type}")

    roles = frappe.db.sql("""
        SELECT rr.role
        FROM `tabHas Role` rr
        WHERE rr.parent = %s
        ORDER BY rr.role
    """, (user_email,), as_dict=True)

    if not roles:
        print("  Aucun rôle trouvé via tabHas Role.")
    else:
        print(f"  Nombre de rôles: {len(roles)}\n")
        has_student = False
        for r in roles:
            marker = ""
            if r.role == "student":
                has_student = True
                marker = "  <-- rôle cible"
            print(f"    - {r.role}{marker}")
        if not has_student:
            print("\n  *** ANOMALIE: Le rôle 'student' n'est PAS assigné ! ***")

    # can_read / can_write via Frappe permission model
    print()
    print(f"  can_read / can_write (via FrappeUser) pour {user_email}:")
    try:
        frappe.set_user(user_email)
        u = frappe.get_user()
        u.build_permissions()
        cr = sorted(u.can_read)
        cw = sorted(u.can_write)
        print(f"    can_read  ({len(cr)}):")
        for c in cr:
            print(f"      - {c}")
        print(f"    can_write ({len(cw)}):")
        for c in cw:
            print(f"      - {c}")
        print(f"    allow_modules: {sorted(u.allow_modules)}")
    except Exception as e:
        print(f"    ERREUR build_permissions: {e}")
    finally:
        frappe.set_user("Administrator")

    # ------------------------------------------------------------------ #
    # 3. DocPerm pour les DocTypes Udshed                                 #
    # ------------------------------------------------------------------ #
    print()
    print(SEP)
    print("3. DocPerm détaillés pour les DocTypes du module Udshed")
    print(SEP)

    udshed_doctypes = [
        "Academic Reregistration",
        "Session Reinscription",
        "Session Inscription",
        "Session Inscription Candidate",
        "Academic Year",
        "Student",
        "Field of study",
        "Field of study Level",
        "Fee Structure",
    ]

    for dt_name in udshed_doctypes:
        print(f"\n  --- DocType: '{dt_name}' ---")
        exists = frappe.db.sql(
            "SELECT name FROM `tabDocType` WHERE name = %s",
            (dt_name,), as_dict=True,
        )
        if not exists:
            print("    (DocType introuvable dans tabDocType)")
            continue

        # Query all DocPerm tables for this doctype
        found_any = False
        for tname in table_names:
            doc_perms = frappe.db.sql(f"""
                SELECT '{tname}' AS _table, dp.*
                FROM `{tname}` dp
                WHERE dp.parent = %s
                ORDER BY dp.permlevel, dp.role
            """, (dt_name,), as_dict=True)

            if doc_perms:
                found_any = True
                print(f"    [{len(doc_perms)} règles depuis `{tname}`]")
                for dp in doc_perms:
                    flags = fmt_flags(dp)
                    level = str(dp.get("permlevel", "?"))
                    print(
                        f"      role={str(dp.get('role', '?')):<30s} "
                        f"permlevel={level:<4s} "
                        f"flags=[{', '.join(flags)}]  "
                        f"if_owner={dp.get('if_owner', 0)}"
                    )

        if not found_any:
            print("    Aucune permission DocPerm définie dans aucune table.")

    # ------------------------------------------------------------------ #
    # 4. Résumé & anomalies                                               #
    # ------------------------------------------------------------------ #
    print()
    print(SEP)
    print("4. RÉSUMÉ & ANOMALIES")
    print(SEP)

    # Build list from Frappe's own permission model (most reliable)
    print()
    print("  a) DocTypes lisibles par l'utilisateur (via FrappeUser.build_permissions):")
    try:
        frappe.set_user(user_email)
        u = frappe.get_user()
        u.build_permissions()
        cr = sorted(u.can_read)
        framework_list = cr
        for c in cr:
            print(f"    - {c}")
        print(f"\n  Total DocTypes lus: {len(cr)}")
    except Exception as e:
        print(f"    ERREUR: {e}")
        framework_list = []
    finally:
        frappe.set_user("Administrator")

    known_framework = {
        "User", "Role", "Has Role", "DocType", "DocPerm",
        "Report", "Dashboard", "Dashboard Chart",
        "Workspace", "Page", "Web Page", "File",
        "Comment", "Activity Log", "Version",
        "Communication", "Email Account",
        "Print Format", "Letter Head", "Workflow",
        "Workflow State", "Workflow Action",
        "Background Task", "Submission Queue",
    }
    flagged = [p for p in framework_list if p in known_framework]
    if flagged:
        print()
        print("  *** ANOMALIE: L'utilisateur a accès en lecture sur des DocTypes framework critiques: ***")
        for f in sorted(flagged):
            print(f"    !! {f}")
    else:
        print("  (aucune anomalie framework détectée)")

    # Cross-check with SQL-based perms
    print()
    print("  b) Vérification croisée: permissions SQL vs FrappeUser pour 'student':")
    sql_parents = set()
    for tname in table_names:
        rows = frappe.db.sql(f"""
            SELECT DISTINCT dp.parent
            FROM `{tname}` dp
            WHERE dp.role = 'student' AND dp.`read` = 1
        """, as_list=True)
        for row in (rows or []):
            sql_parents.add(row[0])

    frappe_user_parents = set(framework_list) if framework_list else set()

    only_frappe = frappe_user_parents - sql_parents
    only_sql = sql_parents - frappe_user_parents
    both = frappe_user_parents & sql_parents

    print(f"    SQL DocPerm pour student: {len(sql_parents)} DocTypes")
    print(f"    FrappeUser can_read:      {len(frappe_user_parents)} DocTypes")
    print(f"    Commun:                   {len(both)}")
    print(f"    Uniquement FrappeUser (pas de DocPerm explicite): {len(only_frappe)}")
    if only_frappe:
        for x in sorted(only_frappe):
            print(f"      - {x}")
    print(f"    Uniquement SQL DocPerm (pas dans can_read Frappe): {len(only_sql)}")
    if only_sql:
        for x in sorted(only_sql):
            print(f"      - {x}")

    print()
    print("  c) Ubiquité du rôle 'student' (tous DocTypes concernés via SQL):")
    all_list = sorted(sql_parents)
    print(f"    {len(all_list)} DocTypes avec read=1 pour 'student' via DocPerm SQL")
    for a in all_list:
        marker = " [FRAMEWORK]" if a in known_framework else ""
        print(f"    - {a}{marker}")

    print()
    print(SEP)
    print("FIN DU DUMP — Aucune modification effectuée en base.")
    print(SEP)


if __name__ == "__main__":
    frappe.set_user("Administrator")
    try:
        dump()
    except Exception:
        traceback.print_exc()
