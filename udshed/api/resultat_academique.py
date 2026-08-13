# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from udshed.grade_calculation import get_seuil_validation, get_student_cycle

TYPE_NORMALE = "Examen de session normal"
TYPE_RATTRAPAGE = "Examen de rattrapage"

SEMESTRES = ["Semestre 1", "Semestre 2"]

_MOIS_INDEX = {
    "Janvier": 1, "Févriér": 2, "Mars": 3, "Avril": 4, "Mai": 5,
    "Juin": 6, "Juillet": 7, "Aout": 8, "Septembre": 9, "Octobre": 10,
    "Novembre": 11, "Decembre": 12,
}


def _debut_annee(academic_year):
    """Date de début (int comparable) d'une Academic Year pour le tri."""
    annee = frappe.db.get_value(
        "Academic Year", academic_year, ["start_year", "start_month"], as_dict=True
    )
    if not annee:
        return 0
    mois = _MOIS_INDEX.get(annee.start_month, 9)
    try:
        return int(annee.start_year) * 100 + mois
    except (TypeError, ValueError):
        return int(annee.start_year or 0) * 100 + 9


# ---------------------------------------------------------------------- #
#  Résultat d'une UE
# ---------------------------------------------------------------------- #
def _resultat_ue(student, session_doc, note_normale):
    """Calcule et sauvegarde le résultat d'une UE pour un étudiant.

    Retient le meilleur résultat entre la session normale et la session de
    rattrapage : note finale = MAX(note normale, note rattrapage).

    Args:
        student: Nom du Student
        session_doc: Document Session Examen (session normale)
        note_normale: dict de la Session Examen Note (session normale)

    Returns:
        dict: résultat de l'UE
    """
    teaching_unit = note_normale.teaching_unit

    note_rattrapage = None
    rattrapages = frappe.get_all(
        "Session Examen",
        filters={
            "academic_year": session_doc.academic_year,
            "semestre": session_doc.semestre,
            "type_dexamen": TYPE_RATTRAPAGE,
        },
        pluck="name",
    )

    for sess_r in rattrapages:
        note_r = frappe.db.get_value(
            "Session Examen Note",
            {
                "student": student,
                "session_examen": sess_r,
                "teaching_unit": teaching_unit,
                "statut": "Publié",
            },
            ["name", "note_finale", "note_pct", "grade", "point", "mention",
             "note_examen_rattrapage"],
            as_dict=True,
        )
        if note_r and note_r.note_finale:
            if note_rattrapage is None or note_r.note_finale > note_rattrapage.note_finale:
                note_rattrapage = note_r

    if note_rattrapage and note_rattrapage.note_finale > note_normale.note_finale:
        resultat_source = note_rattrapage
        est_rattrapage = True
    else:
        resultat_source = note_normale
        est_rattrapage = False

    student_doc = frappe.get_doc("Student", student)
    cycle = get_student_cycle(student_doc)
    seuil = get_seuil_validation(cycle)

    note_pct = resultat_source.note_pct
    statut = "Validé" if note_pct is not None and note_pct >= seuil else "Non Validé"

    existing = frappe.db.get_value(
        "Resultat Academique",
        {
            "student": student,
            "teaching_unit": teaching_unit,
            "academic_year": session_doc.academic_year,
            "semestre": session_doc.semestre,
        },
        "name",
    )

    if existing:
        res = frappe.get_doc("Resultat Academique", existing)
    else:
        res = frappe.new_doc("Resultat Academique")

    res.student = student
    res.teaching_unit = teaching_unit
    res.academic_year = session_doc.academic_year
    res.semestre = session_doc.semestre
    res.note_finale = resultat_source.note_finale
    res.note_pct = note_pct
    res.grade = resultat_source.grade
    res.point = resultat_source.point
    res.mention = resultat_source.mention
    res.statut = statut
    res.est_rattrapage = est_rattrapage
    res.session_normale = note_normale.name
    res.session_rattrapage = note_rattrapage.name if est_rattrapage else None

    if existing:
        res.save()
    else:
        res.insert()

    return {
        "name": res.name,
        "student": student,
        "student_name": res.student_name,
        "teaching_unit": teaching_unit,
        "ue_name": res.ue_name,
        "note_finale": res.note_finale,
        "note_pct": res.note_pct,
        "grade": res.grade,
        "point": res.point,
        "mention": res.mention,
        "statut": res.statut,
        "est_rattrapage": est_rattrapage,
        "session_normale": note_normale.name,
        "session_rattrapage": res.session_rattrapage,
    }


