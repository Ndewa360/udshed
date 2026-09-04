import frappe
from frappe import _


def get_context(context):
    context.title = "Gestion des niveaux"

    # Vérifier les permissions
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login"
        raise frappe.Redirect

    context.levels_data = _get_levels_data()
    context.faculties = frappe.get_all("Faculty", fields=["name", "faculty_name"])


def _get_levels_data():
    """Récupère toutes les filières avec leurs niveaux."""
    filieres = frappe.get_all("Field of study", fields=["name", "name_of_field", "faculte"])
    result = []

    for fos in filieres:
        doc = frappe.get_doc("Field of study", fos.name)
        levels = sorted(doc.field_of_study_level, key=lambda x: x.order or 0)
        result.append({
            "name": fos.name,
            "label": fos.name_of_field,
            "faculte": fos.faculte,
            "levels": [
                {
                    "name": l.name,
                    "level": l.level,
                    "cycle": l.cycle,
                    "order": l.order,
                }
                for l in levels
            ]
        })

    return result
