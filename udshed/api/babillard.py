# Copyright (c) 2026, Udshed and contributors
# For license information, please see license.txt

"""API du Babillard Public des notes.

Alimente la page publique ``/babillard`` (accessible sans connexion).

Le babillard est destiné **uniquement** à l'affichage des notes d'un
étudiant recherché par Niveau + Matricule, pour une année académique
donnée. L'étudiant choisit une *session* (semestre) puis une *matière*
parmi celles disponibles : la page affiche alors la note de **Contrôle
continu** et d'**Examen** pour cette seule matière.

Aucune moyenne (MPS / MPC), mention, grade ni décision (Admis / Ajourné)
n'est exposée : le babillard présente les notes telles qu'elles figurent
au procès-verbal (CC + Examen), sans jugement académique.

Règle métier : seules les notes de « Session Examen Note » ayant le
statut **Publié** sont prises en compte. Les notes en Brouillon / Saisi
/ Validé ne sont jamais exposées.
"""

import frappe
from frappe import _
from frappe.utils import flt

from udshed.grade_calculation import get_student_cycle

SEMESTRES = ["Semestre 1", "Semestre 2"]
TYPE_CC = "Controlle Continue (CC)"
TYPE_NORMALE = "Examen de session normal"


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


def _get_filiere_name(filiere):
	"""Nom lisible d'une Filière."""
	if not filiere:
		return ""
	return frappe.get_cached_value("Field of study", filiere, "name_of_field") or filiere


def _get_ue_label(teaching_unit):
	"""Détails de la matière consultée : UE (intitulé) + Cours rattaché (code, intitulé).

	Returns:
		dict: {
			"teaching_unit":    nom du document Teaching Unit,
			"ue_intitule":      intitulé de la matière (Teaching Unit),
			"course":           nom du Cours rattaché,
			"course_code":      code du Cours,
			"course_intitule":  intitulé du Cours,
			"code":             code d'affichage (cours sinon vide),
			"intitule":         libellé principal (cours sinon UE sinon TU),
		}
	"""
	tu = frappe.get_cached_value(
		"Teaching Unit", teaching_unit, ["name", "course", "intitule_cours"], as_dict=True
	) or {}
	course_name = tu.get("course") or ""
	course_code = ""
	course_intitule = ""
	if course_name:
		row = frappe.db.get_value("Course", course_name, ["code", "intitule"], as_dict=True) or {}
		course_code = row.get("code") or course_name
		course_intitule = row.get("intitule") or ""
	return {
		"teaching_unit": teaching_unit,
		"ue_intitule": tu.get("intitule_cours") or "",
		"course": course_name,
		"course_code": course_code,
		"course_intitule": course_intitule,
		"code": course_code,
		"intitule": course_intitule or tu.get("intitule_cours") or teaching_unit,
	}


def _infos_etudiant(student, classe):
	"""Fiche affichable de l'étudiant (identité + classe de l'année)."""
	return {
		"name": student.name,
		"matricule": student.matricule or "",
		"nom": student.nom or "",
		"prenom": student.prenom or "",
		"filiere": _get_filiere_name(classe.get("filiere")),
		"filiere_code": classe.get("filiere") or "",
		"niveau": classe.get("niveau") or "",
		"cycle": get_student_cycle(student) or "",
	}


