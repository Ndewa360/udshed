# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from udshed.grade_calculation import get_seuil_validation, get_student_cycle

TYPE_NORMALE = "Examen de session normal"


def _detail_ue_non_validee(note, student_doc, seuil):
    """Construit le détail d'une UE non validée pour un étudiant."""
    teaching_unit_doc = frappe.get_doc("Teaching Unit", note.teaching_unit)
    course_name = ""
    if teaching_unit_doc.course:
        course_name = frappe.db.get_value(
            "Course", teaching_unit_doc.course, "intitule"
        )

    credits = frappe.db.get_value("Teaching Unit", note.teaching_unit, "credits") or 0

    return {
        "name": note.name,
        "student": note.student,
        "matricule": student_doc.matricule,
        "student_name": f"{student_doc.nom or ''} {student_doc.prenom or ''}".strip(),
        "cycle": get_student_cycle(student_doc),
        "niveau": student_doc.niveau_actuel or "",
        "teaching_unit": note.teaching_unit,
        "ue_name": course_name or note.teaching_unit,
        "credits": int(credits),
        "note_cc_moyenne": note.note_cc_moyenne,
        "note_examen": note.note_examen,
        "note_examen_rattrapage": note.note_examen_rattrapage,
        "note_examen_active": note.note_examen_active,
        "note_finale": note.note_finale,
        "note_pct": note.note_pct,
        "note_session_normale": note.note_pct,
        "grade": note.grade,
        "type_ue": note.type_ue,
        "seuil": seuil,
        "statut": "Non validé",
    }


@frappe.whitelist()
def identifier_rattrapages(session_examen):
    """Identifie tous les étudiants et UE non validés pour une session d'examen.

    Le passage au rattrapage est déterminé à partir des résultats de la session
    normale : une UE est concernée si sa note est inférieure au seuil du cycle.

    Args:
        session_examen: Nom du document Session Examen

    Returns:
        dict: détails des UE non validées + récapitulatif par étudiant
    """
    try:
        return _identifier_rattrapages_impl(session_examen)
    except Exception:
        frappe.log_error(" retake identifier_rattrapages")
        frappe.throw(_("Erreur lors de l'identification des rattrapages."))


def _identifier_rattrapages_impl(session_examen):
    session = frappe.get_doc("Session Examen", session_examen)

    notes = frappe.get_all(
        "Session Examen Note",
        filters={"session_examen": session_examen, "statut": "Publié"},
        fields=[
            "name",
            "student",
            "teaching_unit",
            "note_cc_moyenne",
            "note_examen",
            "note_examen_rattrapage",
            "note_examen_active",
            "note_finale",
            "note_pct",
            "grade",
            "type_ue",
        ],
    )

    if not notes:
        total_notes = frappe.db.count("Session Examen Note", {"session_examen": session_examen})
        if total_notes:
            frappe.throw(
                _("La session {0} contient {1} note(s) mais aucune n'est publiée. "
                  "Validez et publiez les notes avant d'identifier les rattrapages.").format(
                    session_examen, total_notes
                )
            )
        return {
            "session": session_examen,
            "annee_academique": session.academic_year,
            "semestre": session.semestre,
            "type_session": session.type_dexamen,
            "etudiants": [],
            "total_etudiants": 0,
            "total_non_valides": 0,
            "etudiants_eligibles": [],
            "total_eligibles": 0,
        }

    etudiants_non_valides = []
    for note in notes:
        student_doc = frappe.get_doc("Student", note.student)
        cycle = get_student_cycle(student_doc)
        seuil = get_seuil_validation(cycle)

        if note.note_pct is not None and note.note_pct < seuil:
            etudiants_non_valides.append(
                _detail_ue_non_validee(note, student_doc, seuil)
            )

    # Récapitulatif par étudiant (éligibilité après calcul complet de la session normale)
    par_etudiant = {}
    for detail in etudiants_non_valides:
        par_etudiant.setdefault(detail["student"], []).append(detail)

    etudiants_eligibles = [
        {
            "student": student,
            "matricule": details[0]["matricule"],
            "student_name": details[0]["student_name"],
            "cycle": details[0]["cycle"],
            "niveau": details[0]["niveau"],
            "ue_concernees": [d["ue_name"] for d in details],
            "nb_ue_concernees": len(details),
            "credits_concernee": sum(d["credits"] for d in details),
            "statut": "À rattraper",
        }
        for student, details in par_etudiant.items()
    ]

    return {
        "session": session_examen,
        "annee_academique": session.academic_year,
        "semestre": session.semestre,
        "type_session": session.type_dexamen,
        "etudiants": etudiants_non_valides,
        "total_etudiants": len(notes),
        "total_non_valides": len(etudiants_non_valides),
        "etudiants_eligibles": etudiants_eligibles,
        "total_eligibles": len(etudiants_eligibles),
    }