@frappe.whitelist()
def calculer_resultat_session(student, session_examen, teaching_unit=None):
    """Calcule les résultats académiques d'un étudiant pour une session.

    Prend la meilleure note entre session normale et session de rattrapage
    pour chaque UE, puis crée / met à jour les Resultat Academique.

    Args:
        student: Nom du Student
        session_examen: Nom de la Session Examen (session normale)
        teaching_unit: UE à recalculer (optionnel ; sinon toutes les UE)

    Returns:
        dict: {"resultats": [...], "total": n}
    """
    session_doc = frappe.get_doc("Session Examen", session_examen)

    filters = {
        "student": student,
        "session_examen": session_examen,
        "statut": "Publié",
    }
    if teaching_unit:
        filters["teaching_unit"] = teaching_unit

    notes_normales = frappe.get_all(
        "Session Examen Note",
        filters=filters,
        fields=["name", "teaching_unit", "note_finale", "note_pct", "grade",
                "point", "mention", "note_examen_active", "note_examen_rattrapage"],
        order_by="teaching_unit",
    )

    if not notes_normales:
        frappe.throw(
            _("Aucune note publiée trouvée pour l'étudiant {0} dans la session {1}").format(
                student, session_examen
            )
        )

    resultats = [_resultat_ue(student, session_doc, n) for n in notes_normales]

    return {"resultats": resultats, "total": len(resultats)}


@frappe.whitelist()
def calculer_resultat_semestre(student, semestre, academic_year):
    """Calcule les résultats de toutes les UE pour un semestre donné.

    Args:
        student: Nom du Student
        semestre: "Semestre 1" ou "Semestre 2"
        academic_year: Nom de l'Academic Year

    Returns:
        dict: Résultats du semestre avec MPS pondérée et nombre d'UE validées
    """
    sessions = frappe.get_all(
        "Session Examen",
        filters={
            "academic_year": academic_year,
            "semestre": semestre,
            "type_dexamen": TYPE_NORMALE,
        },
        pluck="name",
    )

    resultats = []
    for session in sessions:
        try:
            data = calculer_resultat_session(student, session)
            resultats.extend(data["resultats"])
        except frappe.DoesNotExistError:
            continue

    if not resultats:
        return {
            "student": student,
            "semestre": semestre,
            "academic_year": academic_year,
            "resultats": [],
            "moyenne": 0,
            "mps": 0,
            "total_ue": 0,
            "ue_validees": 0,
            "ue_non_validees": 0,
        }

    student_doc = frappe.get_doc("Student", student)
    cycle = get_student_cycle(student_doc)
    seuil = get_seuil_validation(cycle)

    somme_cj_pj = 0
    somme_cj = 0
    for r in resultats:
        credits = frappe.db.get_value(
            "Teaching Unit", r["teaching_unit"], "credits"
        ) or 0
        somme_cj_pj += credits * (r.get("point") or 0)
        somme_cj += credits

    mps = round(somme_cj_pj / somme_cj, 2) if somme_cj > 0 else 0

    ue_validees = sum(1 for r in resultats if (r["note_pct"] or 0) >= seuil)
    ue_non_validees = len(resultats) - ue_validees

    return {
        "student": student,
        "semestre": semestre,
        "academic_year": academic_year,
        "resultats": resultats,
        "moyenne": mps,
        "mps": mps,
        "total_ue": len(resultats),
        "ue_validees": ue_validees,
        "ue_non_validees": ue_non_validees,
    }


