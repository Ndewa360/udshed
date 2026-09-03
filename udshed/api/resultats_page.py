# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""API de la page « Résultats académiques ».

Données agrégées pour l'interface : tableau des résultats, statistiques,
vue par cours, analytiques, détail d'un étudiant et export PDF.

Source unique de vérité : les notes publiées (« Session Examen Note » au
statut « Publié ») et le moteur de calcul existant (udshed.grade_calculation).
Aucune formule n'est reconstruite ici.

Règle normale / rattrapage (identique au reste du projet) : pour une UE, la
meilleure note entre la session normale et la session de rattrapage est
retenue — jamais de remplacement systématique de l'examen par le rattrapage.
"""

import frappe
from frappe import _
from frappe.utils import flt

from udshed.api.proces_verbal import _credits_ue
from udshed.api.saisie_notes import _cycle_pour_niveau, _get_etudiants, _get_niveau_name
from udshed.grade_calculation import get_grade_scale, get_seuil_validation

TYPE_CC = "Controlle Continue (CC)"
TYPE_NORMALE = "Examen de session normal"
TYPE_RATTRAPAGE = "Examen de rattrapage"
STATUT_PUBLIE = "Publié"

ROLES_RESULTATS = (
    "System Manager",
    "Coordonateur",
    "Coordinateur",
    "Planning Manager",
    "Registration Manager",
    "Agent de scolarité",
    "Comptable",
    "Udshed Financial Admin",
)


# ---------------------------------------------------------------------- #
#  Permissions
# ---------------------------------------------------------------------- #
def _filieres_coordonnateur(user):
    """Filières dont l'utilisateur est coordonnateur / gestionnaire de planning.

    Retourne [] si l'utilisateur n'est lié à aucune filière (aucune
    restriction applicable).
    """
    rows = frappe.db.sql(
        """
        SELECT DISTINCT fos.name AS filiere
        FROM `tabField of study` fos
        JOIN `tabField of study Level` lvl ON lvl.parent = fos.name
        JOIN `tabTeacher` t ON t.name IN (lvl.coordonateur, lvl.gestionnaire_de_planning)
        WHERE t.email = %s
        """,
        (user,),
        as_dict=True,
    )
    return [r.filiere for r in rows]


def _verifier_acces_resultats(filiere=None):
    """Contrôle l'accès aux résultats côté backend (jamais côté frontend)."""
    user = frappe.session.user
    if user == "Administrator":
        return
    roles = frappe.get_roles(user)
    if not any(r in roles for r in ROLES_RESULTATS):
        frappe.throw(
            _("Vous n'avez pas accès aux résultats académiques."),
            frappe.PermissionError,
        )
    if (
        filiere
        and "System Manager" not in roles
        and ("Coordonateur" in roles or "Coordinateur" in roles)
    ):
        filieres = _filieres_coordonnateur(user)
        if filieres and filiere not in filieres:
            frappe.throw(
                _("Vous n'êtes pas autorisé(e) à consulter les résultats de la filière <b>{0}</b>.").format(filiere),
                frappe.PermissionError,
            )


# ---------------------------------------------------------------------- #
#  Classes et sessions réellement présentes
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def get_classes(academic_year=None):
    """Classes (filière + niveau) ayant au moins une session d'examen sur l'année.

    Aucune donnée fictive : la liste provient des Session Examen et de leurs
    lignes « Session Examen Field of study Level ». Un coordonnateur ne voit
    que ses filières.
    """
    _verifier_acces_resultats()
    filieres_autorisees = None
    user = frappe.session.user
    if user != "Administrator":
        roles = frappe.get_roles(user)
        if "System Manager" not in roles and ("Coordonateur" in roles or "Coordinateur" in roles):
            filieres_autorisees = set(_filieres_coordonnateur(user)) or None

    filters = {}
    if academic_year:
        filters["academic_year"] = academic_year
    sessions = frappe.get_all("Session Examen", filters=filters, pluck="name")
    if not sessions:
        return []

    lignes = frappe.get_all(
        "Session Examen Field of study Level",
        filters={"parent": ["in", sessions]},
        fields=["parent", "filiere", "niveau"],
    )
    niveaux_par_classe = {}
    for l in lignes:
        niveaux_par_classe.setdefault(l.filiere, set()).add(l.niveau)

    classes = []
    for filiere, niveaux in sorted(niveaux_par_classe.items()):
        if filieres_autorisees is not None and filiere not in filieres_autorisees:
            continue
        filiere_name = frappe.get_cached_value("Field of study", filiere, "name_of_field") or filiere
        for niveau_name in sorted(niveaux):
            label_niveau = frappe.db.get_value("Field of study Level", niveau_name, "level") or niveau_name
            classes.append(
                {
                    "filiere": filiere,
                    "niveau": label_niveau,
                    "label": "{0} — {1}".format(filiere_name, label_niveau),
                }
            )
    return classes


