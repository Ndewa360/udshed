# Copyright (c) 2026, Udshed and contributors
# For license information, please see license.txt

"""API de la page « Procès-Verbal récapitulatif »."""

import re

import frappe
from frappe import _
from frappe.utils import flt

from udshed.grade_calculation import get_seuil_validation, get_student_cycle
from udshed.api.saisie_notes import _get_etudiants, _get_niveau_name, get_ues

TYPE_NORMALE = "Examen de session normal"
STATUT_NOTE_PUBLIE = "Publié"


def _sessions_normales(academic_year, filiere, niveau, semestre):
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
    sessions = _sessions_normales(academic_year, filiere, niveau, semestre)
    if not sessions:
        return {}
    notes = frappe.get_all(
        "Session Examen Note",
        filters={
            "session_examen": ["in", sessions],
            "statut": STATUT_NOTE_PUBLIE,
        },
        fields=[
            "student", "teaching_unit", "note_finale", "note_pct",
            "grade", "point", "mention", "type_resultat", "capitalise",
        ],
    )
    return {(n.student, n.teaching_unit): n for n in notes}


def _credits_ue(teaching_unit, filiere, niveau):
    niveau_name = _get_niveau_name(filiere, niveau)
    poid = frappe.db.get_value(
        "Course Field of study level item",
        {"parent": teaching_unit, "filiere": filiere, "niveau": niveau_name},
        "course_poid",
    )
    if poid:
        return float(poid)
    return int(frappe.db.get_value("Teaching Unit", teaching_unit, "credits") or 0)


def _etudiants_classe(academic_year, filiere, niveau, ues):
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


MENTION_COURTE = {
    "Excellent / Très Honorable avec Félicitations du Jury": "E",
    "Très Bien / Très Honorable": "TB",
    "Très Bien": "TB",
    "Assez Bien": "AB",
    "Passable": "P",
    "Insuffisant": "I",
    "Échec": "E",
}


def _mention_courte(mention):
    if not mention:
        return ""
    return MENTION_COURTE.get(mention) or mention


def _numero_semestre_cycle(niveau_label, semestre):
    match = re.search(r"(\d+)", niveau_label or "")
    rang = int(match.group(1)) if match else 1
    base = 6 if "master" in (niveau_label or "").lower() else 0
    part = 1 if str(semestre or "").strip().endswith("1") else 2
    return base + (rang - 1) * 2 + part


def _mps_rs_sur_4(rs_mps):
    """Convertit la MPS d'un Resultat Semestre en échelle 0–4.

    La MPS stockée dans Resultat Semestre est en pourcentage (0–100).
    Garde-fou : si la valeur est déjà <= 4, elle est considérée sur 4.
    """
    v = float(rs_mps or 0)
    if v <= 4.0:
        return round(v, 2)
    return round(v / 25.0, 2)


def _bilan_pv_etudiant(student, academic_year, semestre, mps_sur_4, total_credits, credits_obtenus, pct_validation):
    rows = frappe.get_all(
        "Resultat Semestre",
        filters={"student": student},
        fields=[
            "semester_index", "academic_year", "semestre", "mps", "mpc",
            "total_credits", "credits_obtenus", "mention",
        ],
        order_by="semester_index asc",
    )

    if not rows:
        return {
            "mpc": None,
            "mention_short": "",
            "sem_ant_mpc": None,
            "sem_ant_tcc": None,
            "cycle_tci": total_credits,
            "cycle_tcc": credits_obtenus,
            "cycle_pct": pct_validation,
        }

    current = next(
        (r for r in rows if r.academic_year == academic_year and r.semestre == semestre),
        None,
    )
    index = current.semester_index if current else max(r.semester_index for r in rows)
    sem_ant = next((r for r in rows if r.semester_index == index - 1), None)

    mpc = 0
    mpc_ant = None
    for r in rows:
        i = r.semester_index
        if i > index:
            continue
        is_current = (
            current is not None
            and r.semester_index == current.semester_index
        )
        mps_i = mps_sur_4 if is_current else _mps_rs_sur_4(r.mps)
        mpc_avant = mpc
        if i == 1:
            mpc = mps_i
        else:
            mpc = round((mpc * (i - 1) + mps_i) / i, 2)
        if is_current:
            mpc_ant = mpc_avant

    cycle_rows = [r for r in rows if r.semester_index <= index]
    cycle_tci = sum(r.total_credits or 0 for r in cycle_rows)
    cycle_tcc = sum(r.credits_obtenus or 0 for r in cycle_rows)

    if sem_ant:
        if mpc_ant is not None:
            sem_ant_mpc = mpc_ant
        elif sem_ant.mpc is not None:
            sem_ant_mpc = _mps_rs_sur_4(sem_ant.mpc)
        else:
            sem_ant_mpc = None
    else:
        sem_ant_mpc = None

    return {
        "mpc": round(mpc, 2) if current else None,
        "mention_short": _mention_courte(current.mention if current else ""),
        "sem_ant_mpc": sem_ant_mpc,
        "sem_ant_tcc": sem_ant.credits_obtenus if sem_ant else None,
        "cycle_tci": cycle_tci or total_credits,
        "cycle_tcc": cycle_tcc,
        "cycle_pct": round(cycle_tcc / cycle_tci * 100, 2) if cycle_tci else pct_validation,
    }


