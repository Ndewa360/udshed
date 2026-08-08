import frappe
from frappe import _
import os


def create_releve_notes_print_format():
    """Create the Relevé de Notes / Transcript Print Format if it doesn't exist."""

    if frappe.db.exists("Print Format", "Releve Notes"):
        return

    template_path = frappe.get_app_path(
        "udshed", "public", "print_templates", "releve_notes.html"
    )

    if os.path.exists(template_path):
        with open(template_path, "r") as f:
            html = f.read()
    else:
        html = "<p>Template not found</p>"

    pf = frappe.new_doc("Print Format")
    pf.doc_type = "Student"
    pf.name = "Releve Notes"
    pf.print_format_name = "Releve Notes"
    pf.module = "Udshed"
    pf.standard = "Yes"
    pf.print_format_builder = 0
    pf.align = "Left"
    pf.css = ""
    pf.html = html
    pf.insert(ignore_permissions=True)

    frappe.db.commit()
    return pf.name


def after_install():
    """Called by hooks.after_install to set up initial data."""
    create_releve_notes_print_format()
