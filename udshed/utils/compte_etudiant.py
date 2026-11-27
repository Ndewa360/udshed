"""Compte Frappe d'un étudiant : une seule authentification (/login).

- identifiant : le MATRICULE (nom d'utilisateur Frappe), ou l'email ;
- mot de passe : choisi par l'étudiant via le lien d'activation envoyé avec
  son matricule (« Mot de passe oublié » de Frappe ensuite) ;
- rôle « Student » : ses droits ne lui ouvrent que la barre « Mon espace étudiant »
  (ses données passent par udshed.api.etudiant / actes / requetes).
La connexion par nom d'utilisateur est activée dans System Settings
(allow_login_using_user_name) par l'installation et le patch de migration.
"""

import frappe

ROLE = "Student"


def activer_connexion_par_matricule():
	if not frappe.db.get_single_value("System Settings", "allow_login_using_user_name"):
		frappe.db.set_single_value("System Settings", "allow_login_using_user_name", 1)


def _username_libre(username, user):
	autre = frappe.db.get_value("User", {"username": username}, "name")
	return not autre or autre == user


def assurer_compte(student):
	"""Crée ou complète le compte de l'étudiant (nom ou document Student).
	Retourne le nom du User."""
	if isinstance(student, str):
		student = frappe.get_doc("Student", student)
	email = (student.email or "").strip() or f"{student.name}@etudiant.invalid"
	matricule = (student.matricule or student.name or "").strip()

	user_name = student.get("utilisateur") if student.get("utilisateur") and frappe.db.exists(
		"User", student.get("utilisateur")) else (email if frappe.db.exists("User", email) else None)

	if not user_name:
		user = frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": student.nom or matricule,
			"last_name": student.prenom or "",
			"send_welcome_email": 0,
			"user_type": "System User",
			"roles": [{"role": ROLE}],
		})
		if matricule and _username_libre(matricule, None):
			user.username = matricule
		user.flags.no_welcome_mail = True
		user.insert(ignore_permissions=True)
		user_name = user.name
	else:
		user = frappe.get_doc("User", user_name)
		if ROLE not in [r.role for r in user.roles]:
			user.add_roles(ROLE)
		if matricule and user.username != matricule and _username_libre(matricule, user_name):
			frappe.db.set_value("User", user_name, "username", matricule)

	if student.get("utilisateur") != user_name:
		frappe.db.set_value("Student", student.name, "utilisateur", user_name)
	return user_name


def notifier_etudiant(user, sujet, message=None, code=None, reference=None, **options):
	"""Alerte de l'étudiant, ouvrant son espace (et non un formulaire du personnel).

	Avec `code`, passe par le moteur de notifications (canaux de la règle : application,
	e-mail, SMS) ; sans, simple alerte dans l'application."""
	if not user or user in ("Administrator", "Guest") or not frappe.db.get_value("User", user, "enabled"):
		return
	if code:
		from udshed.notifications import emettre

		emettre(code, [user], sujet, message, lien="/app/mon-espace-etudiant", reference=reference, **options)
		return
	frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert", "subject": sujet,
					"email_content": message, "link": "/app/mon-espace-etudiant"}).insert(ignore_permissions=True)


def lien_activation(user_name):
	"""Lien « choisir mon mot de passe » (clé à usage unique de Frappe)."""
	if not user_name or not frappe.db.exists("User", user_name):
		return ""
	user = frappe.get_doc("User", user_name)
	# Frappe 16.6x a renommé User.reset_password en _reset_password (même contrat : renvoie le lien).
	reinit = getattr(user, "reset_password", None) or user._reset_password
	return reinit(send_email=False)
