# Copyright (c) 2026, Udshed and contributors
# For license information, please see license.txt

"""API de la page « Procès-Verbal récapitulatif ».

Génère le procès-verbal d'une classe (filière + niveau) pour un semestre :
résultats de session normale par UE, bilan semestriel (crédits, MPS, MPC,
statut) et statistiques de réussite. Seules les données réelles de
l'application sont utilisées (réinscriptions validées, notes publiées,
grille de grades, résultats calculés par le moteur).
"""

import frappe
from frappe import _

from udshed.grade_calculation import get_seuil_validation, get_student_cycle
from udshed.api.saisie_notes import _get_etudiants, _get_niveau_name, get_ues

TYPE_NORMALE = "Examen de session normal"
STATUT_NOTE_PUBLIE = "Publié"


# ---------------------------------------------------------------------- #
#  Accès aux données
# ---------------------------------------------------------------------- #
def _sessions_normales(academic_year, filiere, niveau, semestre):
    """Sessions « Examen de session normal » couvrant la classe (filière, niveau)."""
    niveau_name = _get_niveau_name(filiere, niveau)
    sessions = frappe.get_all(
        "Session Examen",
        filters={
            "academic_year": academic_year,
            "semestre": semestre,
            "type_dexamen": TYPE_NORMALE,
        },
        pluck="name",
    )
    out = []
    for session in sessions:
        if frappe.db.exists(
            "Session Examen Field of study Level",
            {"parent": session, "filiere": filiere, "niveau": niveau_name},
        ):
            out.append(session)
    return out


def _notes_normales(academic_year, filiere, niveau, semestre):
    """Notes publiées de session normale, indexées par (student, teaching_unit)."""
    sessions = _sessions_normales(academic_year, filiere, niveau, semestre)
    if not sessions:
        return {}

    notes = frappe.get_all(
        "Session Examen Note",
        filters={
            "session_examen": ["in", sessions],
            "statut": STATUT_NOTE_PUBLIE,
        },
        fields=["student", "teaching_unit", "note_finale", "note_pct", "grade", "point"],
    )
    return {(n.student, n.teaching_unit): n for n in notes}


def _credits_ue(teaching_unit, filiere, niveau):
    """Crédits d'une UE pour le niveau de la classe (course_levels, sinon champ credits)."""
    niveau_name = _get_niveau_name(filiere, niveau)
    poid = frappe.db.get_value(
        "Course Field of study level item",
        {"parent": teaching_unit, "filiere": filiere, "niveau": niveau_name},
        "course_poid",
    )
    if poid:
        return int(poid)
    return int(frappe.db.get_value("Teaching Unit", teaching_unit, "credits") or 0)


def _etudiants_classe(academic_year, filiere, niveau, ues):
    """Union (triée par matricule) des étudiants inscrits aux UE du semestre.

    Reprend la logique de la Saisie des notes : réinscription « Validée »
    pour l'année/filière/niveau et statut « Inscrit » à l'UE.
    """
    resultats = []
    vus = set()
    for ue in ues:
        for et in _get_etudiants(academic_year, filiere, niveau, ue["name"]):
            if et["student"] in vus:
                continue
            vus.add(et["student"])
            resultats.append(et)
    resultats.sort(key=lambda s: (s.get("matricule") or s["student"]).lower())
    return resultats


def _mpc_etudiant(student, academic_year, semestre):
    """MPC d'un étudiant depuis Resultat Semestre (si calculé par le moteur)."""
    return frappe.db.get_value(
        "Resultat Semestre",
        {
            "student": student,
            "academic_year": academic_year,
            "semestre": semestre,
        },
        "mpc",
    )


