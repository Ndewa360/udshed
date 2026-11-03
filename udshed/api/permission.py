import frappe
from frappe.utils.user import is_website_user

ROLE_ETUDIANT = "Student"
# Rôles qui voient toutes les réinscriptions / progressions (selon leurs DocPerm).
ROLES_PERSONNEL = {
    "System Manager", "Coordonateur", "Agent de scolarité", "Comptable", "Registration Manager",
}


def has_app_permission():
    if frappe.session.user == "Administrator":
        return True
    if is_website_user():
        return False

    return True


def _etudiant_restreint(user):
    """Matricule si `user` est un étudiant sans rôle du personnel, sinon None.

    Retourne "" pour un étudiant sans dossier lié (il ne verra rien).
    """
    user = user or frappe.session.user
    if user == "Administrator":
        return None
    roles = set(frappe.get_roles(user))
    if ROLE_ETUDIANT not in roles or roles & ROLES_PERSONNEL:
        return None
    return frappe.db.get_value("Student", {"utilisateur": user}, "name") or ""


def _condition_etudiant(doctype, user):
    matricule = _etudiant_restreint(user)
    if matricule is None:
        return ""
    return "`tab{0}`.`student` = {1}".format(doctype, frappe.db.escape(matricule))


def _acces_etudiant(doc, user):
    # Un hook has_permission ne peut que refuser : True = aucune restriction
    # supplémentaire, les DocPerm standard s'appliquent ensuite.
    matricule = _etudiant_restreint(user)
    if matricule is None:
        return True
    return bool(matricule) and doc.student == matricule


def academic_reregistration_query(user=None):
    return _condition_etudiant("Academic Reregistration", user)


def academic_reregistration_has_permission(doc, ptype=None, user=None):
    return _acces_etudiant(doc, user)


def progression_query(user=None):
    return _condition_etudiant("Progression Academique", user)


def progression_has_permission(doc, ptype=None, user=None):
    return _acces_etudiant(doc, user)