def _sessions_classe(academic_year, filiere, niveau, semestre=None, types=None):
    """Sessions des types demandés couvrant la classe (filière, niveau)."""
    niveau_name = _get_niveau_name(filiere, niveau)
    if not niveau_name:
        return {}
    filters = {
        "academic_year": academic_year,
        "type_dexamen": ["in", types or [TYPE_NORMALE, TYPE_RATTRAPAGE]],
    }
    if semestre:
        filters["semestre"] = semestre
    sessions = frappe.get_all(
        "Session Examen",
        filters=filters,
        fields=["name", "type_dexamen", "semestre", "statut"],
    )
    couvertes = {}
    for s in sessions:
        if frappe.db.exists(
            "Session Examen Field of study Level",
            {"parent": s.name, "filiere": filiere, "niveau": niveau_name},
        ):
            couvertes[s.name] = s
    return couvertes


# ---------------------------------------------------------------------- #
#  Agrégation principale
# ---------------------------------------------------------------------- #
def _notes_classe(sessions, filiere, niveau):
    """Notes publiées des sessions, consolidées par (étudiant, UE).

    Règle projet : lorsque l'UE possède une note normale et une note de
    rattrapage publiées, la meilleure note finale est retenue.
    """
    if not sessions:
        return {}
    notes = frappe.get_all(
        "Session Examen Note",
        filters={"session_examen": ["in", list(sessions)], "statut": STATUT_PUBLIE},
        fields=[
            "name", "session_examen", "student", "teaching_unit",
            "note_cc_moyenne", "cc_saisi",
            "note_examen", "examen_saisi",
            "note_examen_rattrapage", "rattrapage_saisi",
            "note_examen_active",
            "note_finale", "note_pct", "grade", "point", "mention", "type_resultat",
        ],
    )

    consolidees = {}
    for n in notes:
        n.type_session = sessions[n.session_examen].type_dexamen
        cle = (n.student, n.teaching_unit)
        actuelle = consolidees.get(cle)
        if actuelle is None or (n.note_finale or 0) > (actuelle.note_finale or 0):
            consolidees[cle] = n

    # L'examen initial et le rattrapage peuvent être portés par deux notes
    # distinctes : on complète la note retenue avec les valeurs de l'autre.
    for n in notes:
        cle = (n.student, n.teaching_unit)
        retenue = consolidees.get(cle)
        if retenue is None or retenue.name == n.name:
            continue
        if retenue.note_examen is None and n.note_examen is not None:
            retenue.note_examen = n.note_examen
        if retenue.note_examen_rattrapage is None and n.note_examen_rattrapage is not None:
            retenue.note_examen_rattrapage = n.note_examen_rattrapage
        if not retenue.note_cc_moyenne and n.note_cc_moyenne:
            retenue.note_cc_moyenne = n.note_cc_moyenne

    return consolidees


def _etudiants_classe(academic_year, filiere, niveau, ues_names):
    """Étudiants inscrits aux UE de la classe (réinscription Validée + Inscrit)."""
    resultats = []
    vus = set()
    for ue in ues_names:
        for et in _get_etudiants(academic_year, filiere, niveau, ue):
            if et["student"] in vus:
                continue
            vus.add(et["student"])
            resultats.append(et)
    resultats.sort(key=lambda s: (s.get("matricule") or s["student"]).lower())
    return resultats


