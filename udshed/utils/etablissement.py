"""Identité de l'établissement configuré (Udshed Setting).

Une seule fonction pour toutes les pages publiques, les emails et les PDF :
nom, institut, coordonnées et logo. Rien n'est écrit en dur dans les gabarits.
"""

import frappe

APP = "Udshed"


def _url_logo(valeur):
	"""URL absolue et publique du logo. Un logo en fichier privé n'est pas
	lisible par les messageries ni par les visiteurs : on se replie alors sur
	l'URL d'un asset public de l'app."""
	valeur = (valeur or "").strip()
	if not valeur:
		return frappe.utils.get_url("/assets/udshed/images/logo1.png")
	if valeur.startswith(("http://", "https://")):
		return valeur
	if valeur.startswith("/private/"):
		return frappe.utils.get_url("/assets/udshed/images/logo1.png")
	return frappe.utils.get_url(valeur)


def etablissement():
	"""Dictionnaire de l'établissement, prêt pour Jinja et JSON."""
	try:
		s = frappe.get_cached_doc("Udshed Setting")
	except Exception:
		s = frappe._dict()
	nom = (s.get("school_name") or "").strip() or APP
	site = (s.get("school_website") or "").strip()
	if site and not site.startswith(("http://", "https://")):
		site = "https://" + site
	return frappe._dict({
		"nom": nom,
		"institut": (s.get("school_institute") or "").strip(),
		"adresse": (s.get("school_address") or "").strip(),
		"telephone": (s.get("school_phone") or "").strip(),
		"email": (s.get("school_email") or "").strip(),
		"site": site,
		"logo": _url_logo(s.get("school_logo")),
		"expediteur": (s.get("email_candidature_sender_name") or "").strip() or nom,
		"app": APP,
	})


def nom_etudiant(student):
	"""« Nom Prénom » d'un étudiant (le nom complet n'est pas stocké)."""
	row = frappe.db.get_value("Student", student, ["nom", "prenom"], as_dict=True)
	if not row:
		return student
	return " ".join(x for x in [row.nom, row.prenom] if x) or student
