import frappe

from udshed.utils.reregistration import has_reregistered


def get_context(context):
    context.title = "Relevé de notes"

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
    context.active = "releve"

    # Accès restreint : l'étudiant doit être réinscrit pour voir son relevé
    context.has_reregistered, context.reregistration = has_reregistered(student.name)
    if not context.has_reregistered:
        context.semesters = []
        context.blocked = True
        return context

    context.blocked = False
    _transcript = _get_transcript(student.name)
    context.semesters = _transcript.get("semesters", [])
    context.transcript = _transcript


def _get_student(user_email):
    student_name = frappe.db.get_value("Student", {"utilisateur": user_email}, "name")
    if student_name:
        return frappe.get_doc("Student", student_name)
    return None


def _get_initials(student):
    prenom = (student.prenom or "")[:1]
    nom = (student.nom or "")[:1]
    return f"{prenom}{nom}".upper()


def _get_transcript(student_name):
    """Récupère les vraies données du relevé via le module note
    (même pipeline que le PDF officiel « Releve Notes »)."""
    from udshed.api.transcript import get_transcript_data

    student_doc = frappe.get_doc("Student", student_name)
    return get_transcript_data(student_doc)