def _ues_classe(academic_year, filiere, niveau, semestre=None):
    """UE de la classe avec leur code / intitulé / crédits."""
    filiere_doc = frappe.get_doc("Field of study", filiere)
    niveau_names = [row.name for row in filiere_doc.field_of_study_level if row.level == niveau]
    if not niveau_names:
        return []
    rows = frappe.get_all(
        "Course Field of study level item",
        filters={"filiere": filiere, "niveau": ["in", niveau_names]},
        fields=["parent"],
        distinct=True,
    )
    ue_names = [r.parent for r in rows]
    if not ue_names:
        return []
    filters_ue = {"name": ["in", ue_names], "academic_year": academic_year}
    if semestre:
        filters_ue["semestre"] = semestre
    ues = frappe.get_all(
        "Teaching Unit",
        filters=filters_ue,
        fields=["name", "course", "intitule_cours", "credits", "semestre"],
        order_by="name",
    )
    for ue in ues:
        code = frappe.get_cached_value("Course", ue.course, "code") if ue.course else ""
        ue.code = code or ""
        ue.intitule = ue.intitule_cours or ue.name
        ue.credits_classe = _credits_ue(ue.name, filiere, niveau)
    return ues


@frappe.whitelist()
def get_resultats(
    academic_year=None,
    filiere=None,
    niveau=None,
    semestre=None,
    session_type=None,
    statut=None,
    search=None,
):
    """Données agrégées de la page Résultats académiques.

    Tout est calculé côté backend depuis les notes publiées : lignes du
    tableau (avec rang), statistiques, vue par cours et analytiques.

    Args:
        academic_year: Academic Year (défaut : année courante des réglages)
        filiere: Field of study
        niveau: Label du niveau (ex : « Licence 1 »)
        semestre: « Semestre 1 » / « Semestre 2 » (optionnel)
        session_type: « Examen de session normal », « Examen de rattrapage »
            ou vide (meilleure note des deux, règle métier du projet)
        statut: filtre étudiant « Admis » / « Ajourné » (optionnel)
        search: filtre sur matricule / nom / prénom (optionnel)
    """
    if not academic_year:
        academic_year = frappe.db.get_single_value("Udshed Setting", "current_year")

    contexte = _contexte(academic_year, filiere, niveau, semestre)
    vide = {
        "contexte": contexte,
        "lignes": [],
        "etudiants": [],
        "statistiques": _statistiques([]),
        "par_cours": [],
        "analytiques": _analytiques([], [], []),
    }
    if not academic_year or not filiere or not niveau:
        return vide

    _verifier_acces_resultats(filiere)
    if not frappe.db.exists("Field of study", filiere):
        return vide

    types = [session_type] if session_type in (TYPE_NORMALE, TYPE_RATTRAPAGE) else None
    sessions = _sessions_classe(academic_year, filiere, niveau, semestre, types)
    ues = _ues_classe(academic_year, filiere, niveau, semestre)
    if not ues:
        return vide

    consolidees = _notes_classe(sessions, filiere, niveau)
    etudiants = _etudiants_classe(academic_year, filiere, niveau, [u.name for u in ues])
    if not etudiants:
        return vide

    cycle_classe = _cycle_pour_niveau(niveau)
    infos_etudiants = {
        s.name: s
        for s in frappe.get_all(
            "Student",
            filters={"name": ["in", [e["student"] for e in etudiants]]},
            fields=["name", "matricule", "nom", "prenom", "cycle", "filiere", "niveau_actuel"],
        )
    }
    # -- lignes par (étudiant, UE) et bilan par étudiant ------------------ #
    lignes = []
    bilans = {}
    for et in etudiants:
        student = et["student"]
        info = infos_etudiants.get(student)
        if info is None:
            continue
        cycle = info.cycle or cycle_classe
        somme_credits = 0
        somme_credits_pct = 0
        nb_notes = 0
        ue_validees = 0

        for ue in ues:
            note = consolidees.get((student, ue.name))
            if note is None:
                continue
            note_pct = note.note_pct
            valide = bool(note_pct is not None and note_pct >= get_seuil_validation(cycle))
            lignes.append(
                {
                    "student": student,
                    "matricule": info.matricule or et.get("matricule") or student,
                    "nom": info.nom or "",
                    "prenom": info.prenom or "",
                    "nom_complet": "{0} {1}".format(info.prenom or "", info.nom or "").strip(),
                    "classe": contexte["classe_label"],
                    "cycle": cycle,
                    "teaching_unit": ue.name,
                    "cours_code": ue.code,
                    "cours_intitule": ue.intitule,
                    "credits": ue.credits_classe,
                    "note_cc": note.note_cc_moyenne if note.cc_saisi else None,
                    "note_examen": note.note_examen_active,
                    "session_normale": note.note_examen if note.examen_saisi else None,
                    "session_rattrapage": note.note_examen_rattrapage if note.rattrapage_saisi else None,
                    "est_rattrapage": bool(note.type_session == TYPE_RATTRAPAGE),
                    "note_finale": note.note_finale,
                    "note_pct": note_pct,
                    "grade": note.grade or "",
                    "point": note.point,
                    "statut_ue": "Validé" if valide else "Non Validé",
                }
            )
            somme_credits += ue.credits_classe
            somme_credits_pct += ue.credits_classe * flt(note_pct)
            nb_notes += 1
            if valide:
                ue_validees += 1

        mps = round(somme_credits_pct / somme_credits, 2) if somme_credits > 0 else 0
        if nb_notes == 0:
            statut_etudiant = "En attente"
        elif mps >= get_seuil_validation(cycle):
            statut_etudiant = "Admis"
        else:
            statut_etudiant = "Ajourné"
        bilans[student] = {
            "student": student,
            "matricule": info.matricule or et.get("matricule") or student,
            "nom": info.nom or "",
            "prenom": info.prenom or "",
            "nom_complet": "{0} {1}".format(info.prenom or "", info.nom or "").strip(),
            "mps": mps,
            "mps_20": round(mps / 5, 2),
            "nb_ue": nb_notes,
            "ue_validees": ue_validees,
            "statut": statut_etudiant,
        }

    # -- filtres (validés et appliqués côté backend) ----------------------- #
    if search:
        needle = search.lower()
        bilans = {
            s: b
            for s, b in bilans.items()
            if needle in (b["matricule"] or "").lower()
            or needle in (b["nom"] or "").lower()
            or needle in (b["prenom"] or "").lower()
        }
    if statut in ("Admis", "Ajourné"):
        bilans = {s: b for s, b in bilans.items() if b["statut"] == statut}

    # -- classement par moyenne (MPS) -------------------------------------- #
    classements = sorted(
        bilans.values(), key=lambda b: (-b["mps"], b["matricule"].lower())
    )
    for rang, bilan in enumerate(classements, 1):
        bilan["rang"] = rang
    rangs = {b["student"]: b["rang"] for b in classements}
    lignes = [l for l in lignes if l["student"] in bilans]
    for ligne in lignes:
        ligne["rang"] = rangs.get(ligne["student"])
        ligne["mps"] = bilans[ligne["student"]]["mps"]
        ligne["statut"] = bilans[ligne["student"]]["statut"]
    lignes.sort(key=lambda l: (l["rang"], l["teaching_unit"]))

    par_cours = _par_cours(lignes, ues)
    etudiants_out = [b for b in classements]

    return {
        "contexte": contexte,
        "lignes": lignes,
        "etudiants": etudiants_out,
        "statistiques": _statistiques(etudiants_out),
        "par_cours": par_cours,
        "analytiques": _analytiques(etudiants_out, lignes, par_cours),
    }


