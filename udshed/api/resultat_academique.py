# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from udshed.grade_calculation import get_active_formula


@frappe.whitelist()
def calculer_resultat_session(student, session_examen):
    """Calcule le résultat académique pour un étudiant donné dans une session d'examen.

    Prend la meilleure note entre session normale et session de rattrapage.
    Crée ou met à jour le Resultat Academique correspondant.

    Args:
        student: Nom du Student
        session_examen: Nom de la Session Examen (session normale)

    Returns:
        dict: Résultat calculé
    """
    session_doc = frappe.get_doc("Session Examen", session_examen)

    note_normale = frappe.db.get_value(
        "Session Examen Note",
        {
            "student": student,
            "session_examen": session_examen,
            "statut": "Publié",
        },
        ["name", "teaching_unit", "note_finale", "note_pct", "grade", "point", "mention",
         "note_examen_active", "note_examen_rattrapage", "session_examen"],
        as_dict=True,
    )

    if not note_normale:
        frappe.throw(
            _("Aucune note publiée trouvée pour l'étudiant {0} dans la session {1}").format(
                student, session_examen
            )
        )

    teaching_unit = note_normale.teaching_unit

    note_rattrapage = None
    session_rattrapage_name = None
    rattrapages = frappe.get_all(
        "Session Examen",
        filters={
            "academic_year": session_doc.academic_year,
            "semestre": session_doc.semestre,
            "type_dexamen": "Examen de rattrapage",
        },
        pluck="name",
    )

    for sess_r in session_rattrapages:
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
                session_rattrapage_name = sess_r

    if note_rattrapage and note_rattrapage.note_finale > note_normale.note_finale:
        resultat_source = note_rattrapage
        est_rattrapage = True
    else:
        resultat_source = note_normale
        est_rattrapage = False

    student_doc = frappe.get_doc("Student", student)
    cycle = student_doc.cycle or "Licence"
    formula = get_active_formula(cycle)
    seuil = formula.seuil_validation

    note_pct = resultat_source.note_pct
    statut = "Validé" if note_pct >= seuil else "Non Validé"

    grade = resultat_source.grade
    point = resultat_source.point
    mention = resultat_source.mention

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
    res.grade = grade
    res.point = point
    res.mention = mention
    res.statut = statut
    res.est_rattrapage = est_rattrapage
    res.session_normale = session_examen
    res.session_rattrapage = session_rattrapage_name

    if existing:
        res.save()
    else:
        res.insert()

    frappe.db.commit()

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
        "session_normale": session_examen,
        "session_rattrapage": session_rattrapage_name,
    }


@frappe.whitelist()
def calculer_resultat_semestre(student, semestre, academic_year):
    """Calcule les résultats de toutes les UE pour un semestre donné.

    Args:
        student: Nom du Student
        semestre: "S1" ou "S2"
        academic_year: Nom de l'Academic Year

    Returns:
        dict: Résultats du semestre avec MPS pondérée et nombre d'UE validées
    """
    sessions = frappe.get_all(
        "Session Examen",
        filters={
            "academic_year": academic_year,
            "semestre": semestre,
            "type_dexamen": "Examen normal",
        },
        pluck="name",
    )

    resultats = []
    for session in sessions:
        try:
            resultat = calculer_resultat_session(student, session)
            resultats.append(resultat)
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
    cycle = student_doc.cycle or "Licence"
    formula = get_active_formula(cycle)
    seuil = formula.seuil_validation

    somme_cj_pj = 0
    somme_cj = 0
    for r in resultats:
        credits = frappe.db.get_value(
            "Teaching Unit", r["teaching_unit"], "credits"
        ) or 0
        somme_cj_pj += credits * r["point"]
        somme_cj += credits

    mps = round(somme_cj_pj / somme_cj, 2) if somme_cj > 0 else 0

    ue_validees = sum(1 for r in resultats if r["note_pct"] >= seuil)
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
    resultats_s1 = calculer_resultat_semestre(student, "S1", academic_year)
    resultats_s2 = calculer_resultat_semestre(student, "S2", academic_year)

    tous_resultats = resultats_s1["resultats"] + resultats_s2["resultats"]

    if not tous_resultats:
        return {
            "student": student,
            "academic_year": academic_year,
            "moyenne_annuelle": 0,
            "total_ue": 0,
            "ue_validees": 0,
            "decision": "En attente",
            "resultats_s1": resultats_s1,
            "resultats_s2": resultats_s2,
        }

    total_note_pct = sum(r["note_pct"] for r in tous_resultats)
    moyenne_annuelle = round(total_note_pct / len(tous_resultats), 2)

    student_doc = frappe.get_doc("Student", student)
    cycle = student_doc.cycle or "Licence"
    formula = get_active_formula(cycle)
    seuil = formula.seuil_validation

    ue_validees = sum(1 for r in tous_resultats if r["note_pct"] >= seuil)
    ue_non_validees = len(tous_resultats) - ue_validees

    if ue_non_validees == 0:
        decision = "Admis"
    else:
        decision = "Ajourné"

    for r in resultats_s1["resultats"] + resultats_s2["resultats"]:
        if r.get("name"):
            frappe.db.set_value("Resultat Academique", r["name"], "decision_annee", decision)
    frappe.db.commit()

    return {
        "student": student,
        "student_name": resultats_s1["resultats"][0]["student_name"] if resultats_s1["resultats"] else "",
        "academic_year": academic_year,
        "moyenne_annuelle": moyenne_annuelle,
        "total_ue": len(tous_resultats),
        "ue_validees": ue_validees,
        "ue_non_validees": ue_non_validees,
        "decision": decision,
        "resultats_s1": resultats_s1,
        "resultats_s2": resultats_s2,
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
        filters={"niveau": niveau},
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
        semestre: "S1" ou "S2"
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
    cycle = student_doc.cycle or "Licence"
    formula = get_active_formula(cycle)
    seuil = formula.seuil_validation

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
    Ex: S1 de la 1ère année = 1, S2 de la 1ère année = 2,
        S1 de la 2ème année = 3, etc.

    Args:
        student: Nom du Student
        academic_year: Nom de l'Academic Year actuelle
        semestre: "S1" ou "S2"

    Returns:
        int: Index du semestre (i ≥ 1)
    """
    all_years = frappe.get_all(
        "Academic Year",
        order_by="year_start_date asc",
        fields=["name", "year_start_date"],
    )

    current_year_doc = frappe.get_doc("Academic Year", academic_year)
    current_start = current_year_doc.year_start_date

    index = 0
    for year in all_years:
        if year.year_start_date and year.year_start_date < current_start:
            index += 2
        elif year.name == academic_year:
            index += 1
            break

    if semestre == "S2":
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
        semestre: "S1" ou "S2"
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
    cycle = student_doc.cycle or "Licence"
    formula = get_active_formula(cycle)
    seuil = formula.seuil_validation

    if mps >= seuil:
        rs.decision = "Admis"
    else:
        rs.decision = "Ajourné"

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
    frappe.db.commit()

    return {
        "name": rs.name,
        "mps": mps,
        "mpc": mpc,
        "total_credits": total_credits,
        "credits_obtenus": credits_obtenus,
        "mention": rs.mention,
        "decision": rs.decision,
    }
