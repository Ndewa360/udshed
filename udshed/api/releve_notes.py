# Copyright (c) 2026, Udshed and contributors
# For license information, please see license.txt

"""API de la page « Relevé de notes »."""

import frappe


@frappe.whitelist()
def search_students(doctype, txt, searchfield, start, page_len, filters=None):
	"""Recherche d'étudiants pour le champ Link de la page Relevé de notes.

	Cherche par nom du document (STU-####), matricule, nom ou prénom.
	"""
	txt = (txt or "").strip()
	or_filters = None
	if txt:
		like = f"%{txt}%"
		or_filters = [
			["name", "like", like],
			["matricule", "like", like],
			["nom", "like", like],
			["prenom", "like", like],
		]

	students = frappe.get_all(
		"Student",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "matricule", "nom", "prenom"],
		order_by="matricule asc",
		limit_start=start,
		limit_page_length=page_len,
	)

	out = []
	for s in students:
		label = " ".join(x for x in [s.matricule, s.nom, s.prenom] if x) or s.name
		out.append([s.name, label])
	return out