def _contexte(academic_year, filiere, niveau, semestre):
    """Contexte d'en-tête partagé par l'interface et le PDF."""
    settings = frappe.get_single("Udshed Setting")
    filiere_name = (
        frappe.get_cached_value("Field of study", filiere, "name_of_field") or filiere
    ) if filiere else ""
    classe_label = (
        "{0} — {1}".format(filiere_name, niveau) if filiere and niveau else ""
    )
    return {
        "academic_year": academic_year or "",
        "year_label": (
            frappe.get_cached_value("Academic Year", academic_year, "year_name") or academic_year
        ) if academic_year else "",
        "filiere": filiere or "",
        "filiere_name": filiere_name,
        "niveau": niveau or "",
        "classe_label": classe_label,
        "semestre": semestre or "",
        "school_name": settings.school_name or "",
        "school_logo": settings.school_logo or "",
    }


def _statistiques(etudiants):
    """Statistiques de la sélection courante (calculées côté backend)."""
    total = len(etudiants)
    admis = sum(1 for e in etudiants if e["statut"] == "Admis")
    ajournes = sum(1 for e in etudiants if e["statut"] == "Ajourné")
    notes = [e["mps"] for e in etudiants if e["statut"] != "En attente"]
    moyenne_pct = round(sum(notes) / len(notes), 2) if notes else 0
    return {
        "total_etudiants": total,
        "admis": admis,
        "echecs": ajournes,
        "en_attente": total - admis - ajournes,
        "moyenne_classe": round(moyenne_pct / 5, 2),
        "moyenne_classe_pct": moyenne_pct,
        "taux_reussite": round(admis / total * 100, 1) if total else 0,
    }