@frappe.whitelist()
def calculer_resultat_annee(student, academic_year):
    """Calcule les résultats annuels et la décision de promotion.

    Args:
        student: Nom du Student
        academic_year: Nom de l'Academic Year

    Returns:
        dict: Résultats annuels avec décision
    """
    semestres = frappe.get_all(
        "Session Examen",
        filters={
            "academic_year": academic_year,
            "type_dexamen": TYPE_NORMALE,
        },
        pluck="semestre",
        distinct=True,
    )
    if not semestres:
        semestres = list(SEMESTRES)

    resultats_par_semestre = {}
    tous_resultats = []
    for semestre in semestres:
        data = calculer_resultat_semestre(student, semestre, academic_year)
        resultats_par_semestre[semestre] = data
        tous_resultats.extend(data["resultats"])

    if not tous_resultats:
        return {
            "student": student,
            "academic_year": academic_year,
            "moyenne_annuelle": 0,
            "total_ue": 0,
            "ue_validees": 0,
            "decision": "En attente",
            "resultats_par_semestre": resultats_par_semestre,
        }

    student_doc = frappe.get_doc("Student", student)
    cycle = get_student_cycle(student_doc)
    seuil = get_seuil_validation(cycle)

    somme_cp = 0.0
    somme_c = 0
    for r in tous_resultats:
        credits = frappe.db.get_value("Teaching Unit", r["teaching_unit"], "credits") or 0
        somme_cp += credits * (r["note_pct"] or 0)
        somme_c += credits
    moyenne_annuelle = round(somme_cp / somme_c, 2) if somme_c > 0 else 0

    ue_validees = sum(1 for r in tous_resultats if (r["note_pct"] or 0) >= seuil)
    ue_non_validees = len(tous_resultats) - ue_validees

    decision = "Admis" if ue_non_validees == 0 else "Ajourné"

    for r in tous_resultats:
        if r.get("name"):
            frappe.db.set_value("Resultat Academique", r["name"], "decision_annee", decision)

    return {
        "student": student,
        "student_name": tous_resultats[0].get("student_name", ""),
        "academic_year": academic_year,
        "moyenne_annuelle": moyenne_annuelle,
        "total_ue": len(tous_resultats),
        "ue_validees": ue_validees,
        "ue_non_validees": ue_non_validees,
        "decision": decision,
        "resultats_par_semestre": resultats_par_semestre,
    }


@frappe.whitelist()
def generer_classe_resultat(filiere, niveau, academic_year):
    """Génère les résultats pour toute une classe (filière + niveau).

    Args:
        filiere: Nom de la Filiere
        niveau: Nom du Field of study Level
        academic_year: Nom de l'Academic Year

    Returns:
        dict: Résultats de la classe avec statistiques
    """
    students = frappe.get_all(
        "Student",
        filters={"filiere": filiere, "niveau_actuel": niveau},
        pluck="name",
    )

    if not students:
        return {
            "filiere": filiere,
            "niveau": niveau,
            "academic_year": academic_year,
            "eleves": [],
            "total_eleves": 0,
            "admis": 0,
            "ajournes": 0,
        }

    resultats_classe = []
    admis = 0
    ajournes = 0

    for student in students:
        resultat_annuel = calculer_resultat_annee(student, academic_year)

        if resultat_annuel["decision"] == "Admis":
            admis += 1
        elif resultat_annuel["decision"] == "Ajourné":
            ajournes += 1

        resultats_classe.append({
            "student": student,
            "student_name": resultat_annuel.get("student_name", ""),
            "moyenne_annuelle": resultat_annuel["moyenne_annuelle"],
            "total_ue": resultat_annuel["total_ue"],
            "ue_validees": resultat_annuel["ue_validees"],
            "decision": resultat_annuel["decision"],
        })

    resultats_classe.sort(key=lambda x: x["moyenne_annuelle"], reverse=True)

    return {
        "filiere": filiere,
        "niveau": niveau,
        "academic_year": academic_year,
        "eleves": resultats_classe,
        "total_eleves": len(resultats_classe),
        "admis": admis,
        "ajournes": ajournes,
        "moyenne_classe": round(
            sum(e["moyenne_annuelle"] for e in resultats_classe) / len(resultats_classe), 2
        ) if resultats_classe else 0,
    }


