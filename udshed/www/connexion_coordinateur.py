import frappe
from frappe import _
from frappe.auth import LoginManager


def get_context(context):
	context.title = "Connexion personnel"
	context.error = None
	context.email = ""

	if frappe.request.method != "POST":
		return context

	email = (frappe.form_dict.get("email") or "").strip()
	mot_de_passe = frappe.form_dict.get("mot_de_passe") or ""

	if not email or not mot_de_passe:
		context.error = _("Veuillez renseigner l'email et le mot de passe.")
		return context

	try:
		login_manager = LoginManager()
		login_manager.authenticate(user=email, pwd=mot_de_passe)
	except frappe.AuthenticationError:
		context.error = _("Identifiants incorrects.")
		return context

	if "Student" in frappe.get_roles(login_manager.user):
		context.error = _(
			"Cette page est réservée au personnel. Les étudiants se connectent avec leur matricule "
			"sur la page de connexion étudiant."
		)
		return context

	login_manager.post_login()
	frappe.db.commit()

	frappe.local.flags.redirect_location = "/app"
	raise frappe.Redirect