@frappe.whitelist()
def get_proces_verbal_data(academic_year, filiere, niveau, semestre):
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
        somme_cj = 0
        somme_cj_pct = 0
        somme_cj_pts = 0

        for ue in ue_liste:
            note = notes.get((student, ue["name"]))
            if not note:
                resultats[ue["name"]] = {
                    "note_finale": None,
                    "note_pct": None,
                    "grade": "",
                    "point": None,
                    "mention": "",
                    "type_resultat": "",
                    "capitalise": False,
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
                "mention": note.mention or "",
                "type_resultat": note.type_resultat or "",
                "capitalise": bool(note.capitalise),
                "valide": valide,
            }
            cj = ue["credits"]
            if valide:
                credits_obtenus += cj
            somme_cj += cj
            somme_cj_pct += cj * (note_pct or 0)
            somme_cj_pts += cj * (note.point or 0)

        mps_pct = round(somme_cj_pct / somme_cj, 2) if somme_cj > 0 else 0
        mps = round(somme_cj_pts / somme_cj, 2) if somme_cj > 0 else 0
        pct_validation = round(credits_obtenus / total_credits * 100, 2) if total_credits else 0

        if somme_cj > 0:
            statut = "Admis" if mps_pct >= seuil else "Ajourné"
        else:
            statut = "En attente"

        bilan = _bilan_pv_etudiant(
            student, academic_year, semestre, mps,
            total_credits, credits_obtenus, pct_validation,
        )

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
                "mps_pct": mps_pct,
                "statut": statut,
                **bilan,
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
    settings = frappe.get_single("Udshed Setting")
    return {
        "academic_year": academic_year,
        "year_label": frappe.get_cached_value("Academic Year", academic_year, "year_name")
        or academic_year,
        "filiere": filiere,
        "filiere_name": frappe.get_cached_value("Field of study", filiere, "name_of_field")
        or filiere,
        "filiere_code": frappe.get_cached_value("Field of study", filiere, "field_of_study_code")
        or filiere,
        "niveau": niveau,
        "semestre": semestre,
        "semestre_numero": _numero_semestre_cycle(niveau, semestre),
        "school_name": settings.school_name or "",
        "school_logo": settings.school_logo or "",
        "logo_file": "file://"
        + frappe.get_app_path("udshed", "public", "images", "logo.png"),
        "date_emission": frappe.utils.today(),
        "reference_no": "PV-{0}-{1}-{2}".format(
            filiere.replace("/", "-"),
            niveau.replace(" ", "-"),
            frappe.utils.today().replace("-", ""),
        ),
    }


def _statistiques(ue_liste, lignes):
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


@frappe.whitelist()
def download_proces_verbal_pdf(academic_year, filiere, niveau, semestre):
    data = get_proces_verbal_data(academic_year, filiere, niveau, semestre)
    if not data["ues"]:
        frappe.throw(_("Aucune UE trouvée pour ces critères."))
    if not data["etudiants"]:
        frappe.throw(_("Aucun étudiant inscrit pour ces critères."))

    from weasyprint import HTML

    template_path = frappe.get_app_path(
        "udshed", "public", "print_templates", "proces_verbal.html"
    )
    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    html = frappe.render_template(template, {"data": data})
    pdf = HTML(string=html, base_url=frappe.utils.get_url()).write_pdf()

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


# --------------------------------------------------------------------------- #
#  Procès-verbal d'une UE (colonnes = matières de l'UE)
# --------------------------------------------------------------------------- #
def _etudiants_de_lue(academic_year, filiere, niveau, matieres):
    """Classe d'une UE : mêmes règles que le PV de semestre (hors dispensés)."""
    return _etudiants_classe(
        academic_year, filiere, niveau, [{"name": m["teaching_unit"]} for m in matieres]
    )