def _par_cours(lignes, ues):
    """Vue par cours : agrégats par UE depuis les lignes filtrées."""
    par_ue = {}
    for l in lignes:
        par_ue.setdefault(l["teaching_unit"], []).append(l)

    out = []
    ue_par_name = {u.name: u for u in ues}
    for ue_name, rows in par_ue.items():
        ue = ue_par_name.get(ue_name)
        notes = [r["note_finale"] for r in rows if r["note_finale"] is not None]
        valides = sum(1 for r in rows if r["statut_ue"] == "Validé")
        nb = len(rows)
        out.append(
            {
                "teaching_unit": ue_name,
                "code": (ue and ue.code) or "",
                "intitule": (ue and ue.intitule) or ue_name,
                "credits": (ue and ue.credits_classe) or 0,
                "nb_etudiants": nb,
                "moyenne": round(sum(notes) / len(notes), 2) if notes else None,
                "meilleure": max(notes) if notes else None,
                "plus_faible": min(notes) if notes else None,
                "admis": valides,
                "echecs": nb - valides,
                "taux_reussite": round(valides / nb * 100, 1) if nb else 0,
            }
        )
    out.sort(key=lambda c: (c["intitule"] or "").lower())
    return out


def _analytiques(etudiants, lignes, par_cours):
    """Indicateurs pour l'onglet Analytiques (valeurs réelles uniquement)."""
    moyennes = [e["mps_20"] for e in etudiants if e["statut"] != "En attente"]
    bornes = [(0, 10), (10, 12), (12, 14), (14, 16), (16, 20.01)]
    labels = ["< 10", "10 – 12", "12 – 14", "14 – 16", "≥ 16"]
    distribution_moyennes = [
        {
            "tranche": labels[i],
            "nb": sum(1 for m in moyennes if b[0] <= m < b[1]),
        }
        for i, b in enumerate(bornes)
    ]

    distribution_grades = []
    for g in get_grade_scale():
        distribution_grades.append(
            {
                "grade": g["grade"],
                "nb": sum(1 for l in lignes if l["grade"] == g["grade"]),
            }
        )
    distribution_grades = [g for g in distribution_grades if g["nb"] > 0]

    return {
        "distribution_moyennes": distribution_moyennes,
        "distribution_grades": distribution_grades,
        "par_cours": par_cours,
    }


