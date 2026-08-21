"""Logique centralisee des niveaux d'etude (Field of study Level).

Source unique pour :
- l'ordre des niveaux d'une filiere (tableau reordonnable par drag & drop)
- la progression automatique (niveau suivant, respect des cycles)
- le calcul du niveau precedent (chargement des resultats)

Conventions :
- le champ `order` d'une ligne = sa position dans le tableau (renumere a chaque
  sauvegarde par `Field of study.before_save`)
- la progression dans un meme cycle est automatique (L1->L2->L3, BTS1->BTS2)
- fin BTS 2 -> Licence 3 si elle existe (chemin vers le Master)
- fin Licence 3 -> None (admission Master = decision du jury)
"""

import re

import frappe

CYCLES = ("Doctorat", "Licence", "Master", "BTS")
CYCLE_ORDER = {"BTS": 1, "Licence": 2, "Master": 3, "Doctorat": 4}


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


def _level_rank(level_label):
	"""Extrait le rang numerique d'un libelle (ex: 'Licence 2' -> 2)."""
	if not level_label:
		return 0
	match = re.search(r"(\d+)", level_label)
	return int(match.group(1)) if match else 0


def lignes_filiere(filiere):
	"""Retourne les lignes de niveau d'une filiere, triees par ordre."""
	filiere_doc = frappe.get_doc("Field of study", filiere)
	return sorted(filiere_doc.field_of_study_level, key=lambda r: r.order or 0)


def prochain_niveau(filiere, niveau):
	"""Niveau suivant dans le parcours academique.

	Dans un meme cycle : progression automatique (L1->L2->L3, BTS1->BTS2).
	Fin de cycle BTS : retourne Licence 3 si elle existe (chemin vers Master).
	Fin de cycle Licence : retourne None (admission Master = decision du jury).
	"""
	rows = lignes_filiere(filiere)
	current = next((r for r in rows if r.level == niveau), None)
	if not current:
		return None
	cycle = _cycle(current)
	current_rank = _level_rank(current.level)

	for row in rows:
		if _cycle(row) == cycle and _level_rank(row.level) == current_rank + 1:
			return row.level

	if cycle == "BTS":
		licences_3 = [r for r in rows if _cycle(r) == "Licence" and _level_rank(r.level) == 3]
		if licences_3:
			return licences_3[0].level

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
	current_rank = _level_rank(current.level)

	if current_rank > 1:
		for row in rows:
			if _cycle(row) == cycle and _level_rank(row.level) == current_rank - 1:
				return row.level

	if cycle == "Master":
		licences = [r for r in rows if _cycle(r) == "Licence"]
		if licences:
			return max(licences, key=lambda r: r.order).level
	return None
