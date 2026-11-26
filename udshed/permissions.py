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


# ---------------------------------------------------------------------------
# Candidatures : un coordonnateur (sans rôle de décision) ne voit que les
# dossiers des filières qu'il coordonne (Field of study Level.coordonateur).
# ---------------------------------------------------------------------------
ROLES_DECISION_CANDIDATURE = {"System Manager", "Registration Manager", "Agent de scolarité"}


def _coordonnateur_seul(user):
	if not user or user in ("Administrator", "Guest"):
		return False
	roles = set(frappe.get_roles(user))
	return "Coordonateur" in roles and not (roles & ROLES_DECISION_CANDIDATURE)


def filieres_coordonnees(user):
	from udshed.api.planning_permission import _teacher_name

	teacher = _teacher_name(user)
	if not teacher:
		return []
	return sorted(set(frappe.get_all(
		"Field of study Level", filters={"coordonateur": teacher, "parenttype": "Field of study"}, pluck="parent"
	)))


def candidature_query(user=None):
	user = user or frappe.session.user
	if not _coordonnateur_seul(user):
		return ""
	filieres = filieres_coordonnees(user)
	if not filieres:
		return "1=0"
	liste = ", ".join(frappe.db.escape(f) for f in filieres)
	return f"`tabSession Inscription Candidate`.`filiere` in ({liste})"


def candidature_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if not _coordonnateur_seul(user):
		return True
	return doc.filiere in filieres_coordonnees(user)


# ---------------------------------------------------------------------------
# Actes académiques : un étudiant ne voit que les siens.
# ---------------------------------------------------------------------------
def acte_query(user=None):
	user = user or frappe.session.user
	if not _etudiant_seul(user):
		return ""
	student = _student_de(user)
	if not student:
		return "1=0"
	return f"`tabActe Academique`.`student` = {frappe.db.escape(student)}"


def acte_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if not _etudiant_seul(user):
		return True
	return doc.student == _student_de(user)


# ---------------------------------------------------------------------------
# Diplômes et requêtes : un étudiant ne voit que les siens.
# ---------------------------------------------------------------------------
def _query_proprietaire(doctype, user):
	user = user or frappe.session.user
	if not _etudiant_seul(user):
		return ""
	student = _student_de(user)
	if not student:
		return "1=0"
	return f"`tab{doctype}`.`student` = {frappe.db.escape(student)}"


def _permission_proprietaire(doc, user):
	user = user or frappe.session.user
	if not _etudiant_seul(user):
		return True
	return doc.student == _student_de(user)


def diplome_query(user=None):
	return _query_proprietaire("Diplome Etudiant", user)


def diplome_has_permission(doc, ptype=None, user=None, debug=False):
	return _permission_proprietaire(doc, user)


def requete_query(user=None):
	return _query_proprietaire("Requete Etudiant", user)


def requete_has_permission(doc, ptype=None, user=None, debug=False):
	return _permission_proprietaire(doc, user)
