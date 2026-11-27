import frappe
from frappe.utils import getdate, nowdate


def daily():
	"""Daily scheduled task to update session statuses based on dates."""
	update_session_statuses()
	update_reinscription_session_statuses()
	relancer_admissions()
	rappeler_saisie_notes()


def rappeler_saisie_notes():
	"""Rappel aux enseignants dont la saisie n'est pas confirmée, 3 jours avant la date limite."""
	try:
		from udshed.utils.periode_saisie import rappel_saisie

		rappel_saisie()
	except Exception:
		frappe.log_error(title="udshed: rappel de saisie des notes")


def relancer_admissions():
	"""Concours : relance les admis qui n'ont pas finalisé et libère les places
	expirées au profit de la liste d'attente (udshed/api/concours_finalisation.py).

	Déplacé depuis udshed/tasks.py, que le hook « daily » n'appelait pas :
	la tâche n'aurait jamais tourné.
	"""
	try:
		from udshed.api.concours_finalisation import relancer_et_liberer

		relancer_et_liberer()
	except Exception:
		frappe.log_error(title="Tâche quotidienne : relance / libération des admissions")


def update_reinscription_session_statuses():
	"""Ouvre / ferme les Session Reinscription selon leurs dates."""
	from udshed.udshed.doctype.session_reinscription.session_reinscription import mettre_a_jour_statuts

	mettre_a_jour_statuts()


def update_session_statuses():
	"""
	Automatically update session inscription statuses:
	- Draft -> Open when opening_date arrives
	- Open -> Closed when closing_date passes
	"""
	today = getdate(nowdate())

	# Open sessions where opening_date has arrived
	draft_sessions = frappe.get_all(
		"Session Inscription",
		filters={
			"status": "Draft",
			"opening_date": ["<=", today]
		},
		pluck="name"
	)

	for session_name in draft_sessions:
		try:
			session = frappe.get_doc("Session Inscription", session_name)
			# Check if another session is already open
			existing_open = frappe.db.exists("Session Inscription", {"status": "Open"})
			if existing_open and existing_open != session_name:
				frappe.log_error(
					f"Cannot open session {session_name}: another session ({existing_open}) is already open",
					"Session Inscription Auto-Open"
				)
				continue

			session.status = "Open"
			session.save(ignore_permissions=True)
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(
				f"Failed to open session {session_name}: {str(e)}",
				"Session Inscription Auto-Open"
			)

	# Close sessions where closing_date has passed
	open_sessions = frappe.get_all(
		"Session Inscription",
		filters={
			"status": "Open",
			"closing_date": ["<", today]
		},
		pluck="name"
	)

	for session_name in open_sessions:
		try:
			session = frappe.get_doc("Session Inscription", session_name)
			session.status = "Closed"
			session.save(ignore_permissions=True)
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(
				f"Failed to close session {session_name}: {str(e)}",
				"Session Inscription Auto-Close"
			)