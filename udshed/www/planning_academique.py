import frappe
from frappe import _

from udshed.utils.reregistration import has_reregistered


def get_context(context):
    context.title = "Planning Académique"

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
    context.active = "planning"

    # Accès conditionnel : only après réinscription
    context.has_reregistered, context.reregistration = has_reregistered(student.name)
    if not context.has_reregistered:
        context.blocked = True
        context.academic_years = []
        context.faculties = []
        context.plannings = []
        return context

    context.blocked = False
    context.academic_years = frappe.get_all("Academic Year", fields=["name"], order_by="name desc")
    context.faculties = frappe.get_all("Faculty", fields=["name", "faculty_name"])

    # Filtres par défaut
    context.selected_year = frappe.form_dict.get("year", "")

    # Récupérer les plannings
    context.plannings = _get_plannings()


def _get_student(user_email):
    student_name = frappe.db.get_value("Student", {"utilisateur": user_email}, "name")
    if student_name:
        return frappe.get_doc("Student", student_name)
    return None


def _get_initials(student):
    prenom = (student.prenom or "")[:1]
    nom = (student.nom or "")[:1]
    return f"{prenom}{nom}".upper()


def _get_plannings():
    """Récupère les plannings."""
    plannings = frappe.get_all(
        "Calendar Planing",
        fields=["name", "nom_du_planing", "fuseau_horaire"],
        order_by="creation desc",
        limit_page_length=20
    )

    result = []
    for p in plannings:
        doc = frappe.get_doc("Calendar Planing", p.name)
        periods = []
        for item in doc.heure_planification or []:
            periods.append({
                "heure_debut": item.heure_de_debut,
                "heure_fin": item.heure_de_fin,
                "libelle": item.libelle,
                "status": item.status,
            })
        result.append({
            "name": p.name,
            "nom": p.nom_du_planing,
            "fuseau": p.fuseau_horaire,
            "periods": periods
        })

    return result
