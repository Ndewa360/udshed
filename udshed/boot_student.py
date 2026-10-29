import json

import frappe

STUDENT_ROLE = "student"
STUDENT_WORKSPACE = "Inscription - Reinscription"
STUDENT_SIDEBAR = STUDENT_WORKSPACE.lower()


def configure_student_desk(bootinfo):
	"""Restreint le desk de l'étudiant : seul le workspace
	« Inscription - Reinscription » avec le raccourci « Se réinscrire »
	est visible. Sidebar, framework Frappe, autres workspaces retirés.
	"""
	user = frappe.session.user
	if user == "Administrator" or user == "Guest":
		return
	if "System Manager" in frappe.get_roles(user):
		return
	if STUDENT_ROLE not in frappe.get_roles(user):
		return

	# Sidebar: garder le format framework {"workspace": {"label":..., "items":[...]}}.
	# Seul "Se réinscrire" (Page link) est laissé à l'étudiant.
	sidebar = bootinfo.workspace_sidebar_item.get(STUDENT_SIDEBAR)
	if not isinstance(sidebar, dict) or "items" not in sidebar:
		sidebar = {"label": STUDENT_WORKSPACE, "items": [], "app": "udshed"}
	sidebar["items"] = [
		{
			"label": "Se réinscrire",
			"link_to": "reinscription_etudiant",
			"link_type": "Page",
			"type": "Link",
			"icon": "user-plus",
			"child": 0,
			"collapsible": 0,
			"indent": 0,
			"keep_closed": 0,
			"url": None,
			"show_arrow": 0,
			"filters": None,
			"route_options": None,
			"tab": None,
			"open_in_new_tab": 0,
		}
	]
	bootinfo.workspace_sidebar_item = {STUDENT_SIDEBAR: sidebar}

	# Ne pas supprimer app_data / module_wise_workspaces : le framework y accède
	# (ex. frappe.boot.app_data['Udshed']) et lève TypeError si absent.

	# Les icônes du desktop sont lues depuis boot.desktop_icons (pas desktop_icons_by_type).
	# L'étudiant ne garde que le workspace « Inscription - Reinscription ».
	bootinfo.desktop_icons = [
		icon for icon in bootinfo.desktop_icons
		if icon.get("name") == STUDENT_WORKSPACE or icon.get("label") == STUDENT_WORKSPACE
	]

	# Contenu du workspace : ne garder que le bloc raccourci « Se réinscrire ».
	# (Les blocs staff — Session Inscription, Candidats, Gestion des Niveaux… — n'existent
	# pas dans shortcuts.items de l'étudiant, sinon la zone s'affiche vide.)
	student_content = json.dumps(
		[
			{
				"id": "stu-h1",
				"type": "header",
				"data": {"text": "Inscription et Reinscription", "col": 12},
			},
			{
				"id": "stu-p1",
				"type": "paragraph",
				"data": {"text": "Cliquez sur le bouton ci-dessous pour vous réinscrire.", "col": 12},
			},
			{
				"id": "stu-sc1",
				"type": "shortcut",
				"data": {"shortcut_name": "Se réinscrire", "col": 12},
			},
		]
	)
	for page in (bootinfo.workspaces or {}).get("pages", []):
		if page.get("name") == STUDENT_WORKSPACE:
			page["content"] = student_content