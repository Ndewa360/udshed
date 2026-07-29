import frappe
from frappe.query_builder import DocType


@frappe.whitelist()
def verify_student(matricule):
    """
    Vérifie le matricule et retourne les infos de l'étudiant
    pour pré-remplir le formulaire de réinscription.
    """
    if not frappe.db.exists("Student", matricule):
        frappe.throw(f"Aucun étudiant trouvé avec le matricule {matricule}")

    student = frappe.get_doc("Student", matricule)

    # Récupérer la dernière réinscription de l'étudiant
    last_reregistration = frappe.get_all(
        "Academic Reregistration",
        filters={"student": matricule},
        fields=["filiere", "niveau", "semestre", "academic_year"],
        order_by="creation desc",
        limit_page_length=1
    )

    # Si pas de réinscription précédente, essayer l'inscription initiale
    filiere = None
    niveau = None
    semestre = None

    if last_reregistration:
        filiere = last_reregistration[0].filiere
        niveau = last_reregistration[0].niveau
        semestre = last_reregistration[0].semestre
    else:
        # Fallback: utiliser la filière du student
        filiere = student.filiere
        niveau = student.niveau_actuel

    return {
        "exists": True,
        "student_name": f"{student.nom} {student.prenom}",
        "matricule": student.name,
        "email": student.email,
        "filiere": filiere,
        "niveau": niveau,
        "semestre": semestre
    }


@frappe.whitelist()
def get_student_grades_and_debts(matricule, academic_year, filiere, niveau):
    """
    Récupère les notes de l'étudiant et détermine les dettes académiques.
    Lecture seule - les notes viennent du coéquipier (saisie des notes).
    """
    if not frappe.db.exists("Student", matricule):
        frappe.throw(f"Aucun étudiant trouvé avec le matricule {matricule}")

    # Récupérer la note minimale de validation
    note_minimale = 10  # Valeur par défaut

    # Chercher les notes de l'étudiant pour le niveau précédent
    # On cherche dans Session Examen Note
    SessionExamenNote = DocType("Session Examen Note")
    TeachingUnit = DocType("Teaching Unit")
    CourseFieldOfStudyLevelItem = DocType("Course Field of study level item")
    CourseFieldOfStudy = DocType("Field of study")

    # Récupérer les notes existantes
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
def create_reregistration(doc_data):
    """
    Crée une réinscription pour un étudiant.
    Le statut initial est 'En attente' (validation par le coordinateur).
    """
    if isinstance(doc_data, str):
        import json
        doc_data = json.loads(doc_data)

    # Vérifier que la session est ouverte
    session_name = doc_data.get("reinscription_session")
    if session_name:
        session = frappe.db.exists("Reinscription", {
            "name": session_name,
            "statut": "Ouverte"
        })
        if not session:
            frappe.throw("La session de réinscription sélectionnée n'est pas ouverte.")

    # Vérifier les doublons
    existing = frappe.db.exists("Academic Reregistration", {
        "student": doc_data.get("student"),
        "academic_year": doc_data.get("academic_year"),
        "niveau": doc_data.get("niveau")
    })
    if existing:
        frappe.throw("Une réinscription existe déjà pour cet étudiant, cette année et ce niveau.")

    # Créer le document
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
    frappe.db.commit()

    return {
        "status": True,
        "name": doc.name,
        "message": "Réinscription enregistrée avec succès. En attente de validation par le coordinateur."
    }


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
