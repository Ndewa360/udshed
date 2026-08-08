# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Procès-Verbal de Classe (PV Récapitulatif).

Rapport de type Script Report qui présente, pour une classe
(filière + niveau), une année académique et un semestre donnés,
le récapitulatif des résultats de tous les étudiants :
  - une colonne par UE du semestre (avec le grade obtenu),
  - les colonnes de synthèse : TCI, TCC, % de validation,
    MPS, MPC et Mention.

Les calculs MPS / MPC / crédits réutilisent les fonctions déjà
implémentées du moteur de calcul (udshed.api.resultat_academique).
"""

import frappe
from frappe import _

from udshed.api.resultat_academique import calculer_mps

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

    students = _get_students(filters)
    ue_list = _get_ue_list(students, filters)

    columns = _build_columns(ue_list)
    data = _build_rows(students, ue_list, filters)

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
# Récupération des données
# ---------------------------------------------------------------------------

def _get_students(filters):
    """Retourne les étudiants de la classe (filière + niveau), triés par matricule."""
    return frappe.get_all(
        "Student",
        filters={
            "filiere": filters.filiere,
            "niveau_actuel": filters.niveau,
        },
        fields=["name", "matricule", "nom", "prenom", "cycle"],
        order_by="matricule asc",
    )


def _get_ue_list(students, filters):
    """Retourne les UE du semestre ayant des résultats pour la classe.

    La liste est construite à partir des Resultat Academique des étudiants
    de la classe (ce sont les UE réellement évaluées), puis triée par code
    de cours. Elle alimente les colonnes dynamiques du rapport.

    Args:
        students (list[dict]): Étudiants de la classe
        filters (frappe._dict): Filtres du rapport

    Returns:
        list[dict]: [{name, code, label}] trié par code
    """
    ues = {}
    for stu in students:
        rows = frappe.get_all(
            "Resultat Academique",
            filters={
                "student": stu.name,
                "academic_year": filters.academic_year,
                "semestre": filters.semestre,
            },
            fields=["teaching_unit", "ue_name"],
        )
        for row in rows:
            if row.teaching_unit and row.teaching_unit not in ues:
                ues[row.teaching_unit] = row.ue_name or row.teaching_unit

    ue_list = []
    for tu, label in ues.items():
        # Le code du cours (nom de la Course) sert d'en-tête de colonne
        code = frappe.get_cached_value("Teaching Unit", tu, "course") or tu
        ue_list.append({"name": tu, "code": code, "label": label})

    ue_list.sort(key=lambda ue: ue["code"])
    return ue_list


def _get_student_ue_results(student, filters):
    """Retourne les résultats par UE d'un étudiant pour le semestre.

    Returns:
        dict: {teaching_unit: doc Resultat Academique}
    """
    rows = frappe.get_all(
        "Resultat Academique",
        filters={
            "student": student,
            "academic_year": filters.academic_year,
            "semestre": filters.semestre,
        },
        fields=["teaching_unit", "note_finale", "note_pct", "grade", "statut"],
    )
    return {r.teaching_unit: r for r in rows}


def _get_synthese(student, filters):
    """Calcule les colonnes de synthèse d'un étudiant (TCI, TCC, MPS, MPC, mention).

    On privilégie le Resultat Semestre déjà sauvegardé (généré par le moteur
    de calcul). S'il n'existe pas encore, on calcule la MPS à la volée avec
    la fonction existante ``calculer_mps``.

    Returns:
        dict: {tci, tcc, pct_validation, mps, mpc, mention}
    """
    sem_res = frappe.db.get_value(
        "Resultat Semestre",
        {
            "student": student,
            "academic_year": filters.academic_year,
            "semestre": filters.semestre,
        },
        ["total_credits", "credits_obtenus", "mps", "mpc", "mention"],
        as_dict=True,
    )

    if sem_res and sem_res.get("total_credits"):
        tci = sem_res.total_credits or 0
        tcc = sem_res.credits_obtenus or 0
        mps = sem_res.mps or 0
        mpc = sem_res.mpc or 0
        mention = sem_res.mention or _determine_mention(mps)
    else:
        # Repli : calcul à la volée à partir des Resultat Academique
        mps_data = calculer_mps(
            student, filters.semestre, filters.academic_year
        )
        tci = mps_data.get("total_credits", 0)
        tcc = mps_data.get("credits_obtenus", 0)
        mps = mps_data.get("mps", 0)
        mpc = 0  # la MPC nécessite les semestres précédents sauvegardés
        mention = _determine_mention(mps)

    pct_validation = round(tcc / tci * 100, 2) if tci else 0

    return {
        "tci": tci,
        "tcc": tcc,
        "pct_validation": pct_validation,
        "mps": mps,
        "mpc": mpc,
        "mention": mention,
    }


def _determine_mention(mps):
    """Détermine la mention à partir de la MPS et de la grille des grades."""
    setting = frappe.get_single("Udshed Setting")
    for g in setting.grille_grades:
        if g.note_min <= (mps or 0) <= g.note_max:
            return g.mention or ""
    return ""


# ---------------------------------------------------------------------------
# Construction des colonnes et des lignes
# ---------------------------------------------------------------------------

def _ue_key(teaching_unit):
    """Clé de colonne associée à une UE (doit être unique et stable)."""
    return f"ue_{teaching_unit}"


def _build_columns(ue_list):
    """Construit la liste des colonnes du rapport (UE dynamiques incluses)."""
    columns = [
        {"fieldname": "num", "label": _("N°"), "fieldtype": "Int", "width": 45},
        {"fieldname": "matricule", "label": _("Matricule"), "fieldtype": "Data", "width": 110},
        {"fieldname": "student_name", "label": _("Nom complet"), "fieldtype": "Data", "width": 220},
    ]

    # Une colonne par UE du semestre (l'en-tête est le code du cours)
    for ue in ue_list:
        columns.append({
            "fieldname": _ue_key(ue["name"]),
            "label": ue["code"] or ue["name"],
            "fieldtype": "Data",
            "width": 65,
        })

    columns += [
        {"fieldname": "tci", "label": _("TCI"), "fieldtype": "Int", "width": 60},
        {"fieldname": "tcc", "label": _("TCC"), "fieldtype": "Int", "width": 60},
        {"fieldname": "pct_validation", "label": _("% Validation"), "fieldtype": "Float", "width": 90, "precision": 2},
        {"fieldname": "mps", "label": _("MPS"), "fieldtype": "Float", "width": 70, "precision": 2},
        {"fieldname": "mpc", "label": _("MPC"), "fieldtype": "Float", "width": 70, "precision": 2},
        {"fieldname": "mention", "label": _("Mention"), "fieldtype": "Data", "width": 110},
    ]

    return columns


def _build_rows(students, ue_list, filters):
    """Construit les lignes du rapport (une par étudiant)."""
    data = []
    for num, stu in enumerate(students, 1):
        row = {
            "num": num,
            "matricule": stu.matricule or "",
            "student_name": f"{stu.nom or ''} {stu.prenom or ''}".strip(),
        }

        ue_results = _get_student_ue_results(stu.name, filters)

        # Valeurs des UE (grade obtenu, sinon la note %) + indicateur de non-validation
        for ue in ue_list:
            key = _ue_key(ue["name"])
            res = ue_results.get(ue["name"])
            if res:
                row[key] = res.grade or res.note_pct or ""
                row[f"{key}_non_valide"] = 1 if res.statut == "Non Validé" else 0
            else:
                row[key] = ""
                row[f"{key}_non_valide"] = 0

        # Colonnes de synthèse
        row.update(_get_synthese(stu.name, filters))

        data.append(row)

    return data
