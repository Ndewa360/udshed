import frappe
from frappe.query_builder import DocType


@frappe.whitelist()
def verify_student(matricule):
    """
    Vérifie le matricule et retourne les infos de l'étudiant
    pour pré-remplir le formulaire de réinscription.
    Calcule automatiquement le niveau suivant selon l'ordre des niveaux.
    """
    if not frappe.db.exists("Student", matricule):
        frappe.throw(f"Aucun étudiant trouvé avec le matricule {matricule}")

    student = frappe.get_doc("Student", matricule)

    last_reregistration = frappe.get_all(
        "Academic Reregistration",
        filters={"student": matricule},
        fields=["filiere", "niveau", "semestre", "academic_year"],
        order_by="creation desc",
        limit_page_length=1
    )

    filiere = None
    niveau = None
    niveau_suivant = None
    semestre = None

    if last_reregistration:
        filiere = last_reregistration[0].filiere
        niveau = last_reregistration[0].niveau
        semestre = last_reregistration[0].semestre
    else:
        filiere = student.filiere
        niveau = student.niveau_actuel

    if filiere and niveau:
        filiere_doc = frappe.get_doc("Field of study", filiere)
        niveau_actuel_order = None
        for row in filiere_doc.field_of_study_level:
            if row.level == niveau:
                niveau_actuel_order = row.order
                break
        if niveau_actuel_order:
            for row in filiere_doc.field_of_study_level:
                if row.order == niveau_actuel_order + 1:
                    niveau_suivant = row.level
                    break

    return {
        "exists": True,
        "student_name": f"{student.nom} {student.prenom}",
        "matricule": student.name,
        "email": student.email,
        "filiere": filiere,
        "niveau": niveau,
        "niveau_suivant": niveau_suivant,
        "semestre": semestre
    }


@frappe.whitelist()
def get_student_grades_and_debts(matricule, academic_year, filiere, niveau, semestre=None):
    """
    Récupère les notes de l'étudiant et détermine les dettes académiques.
    Peut être filtré par semestre si spécifié.
    Lecture seule - les notes viennent du coéquipier (saisie des notes).
    """
    if not frappe.db.exists("Student", matricule):
        frappe.throw(f"Aucun étudiant trouvé avec le matricule {matricule}")

    note_minimale = 10

    # Chercher les notes de l'étudiant pour le niveau précédent
    # On cherche dans Session Examen Note
    SessionExamenNote = DocType("Session Examen Note")
    TeachingUnit = DocType("Teaching Unit")
    CourseFieldOfStudyLevelItem = DocType("Course Field of study level item")
    CourseFieldOfStudy = DocType("Field of study")

    notes_query = (
        frappe.qb.from_(SessionExamenNote)
        .join(TeachingUnit)
        .on(TeachingUnit.name == SessionExamenNote.teaching_unit)
        .join(CourseFieldOfStudyLevelItem)
        .on(CourseFieldOfStudyLevelItem.parent == TeachingUnit.name)
        .join(CourseFieldOfStudy)
        .on(CourseFieldOfStudy.name == CourseFieldOfStudyLevelItem.filiere)
        .select(
            SessionExamenNote.teaching_unit,
            SessionExamenNote.note_finale,
            SessionExamenNote.session_examen,
            TeachingUnit.intitule_cours,
            TeachingUnit.semestre,
            CourseFieldOfStudyLevelItem.niveau
        )
        .where(
            (SessionExamenNote.student == matricule) &
            (CourseFieldOfStudyLevelItem.filiere == filiere)
        )
    )

    if semestre and semestre != "Les deux":
        notes_query = notes_query.where(TeachingUnit.semestre == semestre)

    notes = notes_query.run(as_dict=True)

    # Séparer les matières validées et les dettes
    matieres_validees = []
    matieres_dettes = []

    for note in notes:
        note_finale = note.note_finale or 0
        is_valide = note_finale >= note_minimale

        matiere_info = {
            "teaching_unit": note.teaching_unit,
            "intitule": note.intitule_cours,
            "semestre": note.semestre,
            "note": note_finale,
            "valide": is_valide
        }

        if is_valide:
            matieres_validees.append(matiere_info)
        else:
            matieres_dettes.append(matiere_info)

    return {
        "matricule": matricule,
        "note_minimale": note_minimale,
        "matieres_validees": matieres_validees,
        "matieres_dettes": matieres_dettes,
        "total_dettes": len(matieres_dettes)
    }


