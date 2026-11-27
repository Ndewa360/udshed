"""Tableaux de bord de direction : faculté (doyen / vice-doyen) et établissement (DAA).

tableau_faculte(academic_year, faculte)  : indicateurs par filière d'une faculté dirigée
tableau_etablissement(academic_year)      : indicateurs par faculté (Directeur des Affaires Académiques)
Mêmes indicateurs : effectifs, avancement des cours, saisie des notes, réussite, dérogations,
actes à signer, délibérations.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from udshed.utils import perimetre

ROLES_ETABLISSEMENT = {"System Manager", "Directeur des Affaires Académiques"}


def _annee(academic_year=None):
	from udshed.utils.session_academique import annee_session

	return academic_year or annee_session()


def _pct(a, b):
	return round(100.0 * a / b, 1) if b else 0.0


def _indicateurs(academic_year, filieres, donnees=None):
	"""Indicateurs d'un ensemble de filières."""
	from udshed.insight import moteur

	res = frappe._dict(filieres=len(filieres))
	if not filieres:
		return res
	res.inscrits = frappe.db.count("Inscription Academique", {"annee_academique": academic_year, "filiere": ["in", filieres]})
	res.reinscrits = frappe.db.count("Academic Reregistration", {"academic_year": academic_year, "filiere": ["in", filieres],
																	 "statut": "Validée"})
	# Avancement des cours (moteur d'Insight : séances échues / volume prévu).
	d = donnees or moteur.Donnees(academic_year)
	classes = {cl for cl in d.classes if cl[0] in filieres}
	calc = moteur.calculer(d, classes_retenues=classes)
	cours = [n for n, s in calc["stats"].items()]
	agr = moteur.agreger(d, calc, cours, list(classes))
	res.cours = agr["cours"]
	res.avancement = agr["completion"]
	res.cours_en_retard = agr["en_retard"]
	# Saisie des notes : évaluations confirmées par les enseignants.
	evaluations = len(cours) * 2  # contrôle continu + examen de session normale
	confirmees = frappe.db.count("Confirmation Saisie", {"academic_year": academic_year, "filiere": ["in", filieres],
														  "type_evaluation": ["in", ["Contrôle continu", "Examen de session normale"]]})
	res.saisies_confirmees = confirmees
	res.saisies_attendues = evaluations
	res.taux_saisie = _pct(confirmees, evaluations)
	# Réussite : résultats publiés des étudiants de ces filières.
	etudiants = frappe.get_all("Student", filters={"filiere": ["in", filieres]}, pluck="name")
	if etudiants:
		total = frappe.db.count("Resultat Academique", {"academic_year": academic_year, "student": ["in", etudiants]})
		valides = frappe.db.count("Resultat Academique", {"academic_year": academic_year, "student": ["in", etudiants],
														   "statut": "Validé"})
		res.taux_reussite = _pct(valides, total)
		res.actes_a_signer = frappe.db.count("Acte Academique", {"statut": "Demandé", "student": ["in", etudiants]})
	else:
		res.taux_reussite = 0.0
		res.actes_a_signer = 0
	res.derogations = frappe.db.count("Derogation Saisie", {"statut": "Demandée", "filiere": ["in", filieres]})
	res.deliberations = frappe.db.count("Deliberation Jury", {"academic_year": academic_year, "filiere": ["in", filieres]})
	return res


def _periodes(academic_year, faculte=None):
	filtres = {"academic_year": academic_year}
	lignes = frappe.get_all("Periode Saisie Notes", filters=filtres,
							fields=["name", "semestre", "type_evaluation", "faculte", "ouverture", "fermeture"],
							order_by="semestre asc, ouverture asc")
	maintenant = now_datetime()
	res = []
	for p in lignes:
		if faculte and p.faculte and p.faculte != faculte:
			continue
		etat = "à venir" if maintenant < p.ouverture else ("fermée" if maintenant > p.fermeture else "ouverte")
		res.append({**p, "etat": etat, "portee": p.faculte or _("Établissement")})
	return res


@frappe.whitelist()
def tableau_faculte(academic_year=None, faculte=None):
	from udshed.insight import moteur

	annee = _annee(academic_year)
	roles = set(frappe.get_roles())
	dirigees = perimetre.facultes_dirigees()
	toutes = frappe.session.user == "Administrator" or bool(roles & ROLES_ETABLISSEMENT)
	if not dirigees and not toutes:
		frappe.throw(perimetre.message_vide(), frappe.PermissionError)
	faculte = faculte or (dirigees[0] if dirigees else None)
	if not faculte:
		frappe.throw(_("Choisissez une faculté."))
	if not toutes and faculte not in dirigees:
		frappe.throw(_("Cette faculté n'est pas la vôtre."), frappe.PermissionError)
	d = moteur.Donnees(annee)
	filieres = frappe.get_all("Field of study", filters={"faculte": faculte}, fields=["name", "name_of_field"],
							  order_by="name_of_field asc")
	lignes = [{"filiere": f.name, "libelle": f.name_of_field or f.name, **_indicateurs(annee, [f.name], d)} for f in filieres]
	derogations = frappe.get_all("Derogation Saisie", filters={"statut": "Demandée", "faculte": faculte},
								 fields=["name", "intitule", "type_evaluation", "enseignant", "demande_le", "motif"],
								 order_by="demande_le asc")
	for x in derogations:
		x.enseignant_nom = frappe.db.get_value("Teacher", x.enseignant, "full_name") or x.enseignant
	etudiants = frappe.get_all("Student", filters={"filiere": ["in", [f.name for f in filieres] or ["∅"]]}, pluck="name")
	actes = frappe.get_all("Acte Academique", filters={"statut": "Demandé", "student": ["in", etudiants or ["∅"]]},
						   fields=["name", "type_acte", "student", "creation"], order_by="creation asc", limit=20)
	return {
		"annee": annee, "faculte": faculte,
		"faculte_libelle": frappe.db.get_value("Faculty", faculte, "faculty_name") or faculte,
		"facultes": [{"value": f, "label": frappe.db.get_value("Faculty", f, "faculty_name") or f}
					 for f in (dirigees if not toutes else frappe.get_all("Faculty", pluck="name"))],
		"total": _indicateurs(annee, [f.name for f in filieres], d), "lignes": lignes,
		"derogations": derogations, "actes": actes, "periodes": _periodes(annee, faculte),
	}


@frappe.whitelist()
def tableau_etablissement(academic_year=None):
	from udshed.insight import moteur

	roles = set(frappe.get_roles())
	if frappe.session.user != "Administrator" and not roles & ROLES_ETABLISSEMENT:
		frappe.throw(_("Réservé au Directeur des Affaires Académiques."), frappe.PermissionError)
	annee = _annee(academic_year)
	d = moteur.Donnees(annee)
	lignes = []
	toutes_filieres = []
	for fac in frappe.get_all("Faculty", fields=["name", "faculty_name", "doyen", "vice_doyen"], order_by="faculty_name asc"):
		filieres = frappe.get_all("Field of study", filters={"faculte": fac.name}, pluck="name")
		toutes_filieres += filieres
		lignes.append({"faculte": fac.name, "libelle": fac.faculty_name or fac.name,
					   "doyen": frappe.utils.get_fullname(fac.doyen) if fac.doyen else "",
					   **_indicateurs(annee, filieres, d)})
	return {"annee": annee, "total": _indicateurs(annee, toutes_filieres, d), "lignes": lignes,
			"periodes": _periodes(annee)}
