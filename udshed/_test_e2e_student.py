import frappe

def exec():
	frappe.set_user("matricule.student@ndewa.edu")
	from frappe.website.utils import get_home_page
	hp = get_home_page()
	print("home_page:", hp)

	from frappe.desk.desktop import get_workspaces
	print("get_workspaces:", [(p.get("name")) for p in get_workspaces().get("pages", [])])

	# URL du workspace pour le desk
	from frappe.utils.data import get_url_to_workspace
	print("workspace url:", get_url_to_workspace("Inscription - Reinscription", True))

	# Le contenu du workspace pour l'étudiant (raccourcis/links)
	from json import dumps
	page = {"name": "Inscription - Reinscription"}
	from frappe.desk.desktop import Workspace, get_desktop_page
	data = get_desktop_page(dumps(page))
	print("shortcuts:", [(s.get("label")) for s in data.get("shortcuts", {}).get("items", [])])
	print("cards:", data.get("cards"))