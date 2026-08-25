# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Remplace la grille des grades par la grille officielle UDSHED.

Source unique de vérité : Udshed Setting › grille_grades (lignes « Grade Config »).
La définition canonique de la grille vit dans ``udshed.grade_calculation``.
Le patch est idempotent : si la grille courante correspond déjà à la grille
officielle (mêmes grades et mêmes bornes /20), il ne fait rien.
"""

import frappe

from udshed.grade_calculation import GRILLE_OFFICIELLE


def execute():
	setting = frappe.get_single("Udshed Setting")

	actuelle = {
		(r.grade, round(float(r.note_min_20 or 0), 2)) for r in setting.get("grille_grades") or []
	}
	attendue = {(g[4], g[0]) for g in GRILLE_OFFICIELLE}
	if actuelle == attendue:
		return

	setting.set("grille_grades", [])
	for note_min_20, note_max_20, note_min_pct, note_max_pct, grade, point, mention in GRILLE_OFFICIELLE:
		capitalise = note_min_20 >= 10.0
		setting.append("grille_grades", {
			"note_min_20": note_min_20,
			"note_max_20": note_max_20,
			"note_min_100": note_min_pct,
			"note_max_100": note_max_pct,
			"grade": grade,
			"point": point,
			"mention": mention,
			"type_resultat": (
				"Crédits capitalisés et transférables"
				if capitalise
				else "Non capitalisé"
			),
			# Anciens champs (%) conservés pour compatibilité
			"note_min": note_min_pct,
			"note_max": note_max_pct,
		})

	setting.flags.ignore_permissions = True
	setting.save()
	frappe.db.commit()