@frappe.whitelist()
def get_pv_ue_data(academic_year, filiere, niveau, semestre, teaching_unit_value):
    """Données du PV d'une UE : une colonne par matière, une ligne par étudiant.

    Le résultat de chaque étudiant est recalculé à la volée
    (``calculer_ue_etudiant``, fonction pure) : le PV reflète donc toujours
    l'état de la saisie, y compris avant le premier enregistrement dans
    ``Resultat UE``.
    """
    from udshed.api.resultat_ue import calculer_ue_etudiant, get_matieres_ue

    matieres = get_matieres_ue(teaching_unit_value, academic_year, filiere, niveau)
    if not matieres:
        return {
            "context": _contexte(academic_year, filiere, niveau, semestre),
            "ue": None,
            "matieres": [],
            "etudiants": [],
            "statistiques": {},
        }

    etudiants = _etudiants_de_lue(academic_year, filiere, niveau, matieres)

    lignes = []
    for et in etudiants:
        resultat = calculer_ue_etudiant(
            et["student"], teaching_unit_value, academic_year, semestre, filiere, niveau
        )
        if resultat is None:
            continue
        lignes.append(
            {
                "student": et["student"],
                "matricule": et.get("matricule") or et["student"],
                "nom": et.get("nom") or "",
                "prenom": et.get("prenom") or "",
                "notes": {
                    ligne["teaching_unit"]: {
                        "code": ligne["code"],
                        "intitule": ligne["intitule"],
                        "credits": ligne["credits"],
                        "note_pct": ligne["note_pct"],
                        "note_finale": ligne["note_finale"],
                        "est_rattrapage": ligne["est_rattrapage"],
                        "valide": ligne["valide"],
                    }
                    for ligne in resultat["lignes"]
                },
                "note_ue_pct": resultat["note_ue_pct"],
                "note_ue_20": resultat["note_ue_20"],
                "grade": resultat["grade"],
                "point": resultat["point"],
                "mention": resultat["mention"],
                "statut": resultat["statut"],
                "seuil_validation": resultat["seuil_validation"],
                "total_credits": resultat["total_credits"],
                "credits_obtenus": resultat["credits_obtenus"],
                "pct_validation": resultat["pct_validation"],
                "commentaire": resultat["commentaire"],
            }
        )

    return {
        "context": _contexte(academic_year, filiere, niveau, semestre),
        "ue": _infos_ue(teaching_unit_value, matieres),
        "matieres": matieres,
        "etudiants": lignes,
        "statistiques": _statistiques_ue(lignes),
    }


def _infos_ue(teaching_unit_value, matieres):
    """Code, intitulé et crédits d'une UE (source : Teaching Unit Value)."""
    ue = frappe.db.get_value(
        "Teaching Unit Value",
        teaching_unit_value,
        ["code", "intitule", "semestre", "academic_year"],
        as_dict=True,
    )
    if not ue:
        return None
    return {
        "teaching_unit_value": teaching_unit_value,
        "code": ue.code or "",
        "intitule": ue.intitule or teaching_unit_value,
        "semestre": ue.semestre or "",
        "credits": round(sum(flt(m["credits"]) for m in matieres if flt(m["credits"]) > 0), 2),
        "n_matieres": len(matieres),
    }


def _statistiques_ue(lignes):
    """Inscrits / admis / échecs / en attente / taux de réussite.

    Le taux porte sur les étudiants effectivement délibérés (admis +
    échecs) : les lignes « En attente » ne doivent pas le faire baisser.
    """
    inscrits = len(lignes)
    admis = sum(1 for l in lignes if l["statut"] == "Validé")
    echecs = sum(1 for l in lignes if l["statut"] == "Non Validé")
    en_attente = sum(1 for l in lignes if l["statut"] == "En attente")
    delibere = admis + echecs
    seuils = sorted({flt(l["seuil_validation"]) for l in lignes if l["seuil_validation"] is not None})

    return {
        "inscrits": inscrits,
        "admis": admis,
        "echecs": echecs,
        "en_attente": en_attente,
        "taux_reussite": round(admis / delibere * 100, 2) if delibere else 0.0,
        "seuils": seuils,
    }


@frappe.whitelist()
def download_pv_ue_pdf(academic_year, filiere, niveau, semestre, teaching_unit_value):
    """Génère le PDF du procès-verbal d'une UE (A4 paysage)."""
    from udshed.api.resultats_page import ROLES_RESULTATS

    if not set(frappe.get_roles(frappe.session.user)) & set(ROLES_RESULTATS):
        frappe.throw(_("Accès réservé au personnel."))

    data = get_pv_ue_data(academic_year, filiere, niveau, semestre, teaching_unit_value)
    if not data["ue"] or not data["matieres"]:
        frappe.throw(_("Cette UE ne contient aucune matière pour cette année."))
    if not data["etudiants"]:
        frappe.throw(_("Aucun étudiant inscrit dans cette UE."))

    from weasyprint import HTML

    template_path = frappe.get_app_path(
        "udshed", "public", "print_templates", "pv_ue.html"
    )
    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    html = frappe.render_template(template, {"data": data})
    pdf = HTML(string=html, base_url=frappe.utils.get_url()).write_pdf()

    nom = "PV_UE_{0}_{1}_{2}_{3}.pdf".format(
        (data["ue"]["code"] or "UE").replace("/", "-"),
        filiere.replace("/", "-"),
        semestre.replace(" ", ""),
        academic_year.replace("/", "-"),
    )
    frappe.response["filename"] = nom
    frappe.response["filecontent"] = pdf
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/pdf"
