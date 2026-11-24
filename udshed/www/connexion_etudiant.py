import frappe
from frappe import _
from frappe.utils import getdate

from udshed.utils import securite

_MAX_ECHECS_MATRICULE = 5
_MAX_ECHECS_IP = 50
_FENETRE_SEC = 15 * 60


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

	context.matricule = matricule

	# Le mot de passe (date de naissance) a peu de valeurs possibles et les
	# matricules sont connus (babillard) : on limite les échecs par matricule
	# et par adresse IP (seuil IP large : un campus partage souvent une IP).
	ip = securite.ip_client()
	try:
		securite.verifier_tentatives("connexion-matricule", matricule, _MAX_ECHECS_MATRICULE, _FENETRE_SEC)
		securite.verifier_tentatives("connexion-ip", ip, _MAX_ECHECS_IP, _FENETRE_SEC)
	except frappe.RateLimitExceededError:
		frappe.clear_messages()
		context.error = _("Trop de tentatives infructueuses. Réessayez dans {0} minutes.").format(
			_FENETRE_SEC // 60
		)
		return context

	student = _verifier_identifiants(matricule, mot_de_passe)
	if not student:
		securite.enregistrer_echec("connexion-matricule", matricule, _FENETRE_SEC)
		securite.enregistrer_echec("connexion-ip", ip, _FENETRE_SEC)
		context.error = _("Matricule ou mot de passe incorrect.")
		return context

	securite.reinitialiser_tentatives("connexion-matricule", matricule)
	user_email = _assurer_compte_utilisateur(student)
	_login(user_email)

	frappe.local.flags.redirect_location = "/dashboard-etudiant"
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
