# Copyright (c) 2026, Udshed and contributors
# For license information, please see license.txt

"""API du Babillard Public des notes.

Alimente la page publique ``/babillard`` (accessible sans connexion).
Permet de consulter les notes *publiées* d'un étudiant recherché par
Niveau + Matricule, pour une année académique et un semestre donnés.

Règle métier : seules les notes de « Session Examen Note » ayant le
statut **Publié** sont prises en compte. Les notes en Brouillon / Saisi
/ Validé ne sont jamais exposées.
"""

import frappe
from frappe import _

from udshed.grade_calculation import get_seuil_validation, get_student_cycle
from udshed.api.resultat_academique import _get_credits

SEMESTRES = ["Semestre 1", "Semestre 2"]
TYPE_NORMALE = "Examen de session normal"
TYPE_RATTRAPAGE = "Examen de rattrapage"


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------
def _start_year(year_name):
	"""Extrait l'année de début d'un nom d'Academic Year (ex: '2025-2026' -> 2025)."""
	try:
		return int(str(year_name).split("-")[0])
	except (ValueError, IndexError):
		return 0


def _erreur(message):
	"""Retourne une réponse d'erreur structurée pour le front-end."""
	return {"success": False, "message": str(message)}


def _get_current_academic_year():
	"""Année académique courante : Udshed Setting > is_current_year > max."""
	year = frappe.db.get_single_value("Udshed Setting", "current_year")
	if year:
		return year

	year = frappe.db.get_value("Academic Year", {"is_current_year": 1}, "name")
	if year:
		return year

	years = frappe.get_all("Academic Year", fields=["name"])
	return max(years, key=lambda y: _start_year(y["name"]))["name"] if years else ""


def _get_seuil_validation(cycle):
	"""Seuil de validation (%) pour un cycle (délègue au moteur central)."""
	return get_seuil_validation(cycle)


def _get_mention(mps):
	"""Mention associée à une moyenne (%) selon la grille des grades."""
	setting = frappe.get_single("Udshed Setting")
	for g in setting.get("grille_grades"):
		note_min = g.get("note_min_100")
		if note_min is None:
			note_min = g.get("note_min") or 0
		note_max = g.get("note_max_100")
		if note_max is None:
			note_max = g.get("note_max") or 0
		try:
			if note_min <= mps <= note_max:
				return g.mention or ""
		except TypeError:
			continue
	return ""


def _get_grade_scale():
	"""Grille des grades triée (du plus haut au plus bas)."""
	setting = frappe.get_single("Udshed Setting")
	scale = []
	for g in setting.get("grille_grades"):
		note_min = g.get("note_min_100")
		if note_min is None:
			note_min = g.get("note_min") or 0
		note_max = g.get("note_max_100")
		if note_max is None:
			note_max = g.get("note_max") or 0
		scale.append({
			"note_min": note_min,
			"note_max": note_max,
			"grade": g.grade,
			"point": g.point,
			"mention": g.mention or "",
		})
	scale.sort(key=lambda x: x.get("note_min") or 0, reverse=True)
	return scale


def _get_filiere_name(filiere):
	"""Nom lisible d'une Filière."""
	if not filiere:
		return ""
	return frappe.get_cached_value("Field of study", filiere, "name_of_field") or filiere


def _get_ue_label(teaching_unit):
	"""Code + intitulé d'une Teaching Unit."""
	tu = frappe.get_cached_value(
		"Teaching Unit", teaching_unit, ["course", "intitule_cours"], as_dict=True
	) or {}
	return (tu.get("course") or ""), (tu.get("intitule_cours") or teaching_unit)


# ---------------------------------------------------------------------------
# Collecte des notes publiées
# ---------------------------------------------------------------------------
def _semestres_publies(student_name):
	"""Semestres (année, semestre) où l'étudiant a au moins une note publiée.

	Triés chronologiquement (année puis S1/S2) — sert de base au calcul
	de la MPC cumulée.
	"""
	notes = frappe.get_all(
		"Session Examen Note",
		filters={"student": student_name, "statut": "Publié"},
		fields=["session_examen"],
	)
	sessions = list({n.session_examen for n in notes})
	if not sessions:
		return []

	rows = frappe.get_all(
		"Session Examen",
		filters={"name": ["in", sessions]},
		fields=["academic_year", "semestre"],
		distinct=True,
	)

	semestres = [
		(r.academic_year, r.semestre)
		for r in rows
		if r.academic_year and r.semestre in SEMESTRES
	]
	semestres.sort(key=lambda t: (_start_year(t[0]), SEMESTRES.index(t[1])))
	return semestres


