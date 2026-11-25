import frappe

no_cache = 1


def get_context(context):
	"""Vérification publique d'un acte académique (lien du QR code)."""
	from udshed.api.actes import verifier

	context.title = "Vérification d'un document"
	context.no_cache = 1
	context.code = (frappe.form_dict.get("code") or "").strip().upper()
	context.resultat = None
	if context.code:
		try:
			context.resultat = verifier(context.code)
		except frappe.RateLimitExceededError:
			frappe.clear_messages()
			context.resultat = {"valide": False, "trop": True}
