"""Logique centralisee des niveaux d'etude (Field of study Level).

Source unique pour :
- l'ordre des niveaux d'une filiere (tableau reordonnable par drag & drop)
- la progression automatique (niveau suivant, respect des cycles)
- le calcul du niveau precedent (chargement des resultats)

Conventions :
- le champ `order` d'une ligne = sa position dans le tableau (renumerote a chaque
  sauvegarde par `Field of study.before_save`)
- la progression ne sort jamais du cycle (Licence -> Master est une admission
  de cycle, pas une progression automatique)
"""

import re

import frappe

CYCLES = ("Doctorat", "Licence", "Master", "BTS")


def cycle_niveau(level_label):
	"""Retourne le cycle d'un libelle de niveau (ex: 'Licence 3' -> 'Licence')."""
	if not level_label:
		return None
	for cycle in CYCLES:
		if level_label.startswith(cycle):
			return cycle
	match = re.match(r"([^\d]+)", level_label or "")
	return match.group(1).strip() if match else None


def _cycle(row):
	return row.get("cycle") or cycle_niveau(row.get("level"))


def lignes_filiere(filiere):
	"""Retourne les lignes de niveau d'une filiere, triees par order."""
	filiere_doc = frappe.get_doc("Field of study", filiere)
	return sorted(filiere_doc.field_of_study_level, key=lambda r: r.order or 0)


def prochain_niveau(filiere, niveau):
	"""Niveau suivant dans le meme cycle (None si fin de cycle).

	Exemple : Licence 2 -> Licence 3 ; Licence 3 -> None (admission Master
	decidee par le jury, pas automatique).
	"""
	rows = lignes_filiere(filiere)
	current = next((r for r in rows if r.level == niveau), None)
	if not current:
		return None
	cycle = _cycle(current)
	for row in rows:
		if row.order == current.order + 1 and _cycle(row) == cycle:
			return row.level
	return None


def niveau_precedent(filiere, niveau):
	"""Niveau dont les resultats conditionnent l'acces au niveau courant.

	- precedent dans le meme cycle : Licence 2 -> Licence 1, BTS 2 -> BTS 1
	- exception LMD : Master 1 -> dernier niveau Licence (Licence 3)
	- sinon None (debut de cycle)
	"""
	rows = lignes_filiere(filiere)
	current = next((r for r in rows if r.level == niveau), None)
	if not current:
		return None
	cycle = _cycle(current)
	precedents = [r for r in rows if _cycle(r) == cycle and r.order < current.order]
	if precedents:
		return max(precedents, key=lambda r: r.order).level
	if cycle == "Master":
		licences = [r for r in rows if _cycle(r) == "Licence"]
		if licences:
			return max(licences, key=lambda r: r.order).level
	return None
