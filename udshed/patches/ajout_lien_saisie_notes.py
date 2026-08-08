import frappe


def execute():
    if not frappe.db.exists("Workspace", "Gestion des Notes"):
        return

    exists = frappe.db.exists(
        "Workspace Link",
        {"parent": "Gestion des Notes", "link_type": "Page", "link_to": "saisie_notes"},
    )
    if exists:
        return

    ws = frappe.get_doc("Workspace", "Gestion des Notes")
    ws.flags.ignore_permissions = True
    ws.flags.ignore_links = True
    for d in ws.get("links"):
        if d.link_type and d.type not in ("Link", "Card Break"):
            d.type = "Link"
    ws.append(
        "links",
        {
            "type": "Link",
            "label": "Saisie des notes",
            "link_type": "Page",
            "link_to": "saisie_notes",
        },
    )
    ws.save()
