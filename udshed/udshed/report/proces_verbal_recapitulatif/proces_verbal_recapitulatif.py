# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Procès-Verbal de Classe (PV Récapitulatif).

Rapport de type Script Report qui présente, pour une classe
(filière + niveau), une année académique et un semestre donnés,
le récapitulatif des résultats de tous les étudiants :
  - trois colonnes par UE du semestre (Note %, Grade, Point),
  - les colonnes de synthèse : TCI, TCC, % de validation,
    MPS, MPC et Statut (délibération de session normale).

Les données proviennent de la fonction unique
``udshed.api.proces_verbal.get_proces_verbal_data`` : étudiants
réinscrits validés et inscrits aux UE, notes de session normale
publiées, bilan recalculé sur ces notes. Le même jeu de données
alimente l'export PDF paysage (logo, filigrane, signatures).
"""

import frappe
from frappe import _

from udshed.api.proces_verbal import get_proces_verbal_data

# Niveaux d'études proposés (alignés sur le doctype Field of study Level)
NIVEAUX = [
    "Licence 1",
    "Licence 2",
    "Licence 3",
    "BTS 1",
    "BTS 2",
    "Master 1",
    "Master 2",
]


def execute(filters=None):
    """Point d'entrée du Script Report : retourne (columns, data)."""
    filters = frappe._dict(filters or {})

    _valider_filtres(filters)

    pv = get_proces_verbal_data(
        filters.academic_year, filters.filiere, filters.niveau, filters.semestre
    )

    columns = _build_columns(pv["ues"])
    data = _build_rows(pv["ues"], pv["etudiants"])

    return columns, data


# ---------------------------------------------------------------------------
# Filtres
# ---------------------------------------------------------------------------

def _valider_filtres(filters):
    """Vérifie que tous les filtres obligatoires sont renseignés."""
    obligatoires = {
        "academic_year": "Année Académique",
        "semestre": "Semestre",
        "filiere": "Filière",
        "niveau": "Niveau / Classe",
    }
    manquants = [
        label for champ, label in obligatoires.items() if not filters.get(champ)
    ]
    if manquants:
        frappe.throw(
            _("Veuillez renseigner les filtres obligatoires : {0}").format(
                ", ".join(manquants)
            )
        )


# ---------------------------------------------------------------------------
# Construction des colonnes et des lignes
# ---------------------------------------------------------------------------

def _ue_key(teaching_unit):
    """Clé de colonne associée à une UE (doit être unique et stable)."""
    return f"ue_{teaching_unit}"


def _build_columns(ues):
    """Construit la liste des colonnes du rapport (UE dynamiques incluses)."""
    columns = [
        {"fieldname": "num", "label": _("N°"), "fieldtype": "Int", "width": 40},
        {"fieldname": "matricule", "label": _("Matricule"), "fieldtype": "Data", "width": 110},
        {"fieldname": "student_name", "label": _("Nom complet"), "fieldtype": "Data", "width": 220},
    ]

    columns += [
        {"fieldname": "sem_ant_mpc", "label": _("SEM N-1 MPC"), "fieldtype": "Float", "width": 70, "precision": 2},
        {"fieldname": "sem_ant_tcc", "label": _("SEM N-1 TCC"), "fieldtype": "Int", "width": 60},
    ]

    # Quatre colonnes par UE : Note %, Grade, Point et Mention
    for ue in ues:
        key = _ue_key(ue["name"])
        columns += [
            {
                "fieldname": f"{key}_note",
                "label": ue["code"] or ue["name"],
                "fieldtype": "Float",
                "width": 70,
                "precision": 2,
            },
            {"fieldname": f"{key}_grade", "label": _("Gr"), "fieldtype": "Data", "width": 45},
            {"fieldname": f"{key}_point", "label": _("Pt"), "fieldtype": "Float", "width": 50, "precision": 2},
            {"fieldname": f"{key}_mention", "label": _("Mention"), "fieldtype": "Data", "width": 130},
        ]

    columns += [
        {"fieldname": "tci", "label": _("TCI"), "fieldtype": "Int", "width": 60},
        {"fieldname": "tcc", "label": _("TCC"), "fieldtype": "Int", "width": 60},
        {"fieldname": "pct_validation", "label": _("% Validation"), "fieldtype": "Float", "width": 90, "precision": 2},
        {"fieldname": "mps", "label": _("MPS"), "fieldtype": "Float", "width": 70, "precision": 2},
        {"fieldname": "mpc", "label": _("MPC"), "fieldtype": "Float", "width": 70, "precision": 2},
        {"fieldname": "statut", "label": _("Statut"), "fieldtype": "Data", "width": 100},
    ]

    return columns


def _build_rows(ues, etudiants):
    """Construit les lignes du rapport (une par étudiant)."""
    data = []
    for num, et in enumerate(etudiants, 1):
        row = {
            "num": num,
            "matricule": et["matricule"],
            "student_name": f"{et['nom'] or ''} {et['prenom'] or ''}".strip(),
        }

        for ue in ues:
            key = _ue_key(ue["name"])
            r = (et["resultats"] or {}).get(ue["name"]) or {}
            note = r.get("note_pct")
            row[f"{key}_note"] = note
            row[f"{key}_grade"] = r.get("grade") or ""
            row[f"{key}_point"] = r.get("point")
            row[f"{key}_mention"] = r.get("mention") or ""
            row[f"{key}_non_valide"] = (
                1 if (note is not None and not r.get("valide")) else 0
            )

        row["sem_ant_mpc"] = et.get("sem_ant_mpc")
        row["sem_ant_tcc"] = et.get("sem_ant_tcc")
        row["tci"] = et["total_credits"]
        row["tcc"] = et["credits_obtenus"]
        row["pct_validation"] = et["pct_validation"]
        row["mps"] = et["mps"]
        row["mpc"] = et["mpc"]
        row["statut"] = et["statut"]

        data.append(row)

    return data
