import frappe
from frappe.utils import getdate, nowdate


def daily():
	"""Daily scheduled task to update session statuses based on dates."""
	update_session_statuses()


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