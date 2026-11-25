"""Desk d'un compte étudiant : uniquement « Mon espace étudiant ».

L'étudiant se connecte par /login (matricule ou email). Son desk ne montre
que son espace (grille, planning, résultats, réinscription en lecture seule
de ses propres données, voir udshed/api/etudiant.py) : les autres espaces,
icônes et barres latérales sont retirés du boot. Le personnel n'est pas
concerné.
"""

import frappe

STUDENT_ROLE = "Student"
STUDENT_WORKSPACE = "Mon espace étudiant"
STUDENT_SIDEBAR = STUDENT_WORKSPACE.lower()


def configure_student_desk(bootinfo):
	from udshed.utils.securite import est_personnel

	user = frappe.session.user
	if user in ("Administrator", "Guest"):
		return
	if STUDENT_ROLE not in frappe.get_roles(user) or est_personnel(user):
		return

	# Le boot ne doit jamais échouer à cause de cette personnalisation :
	# en cas d'imprévu, on journalise et on laisse le desk par défaut.
	try:
		_restreindre_desk(bootinfo)
	except Exception:
		frappe.log_error(title="udshed: configure_student_desk")


def _restreindre_desk(bootinfo):
	barres = bootinfo.get("workspace_sidebar_item") or {}
	if STUDENT_SIDEBAR in barres:
		bootinfo.workspace_sidebar_item = {STUDENT_SIDEBAR: barres[STUDENT_SIDEBAR]}

	# Ne pas supprimer app_data / module_wise_workspaces : le framework y accède
	# (ex. frappe.boot.app_data['Udshed']) et lève TypeError si absent.
	bootinfo.desktop_icons = [
		icon for icon in (bootinfo.get("desktop_icons") or [])
		if STUDENT_WORKSPACE in (icon.get("name"), icon.get("label"))
	]
	bootinfo.home_page = "mon-espace-etudiant"