@frappe.whitelist()
def etudiants_eligibles_rattrapage(academic_year, semestre, filiere, niveau):
    """Liste des étudiants éligibles au rattrapage pour une classe et un semestre.

    Un étudiant devient éligible au rattrapage lorsqu'il reste des UE non
    validées après le calcul complet de la session normale.

    Args:
        academic_year: Nom de l'Academic Year
        semestre: "Semestre 1" ou "Semestre 2"
        filiere: Nom de la Field of study
        niveau: Nom du Field of study Level

    Returns:
        dict: liste des étudiants éligibles avec leurs UE concernées
    """
    try:
        return _etudiants_eligibles_rattrapage_impl(academic_year, semestre, filiere, niveau)
    except Exception:
        frappe.log_error(" retake etudiants_eligibles_rattrapage")
        frappe.throw(_("Erreur lors de la recherche des étudiants éligibles au rattrapage."))


def _etudiants_eligibles_rattrapage_impl(academic_year, semestre, filiere, niveau):
    sessions = frappe.get_all(
        "Session Examen",
        filters={
            "academic_year": academic_year,
            "semestre": semestre,
            "type_dexamen": TYPE_NORMALE,
        },
        pluck="name",
    )

    sessions_classe = []
    for name in sessions:
        existe_classe = frappe.db.exists(
            "Session Examen Field of study Level",
            {"parent": name, "filiere": filiere, "niveau": niveau},
        )
        if existe_classe:
            sessions_classe.append(name)

    if not sessions_classe:
        return {
            "academic_year": academic_year,
            "semestre": semestre,
            "filiere": filiere,
            "niveau": niveau,
            "etudiants": [],
            "total_eligibles": 0,
        }

    notes = frappe.get_all(
        "Session Examen Note",
        filters={"session_examen": ["in", sessions_classe], "statut": "Publié"},
        fields=[
            "name",
            "student",
            "teaching_unit",
            "note_cc_moyenne",
            "note_examen",
            "note_examen_rattrapage",
            "note_examen_active",
            "note_finale",
            "note_pct",
            "grade",
            "type_ue",
        ],
    )

    # Un étudiant est éligible s'il possède au moins une UE non validée.
    par_etudiant = {}
    for note in notes:
        student_doc = frappe.get_doc("Student", note.student)
        cycle = get_student_cycle(student_doc)
        seuil = get_seuil_validation(cycle)
        if note.note_pct is None or note.note_pct >= seuil:
            continue
        par_etudiant.setdefault(note.student, {
            "matricule": student_doc.matricule,
            "student_name": f"{student_doc.nom or ''} {student_doc.prenom or ''}".strip(),
            "cycle": cycle,
            "niveau": student_doc.niveau_actuel or "",
            "ue_concernees": [],
            "credits_concernee": 0,
        })
        par_etudiant[note.student]["ue_concernees"].append(
            _detail_ue_non_validee(note, student_doc, seuil)
        )
        par_etudiant[note.student]["credits_concernee"] += par_etudiant[note.student]["ue_concernees"][-1]["credits"]

    etudiants = []
    for student, info in par_etudiant.items():
        details = info["ue_concernees"]
        etudiants.append({
            "student": student,
            "matricule": info["matricule"],
            "student_name": info["student_name"],
            "cycle": info["cycle"],
            "niveau": info["niveau"],
            "semestre": semestre,
            "ue_concernees": [d["ue_name"] for d in details],
            "nb_ue_concernees": len(details),
            "credits_concernee": info["credits_concernee"],
            "statut": "À rattraper",
            "details": details,
        })

    etudiants.sort(key=lambda e: e["student_name"])

    return {
        "academic_year": academic_year,
        "semestre": semestre,
        "filiere": filiere,
        "niveau": niveau,
        "etudiants": etudiants,
        "total_eligibles": len(etudiants),
    }


@frappe.whitelist()
def creer_session_rattrapage(session_normale, date_debut, date_fin):
    """Crée une session de rattrapage basée sur les résultats d'une session normale.

    Les résultats de la session normale sont conservés : le rattrapage possède
    sa propre session et ses propres notes.

    Args:
        session_normale: Nom de la session normale
        date_debut: Date de début du rattrapage
        date_fin: Date de fin du rattrapage

    Returns:
        dict: Session de rattrapage créée
    """
    try:
        return _creer_session_rattrapage_impl(session_normale, date_debut, date_fin)
    except Exception:
        frappe.log_error(" retake creer_session_rattrapage")
        frappe.throw(_("Erreur lors de la création de la session de rattrapage."))


def _creer_session_rattrapage_impl(session_normale, date_debut, date_fin):
    session_normale_doc = frappe.get_doc("Session Examen", session_normale)

    rattrapage = frappe.new_doc("Session Examen")
    rattrapage.academic_year = session_normale_doc.academic_year
    rattrapage.calendar = session_normale_doc.calendar
    rattrapage.type_dexamen = "Examen de rattrapage"
    rattrapage.date_debut = date_debut
    rattrapage.date_de_fin = date_fin
    rattrapage.semestre = session_normale_doc.semestre

    for classe in session_normale_doc.classes_concernees:
        rattrapage.append(
            "classes_concernees",
            {
                "filiere": classe.filiere,
                "niveau": classe.niveau,
            },
        )

    rattrapage.insert()

    resultats = identifier_rattrapages(session_normale)

    return {
        "session_rattrapage": rattrapage.name,
        "nb_etudiants_concernes": resultats["total_eligibles"],
        "etudiants": resultats["etudiants_eligibles"],
    }
