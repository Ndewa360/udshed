# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Assiduité des étudiants : appel en séance et seuil d'absences.

L'enseignant fait l'appel d'une séance du planning (page « Appel en séance »,
utilisable au téléphone). Quand un étudiant atteint le seuil d'absences non
justifiées d'une matière (réglages : « Seuil d'absences par matière », 0 =
désactivé), l'étudiant et la coordination sont prévenus. Les sanctions restent
une décision humaine de la coordination.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate

from udshed.notifications import emettre
from udshed.notifications.attentes import coordination, enseignants_du_cours, utilisateur_etudiant

ROLES_GESTION = ("System Manager", "Coordonateur", "Agent de scolarité")
STATUTS = ("Présent", "Absent", "Retard", "Excusé")


def _peut_faire_appel(teaching_unit, user=None):
	user = user or frappe.session.user
	if user == "Administrator" or set(frappe.get_roles(user)) & set(ROLES_GESTION):
		return True
	return user in enseignants_du_cours(teaching_unit)


def valider_appel(doc):
	item = frappe.db.get_value("Planning Item", doc.planning_item, ["cours", "date", "academic_year", "status"],
							   as_dict=True)
	if not item:
		frappe.throw(_("Séance introuvable."))
	if item.status == "Annulée":
		frappe.throw(_("Cette séance est annulée."))
	if not _peut_faire_appel(item.cours):
		frappe.throw(_("Seul un enseignant du cours ou la coordination peut faire l'appel."), frappe.PermissionError)
	doc.teaching_unit = item.cours
	doc.date_seance = getdate(item.date)
	doc.academic_year = item.academic_year
	classe = frappe.db.get_value("Course Field of study level item", {"parent": item.cours}, ["filiere", "niveau"],
								 as_dict=True) or {}
	doc.filiere, doc.niveau = classe.get("filiere"), classe.get("niveau")
	if not doc.fait_par:
		doc.fait_par = frappe.session.user
	vus = set()
	for p in doc.presences:
		if p.student in vus:
			frappe.throw(_("L'étudiant {0} figure deux fois dans l'appel.").format(p.student))
		vus.add(p.student)
		p.nom = p.nom or _nom(p.student)
	doc.absents = sum(1 for p in doc.presences if p.statut == "Absent")


def _nom(student):
	s = frappe.db.get_value("Student", student, ["nom", "prenom"], as_dict=True) or {}
	return " ".join(x for x in (s.get("nom"), s.get("prenom")) if x) or student


def absences(student, teaching_unit):
	return frappe.db.sql("""
		SELECT COUNT(*) FROM `tabPresence Etudiant` p
		INNER JOIN `tabAppel Seance` a ON a.name = p.parent
		WHERE p.student = %s AND a.teaching_unit = %s AND p.statut = 'Absent'
	""", (student, teaching_unit))[0][0]


def controler_seuils(doc):
	seuil = cint(frappe.db.get_single_value("Udshed Setting", "seuil_absences"))
	if not seuil:
		return
	intitule = frappe.db.get_value("Teaching Unit", doc.teaching_unit, "intitule_cours") or doc.teaching_unit
	for p in doc.presences:
		if p.statut != "Absent":
			continue
		n = absences(p.student, doc.teaching_unit)
		if n < seuil:
			continue
		s = frappe.db.get_value("Student", p.student, ["utilisateur", "email", "filiere"], as_dict=True) or {}
		emettre("absences_seuil", [{"user": s.get("utilisateur"), "email": s.get("email")}] + coordination(s.get("filiere")),
				_("{0} : {1} absences en {2}").format(p.nom or p.student, n, intitule),
				_("Le seuil de {0} absences non justifiées est atteint. La coordination décidera de la suite.").format(seuil),
				reference=("Appel Seance", doc.name), cle=f"{p.student}:{doc.teaching_unit}:{seuil}")


# ---------------------------------------------------------------------- #
#  API de la page « Appel en séance »
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def mes_seances(date_debut=None, date_fin=None):
	"""Séances des cours de l'enseignant connecté (ou toutes pour la coordination), avec l'état de l'appel."""
	from frappe.utils import add_days, nowdate

	debut = getdate(date_debut or add_days(nowdate(), -7))
	fin = getdate(date_fin or add_days(nowdate(), 1))
	teacher = frappe.db.get_value("Teacher", {"user": frappe.session.user}, "name") or frappe.db.get_value(
		"Teacher", {"email": frappe.session.user}, "name")
	gestion = bool(set(frappe.get_roles()) & set(ROLES_GESTION))
	if not (teacher or gestion):
		frappe.throw(_("Réservé aux enseignants et à la coordination."), frappe.PermissionError)
	filtres = {"date": ["between", [f"{debut} 00:00:00", f"{fin} 23:59:59"]], "status": ["!=", "Annulée"]}
	if not gestion:
		cours = frappe.get_all("Course Teacher Item", filters={"enseignant": teacher}, pluck="parent")
		filtres["cours"] = ["in", cours or [""]]
	res = []
	for item in frappe.get_all("Planning Item", filters=filtres, fields=["name", "cours", "date", "type", "salle"],
							   order_by="date desc", limit=200):
		appel = frappe.db.get_value("Appel Seance", {"planning_item": item.name}, ["name", "absents"], as_dict=True)
		res.append({**item, "intitule": frappe.db.get_value("Teaching Unit", item.cours, "intitule_cours"),
					"appel": appel.name if appel else None, "absents": appel.absents if appel else None})
	return res


@frappe.whitelist()
def preparer_appel(planning_item):
	item = frappe.db.get_value("Planning Item", planning_item, ["cours", "date"], as_dict=True)
	if not item:
		frappe.throw(_("Séance introuvable."))
	if not _peut_faire_appel(item.cours):
		frappe.throw(_("Seul un enseignant du cours ou la coordination peut faire l'appel."), frappe.PermissionError)
	existant = frappe.db.get_value("Appel Seance", {"planning_item": planning_item}, "name")
	if existant:
		doc = frappe.get_doc("Appel Seance", existant)
		lignes = [{"student": p.student, "nom": p.nom, "statut": p.statut, "justification": p.justification}
				  for p in doc.presences]
	else:
		from udshed.notifications.evenements import etudiants_du_cours

		lignes = [{"student": s, "nom": _nom(s), "statut": "Présent", "justification": ""}
				  for s in etudiants_du_cours(item.cours)]
	lignes.sort(key=lambda l: (l["nom"] or "").lower())
	return {"planning_item": planning_item, "intitule": frappe.db.get_value("Teaching Unit", item.cours, "intitule_cours"),
			"date": item.date, "appel": existant, "presences": lignes}


@frappe.whitelist(methods=["POST"])
def enregistrer_appel(planning_item, presences):
	presences = frappe.parse_json(presences) if isinstance(presences, str) else presences
	existant = frappe.db.get_value("Appel Seance", {"planning_item": planning_item}, "name")
	doc = frappe.get_doc("Appel Seance", existant) if existant else frappe.new_doc("Appel Seance")
	doc.planning_item = planning_item
	doc.set("presences", [])
	for p in presences or []:
		if p.get("statut") not in STATUTS:
			frappe.throw(_("Statut de présence invalide : {0}").format(p.get("statut")))
		doc.append("presences", {"student": p["student"], "statut": p["statut"],
								 "justification": p.get("justification") or ""})
	doc.save(ignore_permissions=True)  # droits vérifiés dans valider_appel
	return {"name": doc.name, "absents": doc.absents}
