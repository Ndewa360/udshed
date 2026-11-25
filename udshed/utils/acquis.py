"""Acquis LMD d'un étudiant : unités validées, crédits, dettes, équivalences.

Règles (validées avec l'établissement) :
  - La validation se fait par UNITÉ (Teaching Unit Value) : moyenne des
	matières pondérée par les crédits ≥ seuil du cycle → l'unité est acquise
	avec toutes ses matières (compensation entre matières de l'unité).
	Une matière qui n'appartient à aucune unité forme une unité à elle seule.
  - Une unité non validée est une dette : l'étudiant reprend TOUTE l'unité.
  - Les acquis se cumulent d'une année à l'autre : une matière déjà acquise
	(dans une unité validée) l'est aussi dans la grille d'une autre année via
	son équivalent — même cours (Course) dans la même filière, ou équivalence
	déclarée (DocType « Equivalence UE ») quand la grille change.
  - Le jury (udshed/utils/deliberation.py) peut valider une unité.
"""

import frappe
from frappe.utils import flt

from udshed.utils.deliberation import ajuster_validation


# ---------------------------------------------------------------------- #
#  Grille : unités d'un niveau
# ---------------------------------------------------------------------- #
def _niveau_id(filiere, niveau):
	if not niveau:
		return None
	if frappe.db.exists("Field of study Level", niveau):
		return niveau
	return frappe.db.get_value("Field of study Level", {"parent": filiere, "level": niveau}, "name")


def unites_du_niveau(filiere, niveau, academic_year):
	"""Unités de la classe pour l'année, chacune avec ses matières et crédits."""
	from udshed.api.reregistration import _credit_from_grid, _teaching_units_niveau_year

	niveau_id = _niveau_id(filiere, niveau)
	if not niveau_id:
		return []
	unites = {}
	for tu in _teaching_units_niveau_year(filiere, niveau_id, academic_year):
		info = frappe.db.get_value("Teaching Unit", tu, ["unite_de_valeur", "semestre", "intitule_cours", "course"],
								   as_dict=True) or frappe._dict()
		cle = info.unite_de_valeur or f"TU:{tu}"
		u = unites.setdefault(cle, {
			"cle": cle, "unite": info.unite_de_valeur, "semestre": info.semestre or "",
			"intitule": (frappe.db.get_value("Teaching Unit Value", info.unite_de_valeur, "intitule")
						 if info.unite_de_valeur else info.intitule_cours) or tu,
			"matieres": [], "credits": 0.0,
		})
		credits = flt(_credit_from_grid(filiere, niveau_id, tu))
		u["matieres"].append({"teaching_unit": tu, "credits": credits, "semestre": info.semestre or "",
							  "intitule": info.intitule_cours or tu, "course": info.course})
		u["credits"] += credits
		if not u["semestre"]:
			u["semestre"] = info.semestre or ""
	return list(unites.values())


# ---------------------------------------------------------------------- #
#  Équivalences entre grilles
# ---------------------------------------------------------------------- #
def _filieres_de(tu):
	return set(frappe.get_all("Course Field of study level item", filters={"parent": tu}, pluck="filiere"))


def equivalents(tu):
	"""Matières équivalentes à `tu` (toutes années) : même cours dans une filière
	commune, plus les équivalences déclarées dans les deux sens."""
	if not tu:
		return set()
	res = set()
	course = frappe.db.get_value("Teaching Unit", tu, "course")
	filieres = _filieres_de(tu)
	if course and filieres:
		for autre in frappe.get_all("Teaching Unit", filters={"course": course, "name": ["!=", tu]}, pluck="name"):
			if _filieres_de(autre) & filieres:
				res.add(autre)
	for row in frappe.get_all("Equivalence UE", filters={"ancienne_matiere": tu}, pluck="nouvelle_matiere"):
		res.add(row)
	for row in frappe.get_all("Equivalence UE", filters={"nouvelle_matiere": tu}, pluck="ancienne_matiere"):
		res.add(row)
	return res


def equivalent_annee(tu, academic_year, filiere, niveau=None):
	"""Matière de l'année `academic_year` équivalente à `tu` (dette reportée sur la
	nouvelle grille), ou None si la grille ne la propose plus."""
	if frappe.db.get_value("Teaching Unit", tu, "academic_year") == academic_year:
		return tu
	declarees = frappe.get_all("Equivalence UE", filters={"ancienne_matiere": tu, "annee_cible": academic_year},
							   pluck="nouvelle_matiere")
	if declarees:
		return declarees[0]
	course = frappe.db.get_value("Teaching Unit", tu, "course")
	if not course:
		return None
	niveau_id = _niveau_id(filiere, niveau) if niveau else None
	candidats = []
	for autre in frappe.get_all("Teaching Unit", filters={"course": course, "academic_year": academic_year}, pluck="name"):
		lignes = frappe.get_all("Course Field of study level item", filters={"parent": autre, "filiere": filiere},
								pluck="niveau")
		if lignes:
			candidats.append((0 if niveau_id in lignes else 1, autre))
	return sorted(candidats)[0][1] if candidats else None


