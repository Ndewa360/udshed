import frappe


def daily():
	try:
		from udshed.api.concours_finalisation import relancer_et_liberer

		relancer_et_liberer()
	except Exception:
		frappe.log_error(title="Tâche quotidienne : relance / libération des admissions")
