import frappe
from frappe import _

from udshed.api.inscription import get_inscription_report
from udshed.api.reregistration import get_reregistration_report


@frappe.whitelist()
def get_general_report(
	reinscription_session=None,
	filiere=None,
	candidature_status=None,
	statut=None,
):
	"""
	Rapport général combinant inscriptions (candidats) et réinscriptions.

	Args:
		reinscription_session: name/ID de la Session Reinscription (optionnel)
		filiere: name/ID de la Field of study (optionnel)
		candidature_status: statut de candidature (optionnel)
		statut: statut de réinscription (optionnel)

	Returns:
		dict: {inscriptions: {...}, reinscriptions: {...}}
	"""
	try:
		return {
			"inscriptions": get_inscription_report(
				filiere=filiere,
				candidature_status=candidature_status,
			),
			"reinscriptions": get_reregistration_report(
				reinscription_session=reinscription_session,
				filiere=filiere,
				statut=statut,
			),
		}
	except Exception:
		frappe.log_error(" general_report get_general_report")
		frappe.throw(_("Erreur lors de la génération du rapport général."))
