import frappe, json
import udshed.api.planning_calendar_pdf as planning_calendar_pdf

@frappe.whitelist()
def download_planning_pdf(filters):
    try:
        filters = json.loads(filters)
    except (json.JSONDecodeError, TypeError):
        frappe.throw("Filtres invalides.")
    try:
        pdf, planning_name, items, _, _ = planning_calendar_pdf.generate_planning_pdf(filters)
    except (frappe.ValidationError, frappe.PermissionError):
        # Erreur fonctionnelle déjà explicite : on ne la masque pas.
        raise
    except Exception as e:
        # On journalise le détail, mais on remonte la cause réelle à l'écran :
        # un message générique (« Erreur lors de la génération du PDF. »)
        # est impossible à diagnostiquer côté utilisateur.
        frappe.log_error(
            title="planning_pdf generate_planning_pdf",
            message=frappe.get_traceback(),
        )
        frappe.throw(
            "Erreur lors de la génération du PDF : {0}".format(frappe.utils.strip_html(str(e)) or e.__class__.__name__)
        )
    frappe.local.response.filename = planning_name
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "pdf"