def _resultat_semestre(student, academic_year, semestre, seuil):
	"""Calcule le résultat d'un semestre à partir des seules notes publiées.

	Une UE peut avoir une note de session normale et une note de
	rattrapage (toutes deux publiées). On conserve la meilleure des deux
	(cohérent avec ``calculer_resultat_session``).

	MPS = Σ(Cj × note_pct_j) / Σ(Cj)  — moyenne pondérée en pourcentage.
	"""
	sessions = frappe.get_all(
		"Session Examen",
		filters={"academic_year": academic_year, "semestre": semestre},
		fields=["name", "type_dexamen"],
	)
	session_types = {s.name: s.type_dexamen for s in sessions}
	if not session_types:
		return _semestre_vide(academic_year, semestre)

	notes = frappe.get_all(
		"Session Examen Note",
		filters={
			"student": student.name,
			"statut": "Publié",
			"session_examen": ["in", list(session_types)],
		},
		fields=[
			"session_examen", "teaching_unit", "note_finale", "note_pct",
			"grade", "point", "mention",
		],
	)
	if not notes:
		return _semestre_vide(academic_year, semestre)

	# Consolidation par UE : on garde la meilleure note (normale vs rattrapage)
	meilleures = {}
	for n in notes:
		est_rattrapage = session_types.get(n.session_examen) == TYPE_RATTRAPAGE
		current = meilleures.get(n.teaching_unit)
		if current is None or (n.note_finale or 0) > (current["note_finale"] or 0):
			meilleures[n.teaching_unit] = {
				"note_finale": n.note_finale,
				"note_pct": n.note_pct,
				"grade": n.grade,
				"point": n.point,
				"mention": n.mention,
				"est_rattrapage": est_rattrapage,
			}

	somme_cp = 0.0
	somme_c = 0
	credits_obtenus = 0
	ues = []

	for tu_name, m in meilleures.items():
		credits = _get_credits(student.name, tu_name)
		note_pct = m["note_pct"] or 0
		somme_cp += credits * note_pct
		somme_c += credits
		if note_pct >= seuil:
			credits_obtenus += credits

		code, intitule = _get_ue_label(tu_name)
		ues.append({
			"teaching_unit": tu_name,
			"code": code,
			"intitule": intitule,
			"credits": credits,
			"note_finale": m["note_finale"],
			"note_pct": note_pct,
			"grade": m["grade"] or "",
			"point": m["point"] or 0,
			"mention": m["mention"] or "",
			"statut": "Validé" if note_pct >= seuil else "Non Validé",
			"session": _("Rattrapage") if m["est_rattrapage"] else _("Normale"),
		})

	ues.sort(key=lambda x: (x["intitule"] or "").lower())

	ue_validees = sum(1 for u in ues if u["statut"] == "Validé")
	return {
		"academic_year": academic_year,
		"semestre": semestre,
		"mps": round(somme_cp / somme_c, 2) if somme_c > 0 else 0,
		"mpc": None,  # renseigné après calcul cumulé
		"total_credits": somme_c,
		"credits_obtenus": credits_obtenus,
		"ue_validees": ue_validees,
		"ue_non_validees": len(ues) - ue_validees,
		"ues": ues,
		"mention": "",
		"decision": "",
	}


def _semestre_vide(academic_year, semestre):
	"""Semestre sans note publiée."""
	return {
		"academic_year": academic_year,
		"semestre": semestre,
		"mps": 0,
		"mpc": None,
		"total_credits": 0,
		"credits_obtenus": 0,
		"ue_validees": 0,
		"ue_non_validees": 0,
		"ues": [],
		"mention": "",
		"decision": "",
	}


# ---------------------------------------------------------------------------
# Endpoint public
# ---------------------------------------------------------------------------
def _get_etudiants_filiere(academic_year, filiere, niveau):
	"""Étudiants inscrits (réinscription validée) d'une filière/niveau pour une année."""
	regs = frappe.get_all(
		"Academic Reregistration",
		filters={"academic_year": academic_year, "filiere": filiere, "niveau": niveau, "statut": "Validée"},
		fields=["student"],
	)
	return [r.student for r in regs if frappe.db.exists("Student", r.student)]


def _lier_niveau(filiere, niveau):
	"""Vérifie que le niveau appartient à la filière (Field of study Level)."""
	doc = frappe.get_cached_doc("Field of study", filiere)
	return any(row.level == niveau for row in (doc.get("field_of_study_level") or []))


