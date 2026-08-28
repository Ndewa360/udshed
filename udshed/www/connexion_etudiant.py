import frappe
from frappe import _
from frappe.utils import getdate


def get_context(context):
	context.title = "Connexion étudiant"
	context.error = None
	context.matricule = ""

	if frappe.request.method != "POST":
		return context

	matricule = (frappe.form_dict.get("matricule") or "").strip()
	mot_de_passe = (frappe.form_dict.get("mot_de_passe") or "").strip()

	if not matricule or not mot_de_passe:
		context.error = _("Veuillez renseigner le matricule et le mot de passe.")
		return context

	try:
		student = _verifier_identifiants(matricule, mot_de_passe)
	except Exception:
		frappe.log_error(" connexion_etudiant _verifier_identifiants")
		context.error = _("Une erreur est survenue lors de la vérification. Réessayez.")
		return context

	if not student:
		context.error = _("Matricule ou mot de passe incorrect.")
		return context

	try:
		user_email = _assurer_compte_utilisateur(student)
		_login(user_email)
	except Exception:
		frappe.log_error(" connexion_etudiant _assurer_compte_utilisateur / _login")
		context.error = _("Une erreur est survenue lors de la connexion. Réessayez.")
		return context

	frappe.local.flags.redirect_location = "/desk"
	raise frappe.Redirect


def _verifier_identifiants(matricule, mot_de_passe):
	"""Vérifie le matricule + mot de passe (date de naissance en chiffres)."""
	if not frappe.db.exists("Student", matricule):
		return None

	student = frappe.get_doc("Student", matricule)
	if not student.birth_date:
		return None

	chiffres = "".join(c for c in mot_de_passe if c.isdigit())
	naissance = getdate(student.birth_date)
	mots_valides = {
		naissance.strftime("%d%m%Y"),
		naissance.strftime("%Y%m%d"),
	}

	if chiffres and chiffres in mots_valides:
		return student
	return None


def _assurer_compte_utilisateur(student):
	"""Retourne l'email du compte User lié, le crée s'il n'existe pas."""
	if student.utilisateur and frappe.db.exists("User", student.utilisateur):
		return student.utilisateur

	email = student.email or f"{student.name}@udshed.local"
	if not frappe.db.exists("User", email):
		user = frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": student.nom or "",
			"last_name": student.prenom or "",
			"send_welcome_email": 0,
			"roles": [{"role": "Student"}],
		})
		user.insert(ignore_permissions=True)

	frappe.db.set_value("Student", student.name, "utilisateur", email)
	return email


def _login(user_email):
	login_manager = frappe.auth.LoginManager()
	login_manager.login_as(user_email)
	frappe.db.commit()
