# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe

from udshed.api.retake import etudiants_eligibles_rattrapage


def get_report_filters():
    return [
        {
            "fieldname": "academic_year",
            "label": "Année académique",
            "fieldtype": "Link",
            "options": "Academic Year",
            "reqd": 1,
        },
        {
            "fieldname": "semestre",
            "label": "Semestre",
            "fieldtype": "Select",
            "options": "Semestre 1\nSemestre 2",
            "reqd": 1,
        },
        {
            "fieldname": "filiere",
            "label": "Filière",
            "fieldtype": "Link",
            "options": "Field of study",
            "reqd": 1,
        },
        {
            "fieldname": "niveau",
            "label": "Niveau",
            "fieldtype": "Link",
            "options": "Field of study Level",
            "reqd": 1,
        },
    ]


def get_columns():
    return [
        {"label": "Matricule", "fieldname": "matricule", "fieldtype": "Data", "width": 110},
        {"label": "Nom complet", "fieldname": "student_name", "fieldtype": "Data", "width": 220},
        {"label": "Cycle", "fieldname": "cycle", "fieldtype": "Data", "width": 90},
        {"label": "Niveau", "fieldname": "niveau", "fieldtype": "Data", "width": 90},
        {"label": "Semestre", "fieldname": "semestre", "fieldtype": "Data", "width": 110},
        {"label": "UE concernée", "fieldname": "ue_name", "fieldtype": "Data", "width": 220},
        {"label": "Crédits", "fieldname": "credits", "fieldtype": "Int", "width": 70},
        {"label": "Note session normale (%)", "fieldname": "note_session_normale", "fieldtype": "Percent", "width": 140},
        {"label": "Statut", "fieldname": "statut", "fieldtype": "Data", "width": 110},
    ]


def execute(filters=None):
    filters = filters or {}
    if not (filters.get("academic_year") and filters.get("semestre")
            and filters.get("filiere") and filters.get("niveau")):
        return get_columns(), []

    data = etudiants_eligibles_rattrapage(
        filters["academic_year"],
        filters["semestre"],
        filters["filiere"],
        filters["niveau"],
    )

    rows = []
    for etudiant in data.get("etudiants", []):
        for detail in etudiant.get("details", []):
            rows.append({
                "matricule": etudiant.get("matricule"),
                "student_name": etudiant.get("student_name"),
                "cycle": etudiant.get("cycle"),
                "niveau": etudiant.get("niveau"),
                "semestre": etudiant.get("semestre"),
                "ue_name": detail.get("ue_name"),
                "credits": detail.get("credits"),
                "note_session_normale": detail.get("note_session_normale"),
                "statut": "À rattraper",
            })

    return get_columns(), rows
