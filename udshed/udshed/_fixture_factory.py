# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Fabrique de fixtures (données de test) pour UDSHED.

Chaque helper crée un document unique et autonome. Aucune donnée de
démonstration n'est insérée : ces fixtures sont réservées aux tests
d'intégration de l'application.
"""

import contextlib

import frappe

from udshed.grade_calculation import SEUILS_DEFAUT

TYPE_NORMALE = "Examen de session normal"

# Grille des grades alignée sur la configuration réelle de l'application.
GRADES = [
    {"note_min": 0, "note_max": 49.99, "grade": "F", "point": 0, "mention": ""},
    {"note_min": 50, "note_max": 79.99, "grade": "C", "point": 2, "mention": "Passable"},
    {"note_min": 80, "note_max": 100, "grade": "A", "point": 4, "mention": "Très bien"},
]

_COMPTEUR = {"n": 0}


def _next(prefix="TEST"):
    _COMPTEUR["n"] += 1
    return f"{prefix}-{_COMPTEUR['n']:04d}"


@contextlib.contextmanager
def suppress_commits():
    """Neutralise les frappe.db.commit() pendant un bloc (tests)."""
    original = frappe.db.commit
    frappe.db.commit = lambda *args, **kwargs: None
    try:
        yield
    finally:
        frappe.db.commit = original


# ---------------------------------------------------------------------- #
#  Académie
# ---------------------------------------------------------------------- #
def make_academic_year(start="2026", end="2027", is_current=False):
    """Crée (ou réutilise) une Academic Year unique."""
    name = f"{start}-{end}"
    if frappe.db.exists("Academic Year", name):
        doc = frappe.get_doc("Academic Year", name)
        if is_current:
            frappe.db.set_value("Academic Year", name, "is_current_year", 1)
        return doc
    doc = frappe.new_doc("Academic Year")
    doc.start_year = start
    doc.end_year = end
    doc.start_month = "Septembre"
    doc.end_month = "Juin"
    doc.is_current_year = 1 if is_current else 0
    doc.insert(ignore_permissions=True)
    return doc


def make_calendar_planing():
    doc = frappe.new_doc("Calendar Planing")
    doc.nom_du_planing = _next("CAL")
    doc.insert(ignore_permissions=True)
    return doc


def make_faculty():
    doc = frappe.new_doc("Faculty")
    doc.faculty_name = _next("Faculté")
    doc.faculty_code = _next("FAC")
    doc.insert(ignore_permissions=True)
    return doc


def make_teacher():
    n = _COMPTEUR["n"] + 1
    _COMPTEUR["n"] = n
    doc = frappe.new_doc("Teacher")
    doc.grade = "Dr"
    doc.first_name = f"Professeur {n}"
    doc.last_name = f"Testeur {n}"
    doc.email = f"teacher{n}@example.com"
    doc.status = "Permanent"
    doc.insert(ignore_permissions=True)
    return doc


def make_field_of_study(faculty, calendar=None, teacher=None):
    doc = frappe.new_doc("Field of study")
    doc.name_of_field = _next("Filière")
    doc.field_of_study_code = _next("FOS")
    doc.faculte = faculty.name
    if teacher:
        doc.department_coordinator = teacher.name
    doc.insert(ignore_permissions=True)
    doc._test_calendar = calendar
    doc._test_teacher = teacher
    return doc


def make_level(fos, level="Licence 1", order=1):
    """Ajoute un niveau (ligne enfant) à la Field of study et le retourne."""
    calendar = getattr(fos, "_test_calendar", None) or make_calendar_planing()
    teacher = getattr(fos, "_test_teacher", None) or make_teacher()
    fos.append(
        "field_of_study_level",
        {
            "level": level,
            "order": order,
            "coordonateur": teacher.name,
            "calendrier": calendar.name,
        },
    )
    fos.save(ignore_permissions=True)
    return fos.field_of_study_level[-1]


def make_course(code=None, intitule=None, semestre="Semestre 1"):
    doc = frappe.new_doc("Course")
    doc.code = code or _next("COU")
    doc.intitule = intitule or f"Cours {doc.code}"
    doc.semestre = semestre
    doc.nombre_dheure_cm = 20
    doc.nombre_dheure_td = 10
    doc.insert(ignore_permissions=True)
    return doc


def make_teaching_unit(course, academic_year, fos, niveau, credits=3, type_ue="Sans TP"):
    doc = frappe.new_doc("Teaching Unit")
    doc.course = course.name
    doc.academic_year = academic_year.name
    doc.mode = "En présentiel"
    doc.semestre = "Semestre 1"
    doc.credits = credits
    doc.type_ue = type_ue
    doc.append(
        "course_levels",
        {"filiere": fos.name, "niveau": niveau.name, "course_poid": credits},
    )
    doc.insert(ignore_permissions=True)
    return doc


def make_student(fos, niveau, cycle="Licence", niveau_actuel=None):
    n = _COMPTEUR["n"] + 1
    _COMPTEUR["n"] = n
    doc = frappe.new_doc("Student")
    doc.nom = f"Test {n}"
    doc.prenom = f"Étudiant {n}"
    doc.matricule = _next("MAT")
    doc.email = f"etudiant{n}@example.com"
    doc.sexe = "Homme"
    doc.phone = "+237655000000"
    doc.birth_date = "2000-01-01"
    doc.birth_place = "Dshang"
    doc.filiere = fos.name
    doc.cycle = cycle
    doc.niveau_actuel = niveau_actuel or niveau.level
    doc.insert(ignore_permissions=True)
    return doc


def make_session_examen(
    academic_year,
    calendar,
    filiere=None,
    niveau=None,
    type_dexamen=TYPE_NORMALE,
    semestre="Semestre 1",
    date_debut="2026-10-15",
    date_de_fin="2026-10-30",
):
    doc = frappe.new_doc("Session Examen")
    doc.academic_year = academic_year.name
    doc.calendar = calendar.name
    doc.type_dexamen = type_dexamen
    doc.semestre = semestre
    doc.date_debut = date_debut
    doc.date_de_fin = date_de_fin
    doc.name = _next("SESS")
    if filiere and niveau:
        doc.append("classes_concernees", {"filiere": filiere.name, "niveau": niveau.name})
    doc.insert(ignore_permissions=True)
    return doc


def make_session_examen_note(
    session,
    student,
    teaching_unit,
    note_cc=None,
    note_examen=None,
    note_tp=None,
    statut="Publié",
):
    doc = frappe.new_doc("Session Examen Note")
    doc.session_examen = session.name
    doc.student = student.name
    doc.teaching_unit = teaching_unit.name
    doc.type_ue = teaching_unit.type_ue
    if note_cc is not None:
        doc.append("notes_cc", {"cc_label": "CC 1", "cc_weight": 1, "note_cc": note_cc})
    doc.note_examen = note_examen
    doc.note_tp = note_tp
    doc.statut = statut
    doc.insert(ignore_permissions=True)
    return doc


def make_academic_reregistration(
    fos, niveau_label, academic_year, ues, student=None, semestre="Semestre 1", cycle="Licence"
):
    """Crée une réinscription académique validée avec les UE inscrites.

    Reproduit le parcours de la Saisie des notes : réinscription
    « Validée » + lignes Reregistration Course Item « Inscrit ».

    Args:
        fos: Document Field of study
        niveau_label (str): label du niveau (ex : "BTS 1")
        academic_year: Document Academic Year
        ues (list): Teaching Units inscrites
        student (Document, optional): étudiant (sinon créé)
        semestre (str): "Semestre 1" / "Semestre 2"

    Returns:
        tuple: (reinscription, academic_reregistration, student)
    """
    if student is None:
        niveau = None
        for row in fos.field_of_study_level:
            if row.level == niveau_label:
                niveau = row
                break
        if niveau is None:
            niveau = make_level(fos, level=niveau_label)
        student = make_student(fos, niveau, cycle=cycle)

    reinscription = frappe.new_doc("Reinscription")
    reinscription.academic_year = academic_year.name
    reinscription.statut = "Ouverte"
    reinscription.date_ouverture = "2026-09-01"
    reinscription.date_cloture = "2026-12-31"
    reinscription.note_minimale = 0
    reinscription.note_maximale = 20
    reinscription.insert(ignore_permissions=True)

    doc = frappe.new_doc("Academic Reregistration")
    doc.student = student.name
    doc.academic_year = academic_year.name
    doc.filiere = fos.name
    doc.niveau = niveau_label
    doc.semestre = semestre
    doc.reinscription_session = reinscription.name
    doc.statut = "Validée"
    for ue in ues:
        doc.append(
            "cours_inscrits",
            {
                "teaching_unit": ue.name,
                "intitule": ue.intitule_cours or ue.name,
                "semestre": semestre,
                "statut": "Inscrit",
            },
        )
    doc.insert(ignore_permissions=True)
    return reinscription, doc, student


# ---------------------------------------------------------------------- #
#  Formules et grilles
# ---------------------------------------------------------------------- #
def seed_formule(cycle, composantes, pourcentages, seuil=None):
    """Crée (ou réutilise) une formule active pour un (cycle, combinaison).

    La combinaison est déduite des composantes (pourcentage > 0), triées.
    Le total des pourcentages doit être 100.

    Exemple :
        seed_formule("BTS", ["Controle Continu(CC)", "Examen"], [40, 60])

    Args:
        cycle (str): "Licence", "BTS" ou "Master"
        composantes (list[str]): labels des composantes principales
        pourcentages (list[float]): pourcentages alignés sur composantes
        seuil (float, optional): seuil de validation (défaut : SEUILS_DEFAUT)

    Returns:
        Document: Grade Formula active
    """
    combinaison = " + ".join(sorted(composantes))
    active = frappe.db.get_value(
        "Grade Formula",
        {"cycle": cycle, "combinaison": combinaison, "active": 1},
        "name",
    )
    if active:
        return frappe.get_doc("Grade Formula", active)

    existing = frappe.db.get_value(
        "Grade Formula", {"cycle": cycle, "combinaison": combinaison}, "name"
    )
    if existing:
        frappe.db.set_value(
            "Grade Formula", {"cycle": cycle, "combinaison": combinaison}, "active", 0
        )
        doc = frappe.get_doc("Grade Formula", existing)
        doc.active = 1
        doc.save(ignore_permissions=True)
        return doc

    doc = frappe.new_doc("Grade Formula")
    doc.name = _next("FORMULE")
    doc.cycle = cycle
    doc.active = 1
    doc.seuil_validation = (
        seuil if seuil is not None else SEUILS_DEFAUT.get(cycle, 50)
    )
    doc.methode_arrondi = "Au plus proche"
    doc.methode_calcul_cc = "Moyenne arithmétique"
    doc.nb_meilleures_notes_cc = 2
    for label, pct in zip(composantes, pourcentages):
        doc.append("components", {"composante": label, "pourcentage": pct})
    doc.insert(ignore_permissions=True)
    return doc


def seed_grade_formula(cycle, cc=30, examen=50, tp=20, seuil=None):
    """Crée (ou remplace) la formule active CC+Examen+TP (Avec TP) d'un cycle.

    Décompose les pourcentages en composantes principales. Le total doit
    être 100 % (ex: seed_grade_formula("BTS", 30, 50, 20)).

    Returns:
        Document: Grade Formula active
    """
    frappe.db.set_value(
        "Grade Formula", {"cycle": cycle, "active": 1}, "active", 0
    )
    return seed_formule(
        cycle,
        ["Controle Continu(CC)", "Examen", "Travaux Pratique (TP)"],
        [cc, examen, tp],
        seuil=seuil,
    )


def seed_grille_grades():
    """Renseigne la grille des grades dans Udshed Setting."""
    setting = frappe.get_single("Udshed Setting")
    setting.set("grille_grades", [])
    for row in GRADES:
        setting.append("grille_grades", dict(row))
    setting.save(ignore_permissions=True)
    return setting
