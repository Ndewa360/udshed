"""Petites lectures de référentiel pour les écrans, sans exiger la lecture du DocType.

Un enseignant n'a que la sélection sur les référentiels (Filière, Année…) et aucun accès aux
réglages : ces écrans passent donc par ici plutôt que par frappe.db.get_value.
"""

import frappe


@frappe.whitelist()
def annee_courante():
	return frappe.db.get_single_value("Udshed Setting", "current_year")


@frappe.whitelist()
def libelle_filiere(filiere):
	return frappe.db.get_value("Field of study", filiere, "name_of_field") or filiere