# ---------------------------------------------------------------------- #
#  Validation d'une unité
# ---------------------------------------------------------------------- #
def _seuil(student):
	from udshed.grade_calculation import get_seuil_validation, get_student_cycle

	return get_seuil_validation(get_student_cycle(student))


def _matiere_seule(student, tu, academic_year, filiere, niveau_id):
	"""Matière hors unité : son résultat académique, ajusté par le jury."""
	r = frappe.db.get_value("Resultat Academique", {"student": student, "teaching_unit": tu,
													"academic_year": academic_year},
							["note_finale", "note_pct", "statut"], as_dict=True, order_by="modified desc")
	if not r:
		return {"valide": False, "par_jury": False, "note_20": None}
	note_pct = r.note_pct if r.note_pct else (flt(r.note_finale) * 5 if r.note_finale is not None else None)
	if r.statut == "Validé":
		return {"valide": True, "par_jury": False, "note_20": flt(r.note_finale)}
	adj = ajuster_validation(student, note_pct, _seuil(student), academic_year, filiere, niveau_id, matiere=tu)
	return {"valide": adj["valide"], "par_jury": adj["par_jury"], "note_20": flt(r.note_finale)}


def matieres_acquises(student, sauf_annee=None):
	"""Matières acquises par l'étudiant dans les unités validées (résultats
	enregistrés), toutes années sauf `sauf_annee`."""
	acquises = set()
	filtres = {"student": student, "statut": "Validé"}
	for r in frappe.get_all("Resultat UE", filters=filtres, fields=["teaching_unit_value", "academic_year", "name"]):
		if sauf_annee and r.academic_year == sauf_annee:
			continue
		acquises.update(frappe.get_all("Resultat UE Matiere", filters={"parent": r.name}, pluck="teaching_unit"))
	for r in frappe.get_all("Resultat Academique", filters=filtres, fields=["teaching_unit", "academic_year"]):
		if sauf_annee and r.academic_year == sauf_annee:
			continue
		if r.teaching_unit and not frappe.db.get_value("Teaching Unit", r.teaching_unit, "unite_de_valeur"):
			acquises.add(r.teaching_unit)
	return acquises


def est_acquise(tu, acquises):
	return tu in acquises or bool(equivalents(tu) & acquises)


def statut_unite(student, unite, academic_year, filiere, niveau, acquises=None):
	"""(validée, source) d'une unité pour un étudiant : « note », « jury »,
	« acquis » (antérieur, via équivalences) ou « » si non validée."""
	from udshed.api.resultat_ue import calculer_ue_etudiant

	niveau_id = _niveau_id(filiere, niveau)
	if unite["unite"]:
		r = calculer_ue_etudiant(student, unite["unite"], academic_year, unite["semestre"], filiere, niveau_id)
		if r and r["statut"] == "Validé":
			return True, "jury" if r.get("valide_par_jury") else "note"
	else:
		m = _matiere_seule(student, unite["matieres"][0]["teaching_unit"], academic_year, filiere, niveau_id)
		if m["valide"]:
			return True, "jury" if m["par_jury"] else "note"
	if acquises is None:
		acquises = matieres_acquises(student, sauf_annee=academic_year)
	if unite["matieres"] and all(est_acquise(m["teaching_unit"], acquises) for m in unite["matieres"]):
		return True, "acquis"
	return False, ""


def bilan_niveau(student, filiere, niveau, academic_year):
	"""Crédits et dettes d'un étudiant pour la grille d'un niveau et d'une année."""
	acquises = matieres_acquises(student, sauf_annee=academic_year)
	total = valides = 0.0
	unites, dettes, tu_valides = [], [], []
	for u in unites_du_niveau(filiere, niveau, academic_year):
		ok, source = statut_unite(student, u, academic_year, filiere, niveau, acquises)
		total += u["credits"]
		if ok:
			valides += u["credits"]
			tu_valides.extend(m["teaching_unit"] for m in u["matieres"])
		else:
			for m in u["matieres"]:
				note = frappe.db.get_value("Resultat Academique", {"student": student, "teaching_unit": m["teaching_unit"],
																   "academic_year": academic_year}, "note_finale")
				dettes.append({**m, "unite": u["unite"], "unite_intitule": u["intitule"], "note": note or 0})
		unites.append({**u, "valide": ok, "source": source})
	return {"total": total, "valides": valides, "dette": total - valides, "unites": unites,
			"dettes": dettes, "tu_valides": tu_valides}
