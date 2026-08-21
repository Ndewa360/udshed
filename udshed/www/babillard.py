# Copyright (c) 2026, Udshed and contributors
# For license information, please see license.txt

"""Page publique « Babillard des Notes » (/babillard).

Accessible sans connexion. Le formulaire (Niveau + Matricule + Année +
Semestre) appelle l'endpoint ``udshed.api.babillard.consulter_notes``.
"""

import frappe
from frappe import _


def _start_year(year_name):
	"""Année de début d'un nom d'Academic Year."""
	try:
		return int(str(year_name).split("-")[0])
	except (ValueError, IndexError):
		return 0


def get_context(context):
	"""Construit le contexte de la page publique."""
	context.title = _("Babillard des Notes")
	context.no_cache = 1

	context.school_name = frappe.db.get_single_value("Udshed Setting", "school_name") or ""
	context.school_logo = frappe.db.get_single_value("Udshed Setting", "school_logo") or ""

	# Niveaux disponibles (options du champ "level" de Field of study Level)
	options = frappe.get_meta("Field of study Level").get_field("level").options or ""
	context.niveaux = [n for n in options.split("\n") if n]

	# Filières et leurs niveaux (pour la consultation « par filière »)
	filieres = []
	for f in frappe.get_all("Field of study", fields=["name"], order_by="name"):
		doc = frappe.get_cached_doc("Field of study", f["name"])
		filieres.append({
			"name": f["name"],
			"name_of_field": doc.get("name_of_field") or f["name"],
			"niveaux": [row.level for row in (doc.get("field_of_study_level") or [])],
		})
	context.filieres = filieres

	# Années académiques triées de la plus récente à la plus ancienne
	years = frappe.get_all("Academic Year", fields=["name"])
	years.sort(key=lambda y: _start_year(y["name"]), reverse=True)
	context.academic_years = [y["name"] for y in years]

	# Année par défaut
	context.current_year = frappe.db.get_single_value("Udshed Setting", "current_year") or ""
	if not context.current_year:
		cy = frappe.db.get_value("Academic Year", {"is_current_year": 1}, "name")
		context.current_year = cy or (context.academic_years[0] if context.academic_years else "")

	# Pré-remplissage depuis l'URL (permet de partager un lien)
	context.niveau = frappe.form_dict.get("niveau") or ""
	context.matricule = frappe.form_dict.get("matricule") or ""
	context.academic_year = frappe.form_dict.get("academic_year") or context.current_year
	context.semestre = frappe.form_dict.get("semestre") or ""

	return context
