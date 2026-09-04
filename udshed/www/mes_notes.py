import frappe

from udshed.utils.reregistration import has_reregistered


def get_context(context):
    context.title = "Mes Notes"

    student_name = frappe.session.user
    if not student_name or student_name == "Guest":
        frappe.local.flags.redirect_location = "/connexion-etudiant"
        raise frappe.Redirect

    student = _get_student(student_name)
    if not student:
        frappe.local.flags.redirect_location = "/connexion-etudiant"
        raise frappe.Redirect

    context.student = student
    context.student_name = f"{student.prenom or ''} {student.nom or ''}".strip()
    context.initials = _get_initials(student)
    context.niveau = student.niveau_actuel or ""
    context.filiere_name = frappe.db.get_value("Field of study", student.filiere, "name_of_field") if student.filiere else ""
    context.active = "notes"

    # Accès restreint : réinscription requise pour voir ses notes
    context.has_reregistered, context.reregistration = has_reregistered(student.name)
    if not context.has_reregistered:
        context.semesters = []
        context.blocked = True
        return context

    context.blocked = False
    context.semesters = _get_semesters(student.name)


def _get_student(user_email):
    student_name = frappe.db.get_value("Student", {"utilisateur": user_email}, "name")
    if student_name:
        return frappe.get_doc("Student", student_name)
    return None


def _get_initials(student):
    prenom = (student.prenom or "")[:1]
    nom = (student.nom or "")[:1]
    return f"{prenom}{nom}".upper()


def _get_semesters(student_name):
    """Récupère les semestres et leurs UE avec notes pour l'affichage."""
    semesters = frappe.get_all(
        "Resultat Semestre",
        filters={"student": student_name},
        fields=[
            "name", "semestre", "academic_year", "semester_index",
            "mps", "mpc", "total_credits", "credits_obtenus", "mention", "decision",
        ],
        order_by="semester_index asc",
    )

    data = []
    for sem in semesters:
        year_label = frappe.db.get_value("Academic Year", sem.academic_year, "year_name") or sem.academic_year
        ues = frappe.get_all(
            "Resultat Academique",
            filters={
                "student": student_name,
                "semestre": sem.semestre,
                "academic_year": sem.academic_year,
            },
            fields=["ue_name", "teaching_unit", "note_finale", "grade", "mention", "statut"],
            order_by="ue_name asc",
        )
        ue_list = [{
            "intitule": ue.ue_name or ue.teaching_unit,
            "note_finale": ue.note_finale,
            "grade": ue.grade or "",
            "mention": ue.mention or "",
            "statut": ue.statut or "",
        } for ue in ues]

        data.append({
            "label": sem.semestre,
            "academic_year": year_label,
            "mps": sem.mps,
            "mpc": sem.mpc,
            "mention": sem.mention or "",
            "decision": sem.decision or "",
            "ues": ue_list,
        })

    return data
