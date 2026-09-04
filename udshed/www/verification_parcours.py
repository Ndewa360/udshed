import frappe
from frappe import _

from udshed.utils.reregistration import has_reregistered


def get_context(context):
    context.title = "Vérification du Parcours"

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
    context.active = "parcours"

    # Accès conditionnel : le parcours est visible après réinscription
    context.has_reregistered, context.reregistration = has_reregistered(student.name)
    if not context.has_reregistered:
        context.results = []
        context.matieres_a_reprendre = []
        context.has_retakes = False
        context.blocked = True
        return context

    context.blocked = False
    # Récupérer les résultats de l'étudiant
    context.results = _get_student_results(student)
    context.matieres_a_reprendre = _get_retake_courses(context.results)
    context.has_retakes = len(context.matieres_a_reprendre) > 0


def _get_student(user_email):
    student_name = frappe.db.get_value("Student", {"utilisateur": user_email}, "name")
    if student_name:
        return frappe.get_doc("Student", student_name)
    return None


def _get_initials(student):
    prenom = (student.prenom or "")[:1]
    nom = (student.nom or "")[:1]
    return f"{prenom}{nom}".upper()


def _get_student_results(student):
    """Récupère les résultats de l'étudiant pour l'année en cours."""
    # Récupérer la dernière année académique
    current_year = frappe.db.get_single_value("Udshed Setting", "current_year")
    if not current_year:
        current_year = frappe.db.get_value("Academic Year", {}, "name", order_by="creation desc")

    results = frappe.get_all(
        "Resultat Semestre",
        filters={
            "student": student.name,
            "academic_year": current_year
        },
        fields=["name", "semestre", "mps", "mpc", "credits_obtenus", "mention", "decision"]
    )

    # Si pas de résultats semestre, récupérer les UV
    if not results:
        uv_results = frappe.get_all(
            "Resultat Academique",
            filters={
                "student": student.name,
                "academic_year": current_year
            },
            fields=["name", "teaching_unit", "ue_name", "note_finale", "statut", "mention"]
        )
        return uv_results

    return results


def _get_retake_courses(results):
    """Identifie les matières à reprendre."""
    retakes = []
    for result in results:
        if hasattr(result, 'statut') and result.statut == "Non Validé":
            retakes.append(result)
        elif hasattr(result, 'decision') and result.decision == "Ajourné":
            retakes.append(result)
    return retakes