# ---------------------------------------------------------------------- #
#  Données du procès-verbal
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def get_proces_verbal_data(academic_year, filiere, niveau, semestre):
    """Construit les données du procès-verbal d'une classe pour un semestre.

    Args:
        academic_year: Nom de l'Academic Year
        filiere: Nom de la Field of study
        niveau: Label du niveau (ex : "Licence 1")
        semestre: "Semestre 1" ou "Semestre 2"

    Returns:
        dict: contexte, ues, etudiants (avec résultats et bilan), statistiques
    """
    ues = get_ues(academic_year, filiere, niveau, semestre)
    ue_liste = []
    for ue in ues:
        ue_liste.append(
            {
                "name": ue["name"],
                "code": ue["code"],
                "intitule": ue["intitule"],
                "credits": _credits_ue(ue["name"], filiere, niveau),
            }
        )

    if not ue_liste:
        return {
            "context": _contexte(academic_year, filiere, niveau, semestre),
            "ues": [],
            "etudiants": [],
            "statistiques": {},
        }

    etudiants = _etudiants_classe(academic_year, filiere, niveau, ues)
    notes = _notes_normales(academic_year, filiere, niveau, semestre)

    total_credits = sum(u["credits"] for u in ue_liste)

    lignes = []
    for et in etudiants:
        student = et["student"]
        cycle = get_student_cycle(student)
        seuil = get_seuil_validation(cycle)

        resultats = {}
        credits_obtenus = 0
        somme_cj_pj = 0
        somme_cj = 0

        for ue in ue_liste:
            note = notes.get((student, ue["name"]))
            if not note:
                resultats[ue["name"]] = {
                    "note_finale": None,
                    "note_pct": None,
                    "grade": "",
                    "point": None,
                    "valide": False,
                }
                continue

            note_pct = note.note_pct
            valide = bool(note_pct is not None and note_pct >= seuil)
            resultats[ue["name"]] = {
                "note_finale": note.note_finale,
                "note_pct": note_pct,
                "grade": note.grade or "",
                "point": note.point,
                "valide": valide,
            }
            cj = ue["credits"]
            if valide:
                credits_obtenus += cj
            somme_cj += cj
            somme_cj_pj += cj * (note.point or 0)

        mps = round(somme_cj_pj / somme_cj, 2) if somme_cj > 0 else 0
        pct_validation = round(credits_obtenus / total_credits * 100, 2) if total_credits else 0

        if somme_cj > 0:
            statut = "Admis" if mps >= seuil else "Ajourné"
        else:
            statut = "En attente"

        lignes.append(
            {
                "student": student,
                "matricule": et.get("matricule") or student,
                "nom": et.get("nom") or "",
                "prenom": et.get("prenom") or "",
                "resultats": resultats,
                "total_credits": total_credits,
                "credits_obtenus": credits_obtenus,
                "pct_validation": pct_validation,
                "mps": mps,
                "mpc": _mpc_etudiant(student, academic_year, semestre),
                "statut": statut,
            }
        )

    statistiques = _statistiques(ue_liste, lignes)

    return {
        "context": _contexte(academic_year, filiere, niveau, semestre),
        "ues": ue_liste,
        "etudiants": lignes,
        "statistiques": statistiques,
    }


def _contexte(academic_year, filiere, niveau, semestre):
    """Contexte d'en-tête du PV (école, classe, référence)."""
    settings = frappe.get_single("Udshed Setting")
    return {
        "academic_year": academic_year,
        "year_label": frappe.get_cached_value("Academic Year", academic_year, "year_name")
        or academic_year,
        "filiere": filiere,
        "filiere_name": frappe.get_cached_value("Field of study", filiere, "name_of_field")
        or filiere,
        "niveau": niveau,
        "semestre": semestre,
        "school_name": settings.school_name or "",
        "school_logo": settings.school_logo or "",
        "date_emission": frappe.utils.today(),
        "reference_no": "PV-{0}-{1}-{2}".format(
            filiere.replace("/", "-"),
            niveau.replace(" ", "-"),
            frappe.utils.today().replace("-", ""),
        ),
    }


def _statistiques(ue_liste, lignes):
    """Statistiques de réussite : taux global et taux par UE."""
    admis = sum(1 for l in lignes if l["statut"] == "Admis")
    taux_global = round(admis / len(lignes) * 100, 2) if lignes else 0

    taux_par_ue = {}
    for ue in ue_liste:
        validees = sum(1 for l in lignes if l["resultats"].get(ue["name"], {}).get("valide"))
        presentes = sum(
            1
            for l in lignes
            if l["resultats"].get(ue["name"], {}).get("note_pct") is not None
        )
        taux_par_ue[ue["name"]] = {
            "presentes": presentes,
            "validees": validees,
            "taux": round(validees / presentes * 100, 2) if presentes else 0,
        }

    return {
        "total_etudiants": len(lignes),
        "admis": admis,
        "ajournes": len(lignes) - admis,
        "taux_reussite": taux_global,
        "taux_par_ue": taux_par_ue,
    }


# ---------------------------------------------------------------------- #
#  Export PDF
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def download_proces_verbal_pdf(academic_year, filiere, niveau, semestre):
    """Génère et télécharge le procès-verbal (PDF, format paysage) d'une classe."""
    data = get_proces_verbal_data(academic_year, filiere, niveau, semestre)
    if not data["ues"]:
        frappe.throw(_("Aucune UE trouvée pour ces critères."))
    if not data["etudiants"]:
        frappe.throw(_("Aucun étudiant inscrit pour ces critères."))

    try:
        from weasyprint import HTML

        template_path = frappe.get_app_path(
            "udshed", "public", "print_templates", "proces_verbal.html"
        )
        with open(template_path, encoding="utf-8") as f:
            template = f.read()

        html = frappe.render_template(template, {"data": data})
        pdf = HTML(string=html, base_url=frappe.utils.get_url()).write_pdf()
    except Exception:
        frappe.log_error(" proces_verbal download_proces_verbal_pdf")
        frappe.throw(_("Erreur lors de la génération du procès-verbal PDF."))

    nom = "PV_{0}_{1}_{2}_{3}.pdf".format(
        filiere.replace("/", "-"),
        niveau.replace(" ", "-"),
        semestre.replace(" ", ""),
        academic_year.replace("/", "-"),
    )
    frappe.response["filename"] = nom
    frappe.response["filecontent"] = pdf
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/pdf"
