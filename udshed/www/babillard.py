# Copyright (c) 2026, Udshed and contributors
# For license information, please see license.txt

"""Page publique « Babillard des résultats » (/babillard).

Consultation par critères : année → classe (filière + niveau) → semestre (ou
toute l'année), avec recherche par matricule ou nom. Affiche, pour toute la
classe, les notes PUBLIÉES par matière, la moyenne, les crédits et la
décision (choix de l'établissement : babillard public détaillé).
API : udshed.api.babillard.options_babillard et resultats_classe.

Compatibilité : /babillard?academic_year=…&niveau=…&matricule=… (liens des
emails de publication) présélectionne l'année, la classe et l'étudiant.
"""

import frappe

no_cache = 1


def get_context(context):
	context.title = "Babillard des résultats"
	context.no_cache = 1
	context.prefill = {
		"academic_year": frappe.form_dict.get("academic_year") or "",
		"niveau": frappe.form_dict.get("niveau") or "",
		"filiere": frappe.form_dict.get("filiere") or "",
		"matricule": frappe.form_dict.get("matricule") or "",
	}
	return context