def _trouver_etudiant(niveau, matricule, academic_year):
	"""Valide (niveau, matricule) pour une année et renvoie l'étudiant.

	Le niveau effectif provient de la réinscription validée de l'année
	(à défaut du niveau actuel de l'étudiant). Renvoie une réponse
	``{"success": False, "message": ...}`` en cas d'erreur, sinon
	``{"success": True, "student": <doc>, "classe": {...}}``.
	"""
	niveau = (niveau or "").strip()
	matricule = (matricule or "").strip()

	if not niveau:
		return _erreur(_("Veuillez sélectionner un niveau."))
	if not matricule:
		return _erreur(_("Veuillez saisir le matricule de l'étudiant."))
	if academic_year and not frappe.db.exists("Academic Year", academic_year):
		return _erreur(
			_("L'année académique « {0} » est introuvable.").format(academic_year)
		)

	student_name = frappe.db.get_value("Student", {"matricule": matricule}, "name")
	if not student_name:
		return _erreur(
			_("Aucun étudiant ne correspond au matricule « {0} ».").format(matricule)
		)

	reg = frappe.db.get_value(
		"Academic Reregistration",
		{"student": student_name, "academic_year": academic_year},
		["niveau", "filiere"],
		as_dict=True,
	) or {}
	niveau_effectif = (
		reg.get("niveau")
		or frappe.db.get_value("Student", student_name, "niveau_actuel")
		or ""
	)
	if niveau_effectif != niveau:
		return _erreur(
			_("Le matricule « {0} » n'appartient pas au niveau « {1} » sélectionné.").format(
				matricule, niveau
			)
		)

	student = frappe.get_doc("Student", student_name)
	return {
		"success": True,
		"student": student,
		"classe": {
			"niveau": niveau_effectif,
			"filiere": reg.get("filiere") or student.get("filiere") or "",
		},
	}


# ---------------------------------------------------------------------------
# Collecte des notes publiées par matière
# ---------------------------------------------------------------------------
def _sessions_de(academic_year):
	"""Sessions d'examen d'une année académique (nom, type, semestre)."""
	return frappe.get_all(
		"Session Examen",
		filters={"academic_year": academic_year},
		fields=["name", "type_dexamen", "semestre"],
	)


def _notes_publiees_matiere(student_name, teaching_unit, academic_year):
	"""Notes publiées d'un étudiant pour une matière, indexées par type de session.

	Returns:
		tuple: (notes_par_type, semestre) — les clés de ``notes_par_type``
		sont les ``type_dexamen`` des sessions (ex. « Contrôle continu »,
		« Examen de session normal ») ; le semestre est celui des notes
		trouvées ("" si introuvable).
	"""
	sessions = _sessions_de(academic_year)
	if not sessions:
		return {}, ""

	par_session = {s["name"]: s for s in sessions}
	notes = frappe.get_all(
		"Session Examen Note",
		filters={
			"student": student_name,
			"teaching_unit": teaching_unit,
			"session_examen": ["in", list(par_session)],
			"statut": "Publié",
		},
		fields=[
			"session_examen",
			"note_cc_moyenne", "cc_saisi",
			"note_examen", "examen_saisi",
			"note_finale", "note_pct", "grade", "point",
		],
	)

	semestre = ""
	par_type = {}
	for n in notes:
		s = par_session.get(n["session_examen"]) or {}
		if not semestre and s.get("semestre") in SEMESTRES:
			semestre = s["semestre"]
		par_type[s.get("type_dexamen")] = n
	return par_type, semestre


def _lire_notes_matiere(student_name, teaching_unit, academic_year):
	"""Notes publiées (CC + Examen) d'une matière, miroir du procès-verbal.

	Le CC affiché est la moyenne harmonisée de la session normale
	(``note_cc_moyenne``) ; à défaut, on retombe sur la note de la session
	« Contrôle continu » (données historiques). L'Examen est la note de la
	session normale. La session de rattrapage n'est jamais exposée ici.

	Returns:
		dict: ``{"cc", "examen", "moyenne", "note_pct", "grade", "point",
		"semestre"}`` — les champs non publiés valent None/"", la moyenne,
		le grade et les points sont ceux du procès-verbal (note finale).
	"""
	notes, semestre = _notes_publiees_matiere(student_name, teaching_unit, academic_year)
	normale = notes.get(TYPE_NORMALE) or {}
	cc_examen = notes.get(TYPE_CC) or {}

	cc = None
	if normale.get("cc_saisi") and normale.get("note_cc_moyenne") is not None:
		cc = normale.get("note_cc_moyenne")
	elif cc_examen.get("cc_saisi") and cc_examen.get("note_cc_moyenne") is not None:
		cc = cc_examen.get("note_cc_moyenne")

	examen = normale.get("note_examen") if normale.get("examen_saisi") else None

	moyenne = normale.get("note_finale") if normale else None
	grade = (normale.get("grade") or "") if normale else ""
	point = normale.get("point") if normale else None

	return {
		"cc": flt(cc) if cc is not None else None,
		"examen": flt(examen) if examen is not None else None,
		"moyenne": flt(moyenne) if moyenne is not None else None,
		"note_pct": flt(normale.get("note_pct")) if normale and normale.get("note_pct") is not None else None,
		"grade": grade,
		"point": flt(point) if point is not None else None,
		"semestre": semestre,
	}


