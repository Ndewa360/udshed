# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _


@frappe.whitelist()
def identifier_rattrapages(session_examen):
    """Identifie tous les étudiants et UE non validés pour une session d'examen.

    Args:
        session_examen: Nom du document Session Examen

    Returns:
        dict: {
            "session": session_examen,
            "etudiants": [
                {
                    "student": "STU-001",
                    "student_name": "Jean Dupont",
                    "teaching_unit": "UE-001",
                    "ue_name": "Mathématiques",
                    "note_pct": 45.0,
                    "seuil": 50.0,
                    "cycle": "Licence",
                    "note_cc_moyenne": 12.0,
                    "note_examen": 7.0,
                    "note_finale": 8.5,
                    "grade": "F",
                },
                ...
            ],
            "total_etudiants": 100,
            "total_non_valides": 15,
        }
    """
    session = frappe.get_doc("Session Examen", session_examen)
    setting = frappe.get_single("Udshed Setting")

    filters = {
        "session_examen": session_examen,
        "statut": "Publié",
    }

    notes = frappe.get_all(
        "Session Examen Note",
        filters=filters,
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

    etudiants_non_valides = []
    total = len(notes)

    for note in notes:
        student_doc = frappe.get_doc("Student", note.student)
        cycle = student_doc.cycle or "Licence"

        if cycle == "Licence":
            seuil = setting.seuil_validation_licence or 50
        else:
            seuil = setting.seuil_validation_master or 60

        if note.note_pct < seuil:
            teaching_unit_doc = frappe.get_doc("Teaching Unit", note.teaching_unit)
            course_name = ""
            if teaching_unit_doc.course:
                course_name = frappe.db.get_value(
                    "Course", teaching_unit_doc.course, "intitule"
                )

            etudiants_non_valides.append({
                "name": note.name,
                "student": note.student,
                "student_name": f"{student_doc.nom} {student_doc.prenom}",
                "teaching_unit": note.teaching_unit,
                "ue_name": course_name or note.teaching_unit,
                "note_cc_moyenne": note.note_cc_moyenne,
                "note_examen": note.note_examen,
                "note_examen_rattrapage": note.note_examen_rattrapage,
                "note_examen_active": note.note_examen_active,
                "note_finale": note.note_finale,
                "note_pct": note.note_pct,
                "grade": note.grade,
                "cycle": cycle,
                "seuil": seuil,
                "type_ue": note.type_ue,
            })

    return {
        "session": session_examen,
        "annee_academique": session.academic_year,
        "semestre": session.semestre,
        "type_session": session.type_dexamen,
        "etudiants": etudiants_non_valides,
        "total_etudiants": total,
        "total_non_valides": len(etudiants_non_valides),
    }


@frappe.whitelist()
def creer_session_rattrapage(session_normale, date_debut, date_fin):
    """Crée une session de rattrapage basée sur les résultats d'une session normale.

    Args:
        session_normale: Nom de la session normale
        date_debut: Date de début du rattrapage
        date_fin: Date de fin du rattrapage

    Returns:
        dict: Session de rattrapage créée
    """
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
        "nb_etudiants_concernes": resultats["total_non_valides"],
        "etudiants": resultats["etudiants"],
    }
