import frappe


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login"
        raise frappe.Redirect
    else:
        frappe.local.flags.redirect_location = "/desk"
        raise frappe.Redirect