def _get_credits(student, teaching_unit):
    """Récupère les crédits d'une UE pour un étudiant donné.

    Cherche d'abord dans les course_levels de la Teaching Unit
    en fonction du niveau de l'étudiant, sinon prend le champ
    credits directement sur la Teaching Unit.

    Args:
        student: Nom du Student
        teaching_unit: Nom de la Teaching Unit

    Returns:
        int: Nombre de crédits (0 si non trouvé)
    """
    student_niveau = frappe.db.get_value("Student", student, "niveau")
    if not student_niveau:
        student_niveau = frappe.db.get_value("Student", student, "niveau_actuel")
    if student_niveau:
        credits = frappe.db.get_value(
            "Course Field of study level item",
            {"parent": teaching_unit, "niveau": student_niveau},
            "course_poid",
        )
        if credits:
            return int(credits)

    credits = frappe.db.get_value("Teaching Unit", teaching_unit, "credits")
    return int(credits) if credits else 0


def calculer_mps(student, semestre, academic_year):
    """Calcule la Moyenne Pondérée Semestrielle (MPS) d'un étudiant.

    MPS(i) = (Σ Cj × Pj) / (Σ Cj)
    où Cj = crédits de l'UE j, Pj = point (grade) de l'UE j

    Args:
        student: Nom du Student
        semestre: "Semestre 1" ou "Semestre 2"
        academic_year: Nom de l'Academic Year

    Returns:
        dict: {mps, total_credits, credits_obtenus, resultats}
    """
    resultats = frappe.get_all(
        "Resultat Academique",
        filters={
            "student": student,
            "semestre": semestre,
            "academic_year": academic_year,
        },
        fields=["name", "teaching_unit", "note_pct", "point", "statut", "grade", "mention"],
    )

    student_doc = frappe.get_doc("Student", student)
    cycle = get_student_cycle(student_doc)
    seuil = get_seuil_validation(cycle)

    somme_cj_pj = 0
    somme_cj = 0
    credits_obtenus = 0

    for r in resultats:
        cj = _get_credits(student, r.teaching_unit)
        pj = r.point or 0
        somme_cj_pj += cj * pj
        somme_cj += cj
        if r.note_pct and r.note_pct >= seuil:
            credits_obtenus += cj

    mps = round(somme_cj_pj / somme_cj, 2) if somme_cj > 0 else 0

    return {
        "mps": mps,
        "total_credits": somme_cj,
        "credits_obtenus": credits_obtenus,
        "resultats": resultats,
    }


def calculer_index_semestre(student, academic_year, semestre):
    """Calcule l'index (i) d'un semestre dans le parcours de l'étudiant.

    Compte le nombre total de semestres antérieurs + le semestre courant.
    Ex: Semestre 1 de la 1ère année = 1, Semestre 2 de la 1ère année = 2,
        Semestre 1 de la 2ème année = 3, etc.

    Args:
        student: Nom du Student
        academic_year: Nom de l'Academic Year actuelle
        semestre: "Semestre 1" ou "Semestre 2"

    Returns:
        int: Index du semestre (i ≥ 1)
    """
    all_years = frappe.get_all(
        "Academic Year",
        fields=["name"],
    )
    all_years = sorted(
        all_years, key=lambda y: _debut_annee(y.name)
    )

    current_start = _debut_annee(academic_year)

    index = 0
    for year in all_years:
        if _debut_annee(year.name) < current_start:
            index += 2
        elif year.name == academic_year:
            index += 1
            break

    if semestre in ("Semestre 2", "S2"):
        index += 1

    return max(index, 1)


