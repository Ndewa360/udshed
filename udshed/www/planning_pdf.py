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
    except Exception:
        frappe.log_error(" planning_pdf generate_planning_pdf")
        frappe.throw("Erreur lors de la génération du PDF.")
    frappe.local.response.filename = planning_name
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "pdf"





