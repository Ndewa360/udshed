import frappe
from frappe import _
from frappe.utils import getdate

from udshed.utils.reregistration import has_reregistered


def get_context(context):
    context.title = "Dashboard Étudiant"

    student_name = frappe.session.user
    if not student_name or student_name == "Guest":
        frappe.local.flags.redirect_location = "/connexion-etudiant"
        raise frappe.Redirect

    # Récupérer l'étudiant
    student = _get_student(student_name)
    if not student:
        frappe.local.flags.redirect_location = "/connexion-etudiant"
        raise frappe.Redirect

    context.student = student
    context.student_name = f"{student.prenom or ''} {student.nom or ''}".strip()
    context.initials = _get_initials(student)
    context.niveau = student.niveau_actuel or ""
    context.filiere_name = frappe.db.get_value("Field of study", student.filiere, "name_of_field") if student.filiere else ""
    context.active = "dashboard"

    # Statut réinscription
    context.has_reregistered, context.reregistration = has_reregistered(student.name)
    context.can_reregister, context.session = _check_reregistration_eligibility(student)
    context.notifications = _get_notifications(student)


def _get_student(user_email):
    """Récupère le document Student lié à l'utilisateur."""
    student_name = frappe.db.get_value("Student", {"utilisateur": user_email}, "name")
    if student_name:
        return frappe.get_doc("Student", student_name)
    return None


def _get_initials(student):
    """Retourne les initiales de l'étudiant."""
    prenom = (student.prenom or "")[:1]
    nom = (student.nom or "")[:1]
    return f"{prenom}{nom}".upper()


def _check_reregistration_eligibility(student):
    """Vérifie si l'étudiant peut se réinscrire."""
    # Chercher une session de réinscription ouverte
    sessions = frappe.get_all(
        "Session Reinscription",
        filters={"statut": "Ouverte"},
        fields=["name", "date_ouverture", "date_cloture", "academic_year"],
        order_by="date_ouverture desc"
    )

    today = getdate()

    for session in sessions:
        if session.date_ouverture <= today <= session.date_cloture:
            return True, session

    return False, None


def _get_notifications(student):
    """Récupère les notifications de l'étudiant."""
    notifications = []

    # Vérifier les sessions ouvertes
    sessions = frappe.get_all(
        "Session Reinscription",
        filters={"statut": "Ouverte"},
        fields=["date_cloture", "academic_year"]
    )

    for session in sessions:
        notifications.append({
            "text": f"Ré-inscription ouverte jusqu'au {session.date_cloture.strftime('%d/%m/%Y')}",
            "icon": "📅"
        })

    # Vérifier les paiements en attente
    # TODO: Ajouter la logique de paiement

    return notifications