# ---------------------------------------------------------------------- #
#  Détail d'un étudiant
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def get_resultat_detail(student, academic_year=None, semestre=None):
    """Vue détaillée d'un étudiant : UE, notes, crédits, MPS/MPC, décision.

    Réutilise les notes publiées et les résultats produits par le moteur
    (Resultat Semestre lorsque celui-ci a été calculé).
    """
    if not frappe.db.exists("Student", student):
        frappe.throw(_("Étudiant introuvable."), frappe.DoesNotExistError)
    student_doc = frappe.get_doc("Student", student)
    _verifier_acces_resultats(student_doc.filiere)

    if not academic_year:
        academic_year = frappe.db.get_single_value("Udshed Setting", "current_year")

    cycle = student_doc.cycle or _cycle_pour_niveau(student_doc.niveau_actuel or "")
    seuil = get_seuil_validation(cycle)
    filiere_name = (
        frappe.get_cached_value("Field of study", student_doc.filiere, "name_of_field")
        or student_doc.filiere or ""
    )

    filters_notes = {"student": student, "statut": STATUT_PUBLIE}
    if academic_year or semestre:
        filters_sessions = {}
        if academic_year:
            filters_sessions["academic_year"] = academic_year
        if semestre:
            filters_sessions["semestre"] = semestre
        sessions = frappe.get_all(
            "Session Examen", filters=filters_sessions, fields=["name", "type_dexamen"]
        )
        types = {s.name: s.type_dexamen for s in sessions}
        filters_notes["session_examen"] = ["in", list(types)]
    else:
        types = {}

    notes = frappe.get_all(
        "Session Examen Note",
        filters=filters_notes,
        fields=[
            "name", "session_examen", "teaching_unit",
            "note_cc_moyenne", "cc_saisi",
            "note_examen", "examen_saisi",
            "note_examen_rattrapage", "rattrapage_saisi",
            "note_examen_active",
            "note_finale", "note_pct", "grade", "point", "mention", "type_resultat",
        ],
        order_by="teaching_unit",
    )

    consolidees = {}
    for n in notes:
        n.type_session = types.get(n.session_examen, TYPE_NORMALE)
        cle = n.teaching_unit
        actuelle = consolidees.get(cle)
        if actuelle is None or (n.note_finale or 0) > (actuelle.note_finale or 0):
            consolidees[cle] = n
    for n in notes:
        retenue = consolidees.get(n.teaching_unit)
        if retenue is None or retenue.name == n.name:
            continue
        if retenue.note_examen is None and n.note_examen is not None:
            retenue.note_examen = n.note_examen
        if retenue.note_examen_rattrapage is None and n.note_examen_rattrapage is not None:
            retenue.note_examen_rattrapage = n.note_examen_rattrapage
        if not retenue.note_cc_moyenne and n.note_cc_moyenne:
            retenue.note_cc_moyenne = n.note_cc_moyenne

    ues_detail = []
    somme_credits = 0
    somme_credits_pct = 0
    credits_obtenus = 0
    for ue_name, note in sorted(consolidees.items()):
        tu = frappe.get_cached_value(
            "Teaching Unit", ue_name, ["course", "intitule_cours", "semestre"], as_dict=True
        ) or {}
        code = frappe.get_cached_value("Course", tu.get("course"), "code") if tu.get("course") else ""
        credits = _credits_ue(ue_name, student_doc.filiere, student_doc.niveau_actuel) if student_doc.filiere else int(
            frappe.db.get_value("Teaching Unit", ue_name, "credits") or 0
        )
        note_pct = note.note_pct
        valide = bool(note_pct is not None and note_pct >= seuil)
        ues_detail.append(
            {
                "teaching_unit": ue_name,
                "code": code or "",
                "intitule": tu.get("intitule_cours") or ue_name,
                "semestre": tu.get("semestre") or "",
                "credits": credits,
                "note_cc": note.note_cc_moyenne if note.cc_saisi else None,
                "note_examen": note.note_examen if note.examen_saisi else None,
                "note_rattrapage": note.note_examen_rattrapage if note.rattrapage_saisi else None,
                "note_retenue": note.note_examen_active,
                "est_rattrapage": bool(note.type_session == TYPE_RATTRAPAGE),
                "note_finale": note.note_finale,
                "note_pct": note_pct,
                "grade": note.grade or "",
                "point": note.point,
                "mention": note.mention or "",
                "statut_ue": "Validé" if valide else "Non Validé",
            }
        )
        somme_credits += credits
        somme_credits_pct += credits * flt(note_pct)
        if valide:
            credits_obtenus += credits

    mps = round(somme_credits_pct / somme_credits, 2) if somme_credits > 0 else 0

    # MPC depuis Resultat Semestre uniquement si ce dernier est cohérent avec
    # les notes publiées courantes (sinon il est obsolète et on l'ignore).
    mpc = None
    rs = frappe.db.get_value(
        "Resultat Semestre",
        {"student": student, "academic_year": academic_year, "semestre": semestre},
        ["mps", "mpc"],
        as_dict=True,
    ) if semestre else None
    if rs and rs.mps is not None and abs(flt(rs.mps) - mps) < 0.01:
        mpc = rs.mpc

    return {
        "student": student,
        "matricule": student_doc.matricule or student,
        "nom_complet": "{0} {1}".format(student_doc.prenom or "", student_doc.nom or "").strip(),
        "filiere_name": filiere_name,
        "niveau": student_doc.niveau_actuel or "",
        "cycle": cycle,
        "academic_year": academic_year or "",
        "semestre": semestre or "",
        "ues": ues_detail,
        "total_credits": somme_credits,
        "credits_obtenus": credits_obtenus,
        "mps": mps,
        "mpc": mpc,
        "decision": (
            "Admis" if ues_detail and mps >= seuil else ("Ajourné" if ues_detail else "En attente")
        ),
        "seuil": seuil,
    }


