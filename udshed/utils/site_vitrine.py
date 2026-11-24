"""Contexte commun des pages du site vitrine Udshed (/udshed et pages légales)."""

import frappe


def contexte(context, chemin, titre, description):
	context.title = titre
	context.description = description
	context.canonical_url = frappe.utils.get_url(chemin)
	context.og_image = frappe.utils.get_url("/assets/udshed/images/logo1.png")
	context.body_class = "uds-site"
	context.no_cache = 0
	context.sitemap = 1  # pages listées dans /sitemap.xml
	return context