def calculer_mpc(student, academic_year, semestre=None):
    """Calcule la Moyenne Pondérée Cumulée (MPC) d'un étudiant.

    MPC(i) = [MPC(i-1) × (i-1) + MPS(i)] / i
    MPC(1) = MPS(1)

    Args:
        student: Nom du Student
        academic_year: Nom de l'Academic Year
        semestre: Si spécifié, calcule la MPC jusqu'à ce semestre.
                  Sinon, calcule la MPC jusqu'au dernier semestre disponible.

    Returns:
        dict: {mpc, semester_index, mps_result}
    """
    tous_resultats_semestre = frappe.get_all(
        "Resultat Semestre",
        filters={"student": student},
        fields=["semestre", "academic_year", "mps", "semester_index"],
        order_by="semester_index asc",
    )

    if not tous_resultats_semestre:
        return {"mpc": 0, "semester_index": 0}

    mpc = 0
    for rs in tous_resultats_semestre:
        i = rs.semester_index
        if i == 1:
            mpc = rs.mps
        else:
            mpc = round((mpc * (i - 1) + rs.mps) / i, 2)

    return {"mpc": mpc, "semester_index": len(tous_resultats_semestre)}


@frappe.whitelist()
def calculer_et_sauvegarder_mps_mpc(student, semestre, academic_year):
    """Calcule la MPS et MPC d'un étudiant et sauvegarde le Resultat Semestre.

    Args:
        student: Nom du Student
        semestre: "Semestre 1" ou "Semestre 2"
        academic_year: Nom de l'Academic Year

    Returns:
        dict: {mps, mpc, total_credits, credits_obtenus, mention, decision}
    """
    mps_data = calculer_mps(student, semestre, academic_year)
    mps = mps_data["mps"]
    total_credits = mps_data["total_credits"]
    credits_obtenus = mps_data["credits_obtenus"]

    semester_index = calculer_index_semestre(student, academic_year, semestre)

    existing = frappe.db.get_value(
        "Resultat Semestre",
        {
            "student": student,
            "academic_year": academic_year,
            "semestre": semestre,
        },
        "name",
    )

    if existing:
        rs = frappe.get_doc("Resultat Semestre", existing)
    else:
        rs = frappe.new_doc("Resultat Semestre")

    rs.student = student
    rs.academic_year = academic_year
    rs.semestre = semestre
    rs.semester_index = semester_index
    rs.mps = mps
    rs.total_credits = total_credits
    rs.credits_obtenus = credits_obtenus

    student_doc = frappe.get_doc("Student", student)
    cycle = get_student_cycle(student_doc)
    seuil = get_seuil_validation(cycle)

    rs.decision = "Admis" if mps >= seuil else "Ajourné"

    if existing:
        rs.save()
    else:
        rs.insert()

    tous_resultats = frappe.get_all(
        "Resultat Semestre",
        filters={"student": student},
        fields=["mps", "semester_index"],
        order_by="semester_index asc",
    )

    mpc = 0
    for i, res in enumerate(tous_resultats, 1):
        if i == 1:
            mpc = res.mps
        else:
            mpc = round((mpc * (i - 1) + res.mps) / i, 2)

    frappe.db.set_value("Resultat Semestre", rs.name, "mpc", mpc)

    return {
        "name": rs.name,
        "mps": mps,
        "mpc": mpc,
        "total_credits": total_credits,
        "credits_obtenus": credits_obtenus,
        "mention": rs.mention,
        "decision": rs.decision,
    }
