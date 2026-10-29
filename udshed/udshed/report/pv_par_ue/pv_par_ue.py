# Copyright (c) 2026, Udshed and contributors
# For license information, please see license.txt

"""PV d'une UE : une colonne par matière, une ligne par étudiant.

Complémentaire au « PV Récapitulatif » de semestre, qui garde une colonne par
matière sur toute la promotion. Ici les colonnes sont restreintes aux matières
d'une UE et la note affichée est celle de l'UE (moyenne pondérée par les
crédits, meilleure note entre session normale et rattrapage).

Les données viennent de ``udshed.api.proces_verbal.get_pv_ue_data``, également
utilisée par le téléchargement PDF : l'écran et le PDF ne peuvent pas diverger.
"""

import frappe
from frappe import _

from udshed.api.proces_verbal import get_pv_ue_data

# Niveaux d'études proposés (alignés sur le doctype Field of study Level).
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

    pv = get_pv_ue_data(
        filters.academic_year,
        filters.filiere,
        filters.niveau,
        filters.semestre,
        filters.teaching_unit_value,
    )

    if not pv["matieres"]:
        frappe.throw(
            _("L'UE <b>{0}</b> n'a aucune matière dans cette classe pour l'année {1}.").format(
                filters.teaching_unit_value, filters.academic_year
            )
        )

    return _build_columns(pv["matieres"]), _build_rows(pv["matieres"], pv["etudiants"])


def _valider_filtres(filters):
    obligatoires = {
        "academic_year": "Année Académique",
        "semestre": "Semestre",
        "filiere": "Filière",
        "niveau": "Niveau / Classe",
        "teaching_unit_value": "UE",
    }
    manquants = [label for champ, label in obligatoires.items() if not filters.get(champ)]
    if manquants:
        frappe.throw(
            _("Veuillez renseigner les filtres obligatoires : {0}").format(", ".join(manquants))
        )


def _cle_matiere(teaching_unit):
    """Clé de colonne associée à une matière (unique et stable)."""
    return "mat_{0}".format(teaching_unit)


def _build_columns(matieres):
    """N° / Matricule / Nom, une colonne par matière, puis la synthèse UE."""
    columns = [
        {"fieldname": "num", "label": _("N°"), "fieldtype": "Int", "width": 40},
        {"fieldname": "matricule", "label": _("Matricule"), "fieldtype": "Data", "width": 100},
        {"fieldname": "student_name", "label": _("Nom complet"), "fieldtype": "Data", "width": 200},
    ]

    for matiere in matieres:
        columns.append(
            {
                "fieldname": _cle_matiere(matiere["teaching_unit"]),
                "label": matiere["code"] or matiere["intitule"],
                "fieldtype": "Percent",
                "options": "Number",
                "width": 70,
                "precision": 2,
            }
        )

    columns += [
        {
            "fieldname": "note_ue_pct",
            "label": _("Note UE"),
            "fieldtype": "Percent",
            "options": "Number",
            "width": 80,
            "precision": 2,
        },
        {"fieldname": "grade", "label": _("Grade"), "fieldtype": "Data", "width": 60},
        {"fieldname": "point", "label": _("Points"), "fieldtype": "Float", "width": 60, "precision": 2},
        {
            "fieldname": "credits_obtenus",
            "label": _("Crédits obtenus"),
            "fieldtype": "Float",
            "width": 90,
            "precision": 2,
        },
        {"fieldname": "statut", "label": _("Statut"), "fieldtype": "Data", "width": 100},
    ]

    return columns


def _build_rows(matieres, etudiants):
    """Une ligne par étudiant, avec la note de chaque matière puis l'UE."""
    data = []
    for num, et in enumerate(etudiants, 1):
        row = {
            "num": num,
            "matricule": et["matricule"],
            "student_name": "{} {}".format(et["nom"] or "", et["prenom"] or "").strip(),
            "note_ue_pct": et["note_ue_pct"],
            "grade": et["grade"],
            "point": et["point"],
            "credits_obtenus": et["credits_obtenus"],
            "statut": et["statut"],
            # Non affiché en colonne, mais lu par le `formatter` pour colorer la
            # note UE : sans ce seuil, toute note calculée ressortirait verte.
            "seuil_validation": et["seuil_validation"],
        }
        for matiere in matieres:
            note = (et["notes"] or {}).get(matiere["teaching_unit"]) or {}
            row[_cle_matiere(matiere["teaching_unit"])] = note.get("note_pct")
        data.append(row)
    return data
