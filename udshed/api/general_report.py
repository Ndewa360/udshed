import frappe
from frappe import _

from udshed.api.inscription import get_inscription_report


@frappe.whitelist()
def get_general_report(
	filiere=None,
	candidature_status=None,
):
	"""
	Rapport général des inscriptions (candidats).

	Args:
		filiere: name/ID de la Field of study (optionnel)
		candidature_status: statut de candidature (optionnel)

	Returns:
		dict: {inscriptions: {...}}
	"""
	try:
		return {
			"inscriptions": get_inscription_report(
				filiere=filiere,
				candidature_status=candidature_status,
			),
		}
	except Exception:
		frappe.log_error(" general_report get_general_report")
		frappe.throw(_("Erreur lors de la génération du rapport général."))
