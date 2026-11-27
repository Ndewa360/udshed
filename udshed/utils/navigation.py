"""Navigation du desk (Frappe 16.6x) : barres latérales par public et audit.

Depuis Frappe 16.6x, une barre latérale (DocType « Sidebar », livrée dans
udshed/udshed/sidebar/) n'a pas de table de rôles : chaque entrée n'est montrée
que si l'utilisateur peut l'ouvrir (lecture du DocType, rôles de la page ou du
rapport) et une barre sans entrée autorisée disparaît. La structure par rôle
repose donc sur les permissions ; `matrice_visibilite()` les vérifie.
"""

import frappe

BARRES = ["Admissions et scolarité", "Examens et notes", "Planning académique", "Insight", "Configuration",
		  "Mon espace étudiant", "Partenariats enseignants", "Mon espace enseignant", "Accueil", "Ma faculté", "Direction académique"]

ROLES_UDSHED = ["System Manager", "Registration Manager", "Agent de scolarité", "Coordonateur", "Responsable Diplomation",
				"Comptable", "Planning Manager", "Teacher", "Correcteur", "Student",
				"Responsable des partenariats", "Doyen", "Vice-Doyen", "Directeur des Affaires Académiques"]


def visibilite(user, toutes=False):
	"""{barre: [entrées visibles]} pour un utilisateur, tel que le boot du desk les lui envoie.

	Par défaut, seules les barres d'Udshed ; `toutes=True` ajoute celles des autres modules
	(Frappe, apps installées) pour repérer ce qu'un rôle voit en dehors d'Udshed.
	"""
	from frappe.boot import get_module_sidebars

	precedent = frappe.session.user
	frappe.set_user(user)
	# Les droits et pages autorisées sont mis en cache pour la requête : on repart à zéro par utilisateur.
	if getattr(frappe.local, "request_cache", None) is not None:
		frappe.local.request_cache.clear()
	try:
		res = {}
		for barre, entree in get_module_sidebars().items():
			if toutes or barre in BARRES:
				res[barre] = [i.get("label") for i in entree.get("items", []) if i.get("type") == "Link"]
		return res
	finally:
		frappe.set_user(precedent)


def matrice_visibilite(toutes=False):
	"""Barres et entrées visibles pour un utilisateur de chaque rôle (créé puis annulé)."""
	matrice = {}
	frappe.db.savepoint("udshed_audit_nav")
	try:
		for i, role in enumerate(ROLES_UDSHED):
			email = f"audit-role-{i}@udshed.invalid"
			if not frappe.db.exists("User", email):
				user = frappe.get_doc({"doctype": "User", "email": email, "first_name": f"Audit {role}",
									   "send_welcome_email": 0, "roles": [{"role": role}]})
				user.flags.no_welcome_mail = True
				user.insert(ignore_permissions=True)
			matrice[role] = visibilite(email, toutes)
	finally:
		frappe.db.rollback(save_point="udshed_audit_nav")
	return matrice


def afficher_matrice(toutes=False):
	"""bench --site <site> execute udshed.utils.navigation.afficher_matrice [--kwargs "{'toutes': 1}"]"""
	for role, barres in matrice_visibilite(toutes).items():
		print(f"\n## {role}")
		for barre, entrees in barres.items():
			print(f"  {barre}: {', '.join(entrees)}")