# ---------------------------------------------------------------------- #
#  Export PDF
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def download_resultat_etudiant_pdf(student, academic_year=None, semestre=None):
    """PDF individuel d'un étudiant (données réelles du moteur, filtres respectés)."""
    data = get_resultat_detail(student, academic_year=academic_year, semestre=semestre)
    if not data["ues"]:
        frappe.throw(_("Aucun résultat publié pour cet étudiant sur ces critères."))

    from weasyprint import HTML

    template_path = frappe.get_app_path(
        "udshed", "public", "print_templates", "resultat_etudiant.html"
    )
    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    settings = frappe.get_single("Udshed Setting")
    html = frappe.render_template(
        template,
        {
            "data": data,
            "school_name": settings.school_name or "",
            "school_logo": settings.school_logo or "",
        },
    )
    pdf = HTML(string=html, base_url=frappe.utils.get_url()).write_pdf()

    nom = "releve_{0}_{1}_{2}.pdf".format(
        (data["matricule"] or student).replace("/", "-"),
        (data["nom_complet"] or "").replace(" ", "-") or "etudiant",
        (academic_year or "").replace("/", "-"),
    )
    frappe.response["filename"] = nom
    frappe.response["filecontent"] = pdf
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/pdf"


@frappe.whitelist()
def download_resultats_pdf(
    academic_year=None,
    filiere=None,
    niveau=None,
    semestre=None,
    session_type=None,
    statut=None,
    search=None,
):
    """Génère le PDF des résultats en respectant les filtres courants."""
    data = get_resultats(
        academic_year=academic_year,
        filiere=filiere,
        niveau=niveau,
        semestre=semestre,
        session_type=session_type,
        statut=statut,
        search=search,
    )
    if not data["etudiants"]:
        frappe.throw(_("Aucun résultat à exporter pour ces critères."))

    from weasyprint import HTML

    template_path = frappe.get_app_path(
        "udshed", "public", "print_templates", "resultats_academiques.html"
    )
    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    session_libelle = {
        TYPE_NORMALE: "session_normale",
        TYPE_RATTRAPAGE: "rattrapage",
    }.get(session_type, "toutes_sessions")
    html = frappe.render_template(template, {"data": data, "session_libelle": session_libelle})
    pdf = HTML(string=html, base_url=frappe.utils.get_url()).write_pdf()

    nom = "resultats_academiques_{0}_{1}_{2}_{3}.pdf".format(
        (filiere or "classe").replace("/", "-"),
        (niveau or "").replace(" ", "-"),
        session_libelle,
        (academic_year or "").replace("/", "-"),
    )
    frappe.response["filename"] = nom
    frappe.response["filecontent"] = pdf
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/pdf"