@frappe.whitelist(allow_guest=True)
def consulter_notes_filiere(filiere=None, niveau=None, academic_year=None, semestre=None):
	"""Consulte les notes *publiées* de toute une filière (tableau par étudiant).

	Pour une filière/niveau/année/semestre donnés, renvoie pour chaque étudiant
	sa note par UE (finale, %, grade, statut) ainsi que MPS, crédits et décision.
	Seules les notes publiées sont exposées (règle du babillard).

	Returns:
		dict: ``{"success": bool, ...données...}``
	"""
	filiere = (filiere or "").strip()
	niveau = (niveau or "").strip()

	if not filiere:
		return _erreur(_("Veuillez sélectionner une filière."))
	if not niveau:
		return _erreur(_("Veuillez sélectionner un niveau."))
	if not frappe.db.exists("Field of study", filiere):
		return _erreur(_("La filière « {0} » est introuvable.").format(filiere))
	if not _lier_niveau(filiere, niveau):
		return _erreur(_("Le niveau « {0} » n'appartient pas à la filière sélectionnée.").format(niveau))

	year = (academic_year or "").strip() or _get_current_academic_year()
	if not frappe.db.exists("Academic Year", year):
		return _erreur(_("L'année académique « {0} » est introuvable.").format(year))

	if semestre and semestre not in SEMESTRES:
		semestre = None

	students = _get_etudiants_filiere(year, filiere, niveau)
	if not students:
		return _erreur(_("Aucun étudiant inscrit en {0} / {1} pour l'année {2}.").format(filiere, niveau, year))

	# Seuil de validation selon le cycle (on prend le cycle du premier étudiant ;
	# en pratique les étudiants d'une même filière/niveau partagent le cycle).
	cycle = get_student_cycle(students[0])
	seuil = _get_seuil_validation(cycle)

	colonnes_ues = {}
	lignes = []
	for student_name in sorted(students, key=lambda n: (frappe.db.get_value("Student", n, "nom") or "", n)):
		student = frappe.get_doc("Student", student_name)
		if semestre:
			res = _resultat_semestre(student, year, semestre, seuil)
			selection = [res]
		else:
			annees = [y for (y, s) in _semestres_publies(student_name) if y == year]
			selection = []
			for y in sorted(set(annees), key=_start_year):
				for s in SEMESTRES:
					_r = _resultat_semestre(student, y, s, seuil)
					if _r["ues"]:
						selection.append(_r)
		# MPC simple sur les semestres sélectionnés
		mpc = round(sum(r["mps"] for r in selection) / len(selection), 2) if selection else 0
		decision = "Admis" if (selection and max(r["mps"] for r in selection) >= seuil) else "Ajourné"
		mention = max((r["mention"] for r in selection), key=lambda m: _poids_mention(m)) if selection else ""

		resultats = {}
		for r in selection:
			for u in r["ues"]:
				colonnes_ues[u["teaching_unit"]] = {
					"teaching_unit": u["teaching_unit"],
					"code": u["code"],
					"intitule": u["intitule"],
					"credits": u["credits"],
				}
				resultats[u["teaching_unit"]] = {
					"note_finale": u["note_finale"],
					"note_pct": u["note_pct"],
					"grade": u["grade"],
					"point": u["point"],
					"mention": u["mention"],
					"statut": u["statut"],
					"session": u["session"],
				}

		lignes.append({
			"student": student.name,
			"matricule": student.matricule or "",
			"nom": student.nom or "",
			"prenom": student.prenom or "",
			"resultats": resultats,
			"mps": max(r["mps"] for r in selection) if selection else 0,
			"mpc": mpc,
			"credits_obtenus": max(r["credits_obtenus"] for r in selection) if selection else 0,
			"total_credits": max(r["total_credits"] for r in selection) if selection else 0,
			"decision": decision,
			"mention": mention,
		})

	ues = sorted(colonnes_ues.values(), key=lambda u: (u["intitule"] or u["code"] or "").lower())

	return {
		"success": True,
		"filiere": filiere,
		"filiere_name": _get_filiere_name(filiere),
		"niveau": niveau,
		"academic_year": year,
		"semestre": semestre,
		"cycle": cycle,
		"seuil": seuil,
		"ues": ues,
		"students": lignes,
		"school_name": frappe.db.get_single_value("Udshed Setting", "school_name") or "",
	}


def _poids_mention(mention):
	"""Ordre des mentions pour retenir la meilleure (Valeur faible si inconnue)."""
	ordre = ["", "Passable", "Assez Bien", "Bien", "Très Bien"]
	try:
		return ordre.index(mention)
	except ValueError:
		return 0


