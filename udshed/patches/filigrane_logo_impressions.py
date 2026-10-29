import os

import frappe


def execute():
    """Ré-synchronise le corps HTML des impressions depuis les templates du
    dossier public/print_templates (ajout du logo en filigrane)."""
    for pf_name, template_name in [
        ("Releve Notes", "releve_notes.html"),
    ]:
        template_path = frappe.get_app_path(
            "udshed", "public", "print_templates", template_name
        )
        if not os.path.exists(template_path):
            continue

        with open(template_path, encoding="utf-8") as f:
            html = f.read()

        if frappe.db.exists("Print Format", pf_name):
            pf = frappe.get_doc("Print Format", pf_name)
        else:
            pf = frappe.new_doc("Print Format")
            pf.doc_type = "Student"
            pf.name = pf_name
            pf.print_format_name = pf_name
            pf.module = "Udshed"
            pf.standard = "Yes"
            pf.print_format_builder = 0
            pf.align = "Left"

        pf.html = html
        pf.flags.ignore_permissions = True
        pf.save()