# ---------------------------------------------------------------------------
# Endpoints publics
# ---------------------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def list_students(niveau=None, filiere=None, academic_year=None, publies=None):
	"""Liste des étudiants d'un niveau (± filière, ± année) avec leur matricule.

	Permet d'afficher dans le babillard la liste des matricules afin de
	consulter ensuite les notes d'un étudiant. Tous les étudiants inscrits
	(réinscription « Validée ») de la classe sont proposés — qu'ils aient ou
	non des notes publiées : la liste ne dépend plus de l'état de publication.

	Args:
		niveau (str): Label du niveau (ex : « Licence 1 ») — obligatoire
		filiere (str): Field of study (optionnel)
		academic_year (str): Année académique (défaut : année courante)
		publies (str): « 1 » pour ne proposer que les étudiants ayant au
			moins une note publiée (comportement historique, optionnel)

	Returns:
		dict: ``{"success": True, "academic_year", "students": [...]}``
	"""
	niveau = (niveau or "").strip()
	if not niveau:
		return _erreur(_("Veuillez sélectionner un niveau."))

	year = (academic_year or "").strip() or _get_current_academic_year()
	if not frappe.db.exists("Academic Year", year):
		return _erreur(_("L'année académique « {0} » est introuvable.").format(year))

	seuls_publies = (publies or "").strip() in ("1", "true", "True")

	filters = {"academic_year": year, "niveau": niveau, "statut": "Validée"}
	if filiere:
		filiere = filiere.strip()
		if not frappe.db.exists("Field of study", filiere):
			return _erreur(_("La filière « {0} » est introuvable.").format(filiere))
		filters["filiere"] = filiere

	regs = frappe.get_all(
		"Academic Reregistration", filters=filters, fields=["student", "filiere"]
	)
	seen = set()
	rows = []
	for r in regs:
		if r.student in seen or not frappe.db.exists("Student", r.student):
			continue
		seen.add(r.student)
		if seuls_publies and not _any_note_publiee(r.student, year):
			continue
		doc = frappe.get_cached_doc("Student", r.student)
		rows.append({
			"name": r.student,
			"matricule": doc.get("matricule") or r.student,
			"nom": doc.get("nom") or "",
			"prenom": doc.get("prenom") or "",
			"filiere": r.filiere,
		})

	rows.sort(key=lambda s: ((s["nom"] or "").lower(), (s["prenom"] or "").lower()))
	return {"success": True, "academic_year": year, "students": rows}


def _any_note_publiee(student_name, academic_year):
	"""Vrai si l'étudiant a au moins une note publiée pour l'année donnée."""
	sessions = _sessions_de(academic_year)
	if not sessions:
		return False
	return frappe.db.exists("Session Examen Note", {
		"student": student_name,
		"session_examen": ["in", [s["name"] for s in sessions]],
		"statut": "Publié",
	})


