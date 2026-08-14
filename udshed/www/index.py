import frappe


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/connexion-etudiant"
        raise frappe.Redirect

    if "Student" in frappe.get_roles():
        frappe.local.flags.redirect_location = "/reinscription-etudiant"
        raise frappe.Redirect

    frappe.local.flags.redirect_location = "/desk"
    raise frappe.Redirect
