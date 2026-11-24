"""Cloisonnement des données personnelles pour les comptes étudiants.

Le rôle « Student » a besoin de lire SA fiche Student, SON Inscription
Academique et SES Resultat Academique (espace étudiant, réinscription). Sans restriction, la permission
de lecture du DocType lui donnait accès à toutes les fiches de l'établissement
(liste, API REST, export). Ces hooks limitent un compte uniquement étudiant à
ses propres documents ; le personnel n'est pas affecté.
"""

import frappe

from udshed.utils.securite import est_personnel


def _etudiant_seul(user):
	if not user or user in ("Administrator", "Guest"):
		return False
	return "Student" in frappe.get_roles(user) and not est_personnel(user)


def _student_de(user):
	"""Nom du document Student lié au compte `user` (champ utilisateur, sinon email)."""
	return frappe.db.get_value("Student", {"utilisateur": user}, "name") or frappe.db.get_value(
		"Student", {"email": user}, "name"
	)


def _matricule_de(user):
	student = _student_de(user)
	if not student:
		return None
	return frappe.db.get_value("Student", student, "matricule") or student


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------
def student_query(user=None):
	user = user or frappe.session.user
	if not _etudiant_seul(user):
		return ""
	student = _student_de(user)
	if not student:
		return "1=0"
	return f"`tabStudent`.`name` = {frappe.db.escape(student)}"


def student_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if not _etudiant_seul(user):
		return True
	return doc.name == _student_de(user)


# ---------------------------------------------------------------------------
# Inscription Academique (liée à l'étudiant par le matricule)
# ---------------------------------------------------------------------------
def inscription_query(user=None):
	user = user or frappe.session.user
	if not _etudiant_seul(user):
		return ""
	matricule = _matricule_de(user)
	if not matricule:
		return "1=0"
	return f"`tabInscription Academique`.`matricule` = {frappe.db.escape(matricule)}"


def inscription_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if not _etudiant_seul(user):
		return True
	matricule = _matricule_de(user)
	return bool(matricule) and doc.get("matricule") == matricule


# ---------------------------------------------------------------------------
# Resultat Academique (champ Link « student »)
# ---------------------------------------------------------------------------
def resultat_query(user=None):
	user = user or frappe.session.user
	if not _etudiant_seul(user):
		return ""
	student = _student_de(user)
	if not student:
		return "1=0"
	return f"`tabResultat Academique`.`student` = {frappe.db.escape(student)}"


def resultat_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if not _etudiant_seul(user):
		return True
	return doc.get("student") == _student_de(user)
