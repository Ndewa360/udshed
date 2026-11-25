import frappe


def get_context(context):
	"""Espace candidat unique : suivi du dossier, résultat, convocation,
	confirmation de la place ou renoncement, accès à l'inscription."""
	context.title = "Mon dossier"
	context.no_cache = 1
