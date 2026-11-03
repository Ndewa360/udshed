import frappe

# Page servie à chaque requête : elle embarque le jeton CSRF de la session
# courante, qu'une page mise en cache rendrait périmé.
no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/connexion-etudiant"
		raise frappe.Redirect

	context.title = "Réinscription"
	context.no_cache = 1
	context.show_sidebar = False
