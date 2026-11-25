"""Espace étudiant (desk) : lecture seule, limitée à l'étudiant connecté.

Chaque fonction part du compte connecté (Student.utilisateur) et ne lit que
SES données : sa classe, SES UE (réinscription de l'année), le planning de
SES cours, SES résultats. Aucune écriture, aucun paramètre ne permet de lire
la classe ou les notes d'un autre étudiant.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, getdate

ROLE = "Student"


def _mon_etudiant():
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Connectez-vous pour accéder à votre espace."), frappe.PermissionError)
	nom = frappe.db.get_value("Student", {"utilisateur": user}, "name") or frappe.db.get_value(
		"Student", {"email": user}, "name"
	)
	if not nom:
		frappe.throw(_("Aucune fiche étudiant n'est liée à votre compte. Contactez la scolarité."),
					 frappe.PermissionError)
	return frappe.get_doc("Student", nom)


def _annee_courante():
	return frappe.db.get_single_value("Udshed Setting", "current_year")


def _reinscription(student, academic_year=None):
	"""Réinscription (classe + UE) de l'étudiant pour l'année demandée, sinon la plus récente."""
	filtres = {"student": student.name}
	if academic_year:
		filtres["academic_year"] = academic_year
	nom = frappe.db.get_value("Academic Reregistration", filtres, "name", order_by="academic_year desc, creation desc")
	if not nom and academic_year:
		return _reinscription(student, None)
	return frappe.get_doc("Academic Reregistration", nom) if nom else None


def _annees(student):
	return sorted(
		set(frappe.get_all("Academic Reregistration", filters={"student": student.name}, pluck="academic_year")),
		reverse=True,
	)


def _libelle_filiere(filiere):
	return frappe.db.get_value("Field of study", filiere, "name_of_field") or filiere or ""


@frappe.whitelist()
def profil():
	s = _mon_etudiant()
	r = _reinscription(s, _annee_courante())
	return {
		"matricule": s.matricule or s.name,
		"nom_complet": " ".join(x for x in [s.nom, s.prenom] if x),
		"email": s.email or "",
		"photo": s.get("photo") or "",
		"filiere": _libelle_filiere(r.filiere if r else s.filiere),
		"niveau": (r.niveau if r else s.niveau_actuel) or "",
		"annee": r.academic_year if r else "",
		"annees": _annees(s),
		"annee_courante": _annee_courante() or "",
	}


@frappe.whitelist()
def ma_grille(academic_year=None):
	"""UE auxquelles l'étudiant est inscrit pour l'année, avec enseignants et crédits."""
	s = _mon_etudiant()
	r = _reinscription(s, academic_year or _annee_courante())
	if not r:
		return {"annee": academic_year or "", "cours": [], "total_credits": 0}
	cours = []
	for item in r.cours_inscrits:
		if not item.teaching_unit or (item.statut and item.statut != "Inscrit"):
			continue
		tu = frappe.db.get_value("Teaching Unit", item.teaching_unit,
								 ["name", "intitule_cours", "course", "semestre", "credits"], as_dict=True)
		if not tu:
			continue
		enseignants = []
		for t in frappe.get_all("Course Teacher Item", filters={"parent": tu.name, "parenttype": "Teaching Unit"},
								fields=["enseignant", "type_de_cours"]):
			nom = frappe.db.get_value("Teacher", t.enseignant, ["grade", "first_name", "last_name"], as_dict=True)
			if nom:
				libelle = " ".join(x for x in [nom.grade, nom.first_name, nom.last_name] if x)
				enseignants.append(f"{libelle} ({t.type_de_cours})" if t.type_de_cours else libelle)
		credits = item.credits or tu.credits or 0
		cours.append({
			"code": tu.course or tu.name,
			"intitule": tu.intitule_cours or item.intitule or tu.name,
			"semestre": tu.semestre or item.semestre or "",
			"credits": credits,
			"enseignants": enseignants,
			"source": item.source or "",
		})
	cours.sort(key=lambda c: (c["semestre"], c["intitule"]))
	return {"annee": r.academic_year, "filiere": _libelle_filiere(r.filiere), "niveau": r.niveau or "",
			"cours": cours, "total_credits": sum(float(c["credits"] or 0) for c in cours)}


def _cours_suivis(student, academic_year):
	"""Teaching Units suivies (cours liés compris : même enseignement)."""
	from udshed.utils.planning_conflits import groupe_du_cours

	r = _reinscription(student, academic_year)
	if not r:
		return set()
	cours = set()
	for item in r.cours_inscrits:
		if item.teaching_unit and (not item.statut or item.statut == "Inscrit"):
			cours |= groupe_du_cours(item.teaching_unit)
	return cours


def _hhmm(valeur):
	if isinstance(valeur, timedelta):
		total = int(valeur.total_seconds())
		return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
	texte = str(valeur or "")
	return texte[:5]


@frappe.whitelist()
def mon_planning(week_start=None):
	"""Séances de la semaine pour les cours de l'étudiant (lecture seule)."""
	s = _mon_etudiant()
	debut = getdate(week_start) if week_start else getdate()
	debut = debut - timedelta(days=debut.weekday())
	fin = add_days(debut, 6)
	cours = _cours_suivis(s, _annee_courante())
	if not cours:
		return {"debut": str(debut), "fin": str(fin), "seances": []}
	lignes = frappe.get_all(
		"Planning Item",
		filters={"cours": ["in", list(cours)], "date": ["between", [debut, fin]]},
		fields=["name", "cours", "date", "period", "type", "mode", "salle", "batiment", "status"],
		order_by="date asc",
	)
	periodes = {}
	noms_periodes = {l.period for l in lignes if l.period}
	if noms_periodes:
		for p in frappe.get_all("Planning Period", filters={"name": ["in", list(noms_periodes)]},
								fields=["name", "libelle", "heure_de_debut", "heure_de_fin"]):
			periodes[p.name] = p
	from udshed.api.planning_calendar import _batiment_code, _room_code

	cache, salles = {}, {}
	seances = []
	for l in lignes:
		if l.status == "Annulée":
			continue
		if l.cours not in cache:
			tu = frappe.db.get_value("Teaching Unit", l.cours, ["intitule_cours", "course"], as_dict=True) or {}
			cache[l.cours] = tu.get("intitule_cours") or tu.get("course") or l.cours
		p = periodes.get(l.period) or {}
		seances.append({
			"jour": str(getdate(l.date)),
			"debut": _hhmm(p.get("heure_de_debut")),
			"fin": _hhmm(p.get("heure_de_fin")),
			"cours": cache[l.cours],
			"type": l.type or "",
			"mode": l.mode or "",
			"salle": _room_code(l.salle, salles) or (l.salle or ""),
			"batiment": _batiment_code(l.batiment, salles) or (l.batiment or ""),
		})
	seances.sort(key=lambda x: (x["jour"], x["debut"]))
	return {"debut": str(debut), "fin": str(fin), "seances": seances}


@frappe.whitelist()
def mes_resultats(academic_year=None):
	"""Résultats publiés de l'étudiant (UE, note, statut, décision)."""
	s = _mon_etudiant()
	filtres = {"student": s.name}
	if academic_year:
		filtres["academic_year"] = academic_year
	lignes = frappe.get_all(
		"Resultat Academique", filters=filtres,
		fields=["ue_name", "teaching_unit", "academic_year", "semestre", "note_finale", "grade", "mention",
				"statut", "est_rattrapage", "decision_annee"],
		order_by="academic_year desc, semestre asc, ue_name asc",
	)
	return {"resultats": lignes}