@frappe.whitelist(allow_guest=True)
def matieres_publiees(niveau=None, matricule=None, academic_year=None):
	"""Matières d'un étudiant pour lesquelles une note (CC ou Examen) est publiée.

	Avec la fiche de l'étudiant et la liste des sessions (semestres) de
	l'année où des notes sont publiées. Une matière n'apparaît que si au
	moins une note publiée est consultable (règle de publication).

	Returns:
		dict: ``{"success", "student", "academic_year", "semestres",
		"matieres": [{teaching_unit, code, intitule, semestre, notes}]}``
	"""
	year = (academic_year or "").strip() or _get_current_academic_year()
	res = _trouver_etudiant(niveau, matricule, year)
	if not res["success"]:
		return res
	student = res["student"]

	sessions = _sessions_de(year)
	par_matiere = {}
	semestres = set()
	if sessions:
		par_session = {s["name"]: s["semestre"] for s in sessions}
		notes = frappe.get_all(
			"Session Examen Note",
			filters={
				"student": student.name,
				"session_examen": ["in", list(par_session)],
				"statut": "Publié",
			},
			fields=["teaching_unit", "session_examen"],
		)
		for n in notes:
			semestre = par_session.get(n["session_examen"], "")
			if semestre not in SEMESTRES:
				continue
			semestres.add(semestre)
			rationnel = par_matiere.get(n["teaching_unit"])
			if rationnel is None or SEMESTRES.index(semestre) > SEMESTRES.index(rationnel):
				par_matiere[n["teaching_unit"]] = semestre

	matieres = []
	for teaching_unit, semestre in par_matiere.items():
		notes_v = _lire_notes_matiere(student.name, teaching_unit, year)
		if notes_v["cc"] is None and notes_v["examen"] is None:
			continue
		matieres.append({
			**_get_ue_label(teaching_unit),
			"semestre": semestre,
			"notes": {
				"cc": notes_v["cc"],
				"examen": notes_v["examen"],
				"moyenne": notes_v["moyenne"],
				"note_pct": notes_v["note_pct"],
				"grade": notes_v["grade"],
				"point": notes_v["point"],
			},
		})

	matieres.sort(
		key=lambda m: (SEMESTRES.index(m["semestre"]), (m["intitule"] or "").lower())
	)

	return {
		"success": True,
		"student": _infos_etudiant(student, res["classe"]),
		"academic_year": year,
		"semestres": sorted(semestres, key=lambda s: SEMESTRES.index(s)),
		"matieres": matieres,
		"school_name": frappe.db.get_single_value("Udshed Setting", "school_name") or "",
	}


@frappe.whitelist(allow_guest=True)
def consulter_matiere(niveau=None, matricule=None, academic_year=None, teaching_unit=None):
	"""Note (CC + Examen) publiée d'un étudiant pour UNE matière.

	Args:
		niveau (str): Niveau (ex : « Licence 1 ») — obligatoire
		matricule (str): Matricule de l'étudiant — obligatoire
		academic_year (str): Année académique (défaut : année courante)
		teaching_unit (str): Nom du document Teaching Unit — obligatoire

	Returns:
		dict: ``{"success", "student", "academic_year", "semestre",
		"matiere": {...libellé...}, "notes": {"cc", "examen", "moyenne",
		"note_pct", "grade", "point"}}``
	"""
	year = (academic_year or "").strip() or _get_current_academic_year()
	res = _trouver_etudiant(niveau, matricule, year)
	if not res["success"]:
		return res

	teaching_unit = (teaching_unit or "").strip()
	if not teaching_unit:
		return _erreur(_("Veuillez sélectionner une matière."))
	if not frappe.db.exists("Teaching Unit", teaching_unit):
		return _erreur(_("La matière sélectionnée est introuvable."))

	student = res["student"]
	notes_v = _lire_notes_matiere(student.name, teaching_unit, year)
	if notes_v["cc"] is None and notes_v["examen"] is None:
		return _erreur(
			_("Aucune note publiée pour cette matière en {0}.").format(year)
		)

	return {
		"success": True,
		"student": _infos_etudiant(student, res["classe"]),
		"academic_year": year,
		"semestre": notes_v["semestre"],
		"matiere": {
			**_get_ue_label(teaching_unit),
			"semestre": notes_v["semestre"],
		},
		"notes": {
			"cc": notes_v["cc"],
			"examen": notes_v["examen"],
			"moyenne": notes_v["moyenne"],
			"note_pct": notes_v["note_pct"],
			"grade": notes_v["grade"],
			"point": notes_v["point"],
		},
		"school_name": frappe.db.get_single_value("Udshed Setting", "school_name") or "",
	}