@frappe.whitelist()
def create_reregistration(doc_data, courses=None):
    """
    Crée une réinscription pour un étudiant.
    Le statut initial est 'En attente' (validation par le coordinateur).
    L'étudiant peut choisir les matières auxquelles il s'inscrit via le paramètre courses.
    """
    if isinstance(doc_data, str):
        import json
        doc_data = json.loads(doc_data)

    if isinstance(courses, str):
        import json
        courses = json.loads(courses)

    session_name = doc_data.get("reinscription_session")
    if session_name:
        session = frappe.db.exists("Reinscription", {
            "name": session_name,
            "statut": "Ouverte"
        })
        if not session:
            frappe.throw("La session de réinscription sélectionnée n'est pas ouverte.")

    existing = frappe.db.exists("Academic Reregistration", {
        "student": doc_data.get("student"),
        "academic_year": doc_data.get("academic_year"),
        "niveau": doc_data.get("niveau")
    })
    if existing:
        frappe.throw("Une réinscription existe déjà pour cet étudiant, cette année et ce niveau.")

    doc = frappe.get_doc({
        "doctype": "Academic Reregistration",
        "student": doc_data.get("student"),
        "academic_year": doc_data.get("academic_year"),
        "reinscription_session": doc_data.get("reinscription_session"),
        "filiere": doc_data.get("filiere"),
        "niveau": doc_data.get("niveau"),
        "semestre": doc_data.get("semestre"),
        "statut": "En attente"
    })

    doc.insert(ignore_permissions=True)

    if courses:
        noms_cours = set(courses)
        doc.cours_inscrits = [
            c for c in doc.cours_inscrits
            if c.teaching_unit in noms_cours
        ]
        doc.save(ignore_permissions=True)

    frappe.db.commit()

    return {
        "status": True,
        "name": doc.name,
        "message": "Réinscription enregistrée avec succès. En attente de validation par le coordinateur."
    }


@frappe.whitelist()
def get_courses_for_semester(filiere, niveau_label, academic_year, semestre):
    """
    Retourne les matières disponibles pour un niveau, une filière,
    une année et un semestre donnés.
    """
    filiere_doc = frappe.get_doc("Field of study", filiere)
    niveau_name = None
    for row in filiere_doc.field_of_study_level:
        if row.level == niveau_label:
            niveau_name = row.name
            break

    if not niveau_name:
        return []

    TeachingUnit = DocType("Teaching Unit")
    CourseLevel = DocType("Course Field of study level item")

    query = (
        frappe.qb.from_(TeachingUnit)
        .join(CourseLevel).on(CourseLevel.parent == TeachingUnit.name)
        .select(
            TeachingUnit.name,
            TeachingUnit.intitule_cours,
            TeachingUnit.semestre
        )
        .where(
            (TeachingUnit.academic_year == academic_year) &
            (CourseLevel.filiere == filiere) &
            (CourseLevel.niveau == niveau_name)
        )
    )

    if semestre and semestre != "Les deux":
        query = query.where(TeachingUnit.semestre == semestre)

    return query.run(as_dict=True)


@frappe.whitelist()
def get_reregistration_status(matricule, academic_year):
    """
    Vérifie si l'étudiant a déjà une réinscription en cours pour l'année.
    """
    reregistration = frappe.get_all(
        "Academic Reregistration",
        filters={
            "student": matricule,
            "academic_year": academic_year
        },
        fields=["name", "statut", "filiere", "niveau", "semestre"],
        order_by="creation desc",
        limit_page_length=1
    )

    if not reregistration:
        return {"has_reregistration": False}

    return {
        "has_reregistration": True,
        "reregistration": reregistration[0]
    }