@frappe.whitelist(allow_guest=True)
def consulter_notes(niveau=None, matricule=None, academic_year=None, semestre=None):
	"""Consulte les notes publiées d'un étudiant.

	Args:
		niveau (str): Niveau (ex: "Licence 1") — obligatoire
		matricule (str): Matricule de l'étudiant — obligatoire
		academic_year (str): Année académique (défaut: année courante)
		semestre (str): "Semestre 1" ou "Semestre 2" (défaut: toute l'année)

	Returns:
		dict: ``{"success": bool, "message": str, ...données...}``
	"""
	niveau = (niveau or "").strip()
	matricule = (matricule or "").strip()

	if not niveau:
		return _erreur(_("Veuillez sélectionner un niveau."))
	if not matricule:
		return _erreur(_("Veuillez saisir le matricule de l'étudiant."))

	year = (academic_year or "").strip() or _get_current_academic_year()
	if not frappe.db.exists("Academic Year", year):
		return _erreur(_("L'année académique « {0} » est introuvable.").format(year))

	# --- Étudiant par matricule ---
	student_name = frappe.db.get_value("Student", {"matricule": matricule}, "name")
	if not student_name:
		return _erreur(
			_("Aucun étudiant ne correspond au matricule « {0} ».").format(matricule)
		)
	student = frappe.get_doc("Student", student_name)

	# --- Vérification du niveau (réinscription de l'année, sinon niveau actuel) ---
	reg_niveau = frappe.db.get_value(
		"Academic Reregistration",
		{"student": student_name, "academic_year": year},
		"niveau",
	)
	niveau_effectif = reg_niveau or student.get("niveau_actuel") or ""
	if niveau_effectif != niveau:
		return _erreur(
			_("Le matricule « {0} » n'appartient pas au niveau « {1} » sélectionné.").format(
				matricule, niveau
			)
		)

	if semestre and semestre not in SEMESTRES:
		semestre = None

	# --- Semestres où l'étudiant a des notes publiées (ordre chronologique) ---
	annees_semestres = _semestres_publies(student_name)
	if not annees_semestres:
		return _erreur(
			_("Aucune note publiée pour l'étudiant « {0} » ({1}).").format(matricule, niveau)
		)

	cycle = get_student_cycle(student)
	seuil = _get_seuil_validation(cycle)

	# Calcul de chaque semestre + MPC cumulée dans l'ordre chronologique
	calculs = {}
	mpc_cumul = 0
	for i, (y, s) in enumerate(annees_semestres, 1):
		res = _resultat_semestre(student, y, s, seuil)
		mpc = res["mps"]
		if i == 1:
			mpc_cumul = mpc
		else:
			mpc_cumul = round((mpc_cumul * (i - 1) + mpc) / i, 2)
		res["mpc"] = mpc_cumul
		res["mention"] = _get_mention(res["mps"])
		res["decision"] = "Admis" if res["mps"] >= seuil else "Ajourné"
		calculs[(y, s)] = res

	# --- Sélection des semestres demandés ---
	if semestre:
		selection = [(year, semestre)] if (year, semestre) in calculs else []
	else:
		selection = [(y, s) for (y, s) in annees_semestres if y == year]

	if not selection:
		return _erreur(
			_("Aucune note publiée pour l'étudiant « {0} » en {1}{2}.").format(
				matricule, year, (" / " + semestre) if semestre else ""
			)
		)

	semesters = [calculs[ys] for ys in selection]

	# --- Années disponibles pour cet étudiant + année précédente ---
	years_available = sorted({y for (y, s) in annees_semestres}, key=_start_year, reverse=True)
	prev_year = None
	if year in years_available:
		prevs = [y for y in years_available if _start_year(y) < _start_year(year)]
		if prevs:
			prev_year = max(prevs, key=_start_year)

	return {
		"success": True,
		"student": {
			"name": student.name,
			"matricule": student.matricule or "",
			"nom": student.nom or "",
			"prenom": student.prenom or "",
			"filiere": _get_filiere_name(student.filiere),
			"niveau": niveau_effectif,
			"cycle": cycle,
		},
		"academic_year": year,
		"semestre": semestre,
		"semesters": semesters,
		"years_available": years_available,
		"prev_year": prev_year,
		"cycle": cycle,
		"seuil": seuil,
		"grade_scale": _get_grade_scale(),
		"school_name": frappe.db.get_single_value("Udshed Setting", "school_name") or "",
	}
