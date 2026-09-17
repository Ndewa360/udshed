import json
import os

import frappe
from frappe.utils.pdf import get_pdf
from frappe.query_builder import DocType

from udshed.utils.niveaux import (
	cycle_niveau,
	niveau_precedent,
	prochain_niveau,
)

STAFF_ROLES = {"System Manager", "Coordonateur", "Agent de scolarité", "Comptable"}


def _autorise_etudiant(student):
	"""L'appelant doit être l'étudiant lui-même ou un membre du personnel autorisé."""
	if not student:
		return False
	if frappe.session.user == "Administrator":
		return True
	if set(frappe.get_roles()) & STAFF_ROLES:
		return True
	return frappe.db.get_value("Student", student, "utilisateur") == frappe.session.user


def _decision_annee_etudiant(student, academic_year):
	"""Décision d'admission d'un étudiant pour une année donnée.

	Réutilise UNIQUEMENT les données et les règles du module de gestion de notes :
	- décision déjà stockée : Resultat Academique.decision_annee (Admis / Ajourné) ;
	- sinon calcul via le moteur du module notes (calculer_resultat_annee), qui
	  applique les seuils de validation de grade_calculation (Licence/BTS 50 %,
	  Master 60 %) et la meilleure note normale/rattrapage.

	Returns:
		str: "Admis", "Ajourné" ou "En attente".
	"""
	if not student or not academic_year:
		return "En attente"

	stocks = frappe.get_all(
		"Resultat Academique",
		filters={"student": student, "academic_year": academic_year},
		fields=["decision_annee"],
	)
	for row in stocks:
		if row.decision_annee in ("Admis", "Ajourné"):
			return row.decision_annee

	try:
		from udshed.api.resultat_academique import calculer_resultat_annee
		decision = calculer_resultat_annee(student, academic_year).get("decision")
		return decision if decision in ("Admis", "Ajourné") else "En attente"
	except Exception:
		frappe.log_error(
			f"Impossible de calculer la décision de {student} pour {academic_year}",
			frappe.get_traceback(),
		)
		return "En attente"


@frappe.whitelist()
def get_niveau_precedent(filiere, niveau):
	"""Libellé du niveau précédent selon la règle du parcours (utils.niveaux)."""
	return niveau_precedent(filiere, niveau) or ""


@frappe.whitelist()
def get_notes_decision(student, academic_year):
	"""Décision du module de notes pour un étudiant et une année (affichage)."""
	if not _autorise_etudiant(student):
		frappe.throw("Vous n'êtes pas autorisé à consulter cet étudiant.")
	return {"decision": _decision_annee_etudiant(student, academic_year)}


@frappe.whitelist()
def get_open_sessions():
	"""Retourne toutes les sessions de réinscription ouvertes"""
	return frappe.get_all(
		"Session Reinscription",
		filters={"statut": "Ouverte"},
		fields=["name", "academic_year", "date_ouverture", "date_cloture", "note_minimale"]
	)


@frappe.whitelist()
def get_student_by_matricule(matricule=None):
	"""Retrouver l'étudiant : par matricule, ou par l'utilisateur courant
	(le matricule fourni peut être un email / nom d'utilisateur)."""
	if not matricule:
		matricule = frappe.session.user

	student_name = None
	if frappe.db.exists("Student", matricule):
		student_name = matricule
	else:
		# À défaut, chercher via le champ « utilisateur » lié au compte Frappe
		student_name = frappe.db.sql(
			"SELECT name FROM `tabStudent` WHERE utilisateur=%s LIMIT 1",
			matricule,
			pluck=True,
		)
		student_name = student_name[0] if student_name else None

	if not student_name:
		frappe.throw(f"Aucun étudiant trouvé avec le matricule {matricule}")

	if not _autorise_etudiant(student_name):
		frappe.throw("Vous n'êtes pas autorisé à consulter cet étudiant.")

	student = frappe.get_doc("Student", student_name)

	# Récupérer la dernière Inscription Academique pour les données complémentaires
	inscription = frappe.get_all(
		"Inscription Academique",
		filters={"matricule": student.name},
		fields=["name", "classe", "dossier_origine", "dernier_etablissement", "diplome_entree",
				"matricule_diplome", "nom_prenom_pere", "pere_telephone",
				"pere_profession", "pere_ville", "nom_prenom_mere", "telephone_mere",
				"profession_mere", "mere_ville", "nom_prenom_sponsor", "telephone_sponsor",
				"profession_sponsor", "sponsor_ville", "activites_sportives",
				"activites_associatives", "activites_culturelles",
				"connaissances_informatiques"],
		order_by="creation desc",
		limit_page_length=1,
	)
	insc = inscription[0] if inscription else {}

	return {
		"name": student.name,
		"matricule": student.matricule,
		"nom": student.nom,
		"prenom": student.prenom,
		"nom_complet": f"{student.nom or ''} {student.prenom or ''}".strip(),
		"filiere": student.filiere,
		"niveau_actuel": student.niveau_actuel,
		"cycle": student.cycle,
		"email": student.email,
		"utilisateur": student.utilisateur,
		# Données depuis Student
		"date_naissance": student.birth_date,
		"lieu_naissance": student.birth_place,
		"telephone": student.phone,
		# Données depuis Inscription Academique
		"dernier_classe": insc.get("classe"),
		"dossier_origine": insc.get("dossier_origine"),
		"dernier_etablissement": insc.get("dernier_etablissement"),
		"diplome_entree": insc.get("diplome_entree"),
		"matricule_diplome": insc.get("matricule_diplome"),
		"nom_prenom_pere": insc.get("nom_prenom_pere"),
		"pere_telephone": insc.get("pere_telephone"),
		"pere_profession": insc.get("pere_profession"),
		"pere_ville": insc.get("pere_ville"),
		"nom_prenom_mere": insc.get("nom_prenom_mere"),
		"telephone_mere": insc.get("telephone_mere"),
		"profession_mere": insc.get("profession_mere"),
		"mere_ville": insc.get("mere_ville"),
		"nom_prenom_sponsor": insc.get("nom_prenom_sponsor"),
		"telephone_sponsor": insc.get("telephone_sponsor"),
		"profession_sponsor": insc.get("profession_sponsor"),
		"sponsor_ville": insc.get("sponsor_ville"),
		"activites_sportives": insc.get("activites_sportives"),
		"activites_associatives": insc.get("activites_associatives"),
		"activites_culturelles": insc.get("activites_culturelles"),
		"connaissances_informatiques": insc.get("connaissances_informatiques"),
	}


@frappe.whitelist()
def get_ordered_levels(filiere):
	"""Retourne les niveaux d'une filière triés par ordre croissant"""
	doc = frappe.get_doc("Field of study", filiere)
	levels = sorted(doc.field_of_study_level, key=lambda x: x.order or 0)
	return [
		{
			"name": l.name,
			"level": l.level,
			"order": l.order
		}
		for l in levels
	]


@frappe.whitelist()
def get_previous_level_courses(filiere, niveau_label, academic_year):
	"""
	Retourne les matières du niveau précédent
	pour pré-remplir la table des résultats précédents.

	Args:
		filiere: name/ID de la filière (Field of study)
		niveau_label: label du niveau actuel (ex: "Licence 1"), valeur du Select
		academic_year: name/ID de l'année académique
	"""
	filiere_doc = frappe.get_doc("Field of study", filiere)

	# Trouver l'order du niveau actuel par son label (valeur Select)
	niveau_actuel_order = None
	niveau_precedent_name = None

	for row in filiere_doc.field_of_study_level:
		if row.level == niveau_label:
			niveau_actuel_order = row.order
			break

	if not niveau_actuel_order:
		return []

	# Trouver le niveau précédent (order - 1)
	for row in filiere_doc.field_of_study_level:
		if row.order == (niveau_actuel_order - 1):
			niveau_precedent_name = row.name
			break

	if not niveau_precedent_name:
		return []

	# Récupérer les matières du niveau précédent
	TeachingUnit = DocType("Teaching Unit")
	CourseLevel = DocType("Course Field of study level item")

	matieres = (
		frappe.qb.from_(TeachingUnit)
		.join(CourseLevel).on(CourseLevel.parent == TeachingUnit.name)
		.select(
			TeachingUnit.name,
			TeachingUnit.intitule_cours,
			TeachingUnit.semestre
		)
		.where(
			(TeachingUnit.academic_year == academic_year) &
			(CourseLevel.filiere == filiere) &
			(CourseLevel.niveau == niveau_precedent_name)
		)
	).run(as_dict=True)

	return matieres


def _annee_resultats_etudiant(student, niveau_label=None):
	"""Année académique dont les résultats conditionnent la réinscription.

	- dernière année où l'étudiant a été inscrit au niveau passé (Academic
	  Reregistration) ;
	- à défaut, dernière année ayant des résultats publiés (Resultat Academique).
	"""
	if student and niveau_label:
		ok = frappe.db.exists("Academic Reregistration", {
			"student": student,
			"niveau": niveau_label,
		})
		if ok:
			row = frappe.get_all(
				"Academic Reregistration",
				filters={"student": student, "niveau": niveau_label},
				fields=["academic_year"],
				order_by="creation desc",
				limit_page_length=1,
			)
			if row and row[0].academic_year:
				return row[0].academic_year

	rows = frappe.get_all(
		"Resultat Academique",
		filters={"student": student},
		fields=["academic_year"],
		order_by="creation desc",
		limit_page_length=1,
	)
	return rows[0].academic_year if rows else None


@frappe.whitelist()
def get_student_notes(student, filiere, niveau_precedent_label):
	"""Résultats du niveau précédent d'un étudiant.

	Source unique = module de gestion de notes (Resultat Academique) :
	statut Validé / Non Validé par UE, note_finale, semestre et décision
	annuelle (Admis / Ajourné / En attente) calculée par calculer_resultat_annee.

	Args:
		student: name/ID de l'étudiant
		filiere: name/ID de la filière
		niveau_precedent_label: label du niveau précédent (ex: "Licence 1")
	"""
	if not _autorise_etudiant(student):
		frappe.throw("Vous n'êtes pas autorisé à consulter cet étudiant.")

	filiere_doc = frappe.get_doc("Field of study", filiere)
	niveau_precedent_name = None
	for row in filiere_doc.field_of_study_level:
		if row.level == niveau_precedent_label:
			niveau_precedent_name = row.name
			break

	if not niveau_precedent_name:
		return []

	annee_resultats = _annee_resultats_etudiant(student, niveau_precedent_label)
	if not annee_resultats:
		return []

	tu_names = _teaching_units_niveau(filiere, niveau_precedent_name)
	if not tu_names:
		return []

	return frappe.get_all(
		"Resultat Academique",
		filters={
			"student": student,
			"academic_year": annee_resultats,
			"teaching_unit": ["in", tu_names],
		},
		fields=["teaching_unit", "ue_name", "semestre", "note_finale", "statut", "decision_annee"],
		order_by="semestre asc, ue_name asc",
	)


def _teaching_units_niveau(filiere, niveau_name):
	"""Names des Teaching Units d'un niveau d'une filière."""
	TeachingUnit = DocType("Teaching Unit")
	CourseLevel = DocType("Course Field of study level item")

	rows = (
		frappe.qb.from_(TeachingUnit)
		.join(CourseLevel).on(CourseLevel.parent == TeachingUnit.name)
		.select(TeachingUnit.name)
		.where(
			(CourseLevel.filiere == filiere) &
			(CourseLevel.niveau == niveau_name)
		)
	).run(pluck="name")
	return rows or []


# ---------------------------------------------------------------------- #
#  Crédits & admission basée sur les crédits
# ---------------------------------------------------------------------- #

def _resolve_level_name(filiere, niveau_label):
	"""Résout un label de niveau (ex: 'Licence 1') en name/ID du Field of study Level."""
	if not filiere or not niveau_label:
		return None
	doc = frappe.get_doc("Field of study", filiere)
	for row in doc.field_of_study_level:
		if row.level == niveau_label:
			return row.name
	return None


def _credit_from_grid(filiere, niveau_name, teaching_unit):
	"""Crédits d'une UE depuis la grille pédagogique (course_poid).

	Fallback : Teaching Unit.credits si pas de ligne course_poid.
	"""
	row = frappe.db.get_value(
		"Course Field of study level item",
		{"parent": teaching_unit, "filiere": filiere, "niveau": niveau_name},
		"course_poid",
	)
	if row:
		return int(row)
	return int(frappe.db.get_value("Teaching Unit", teaching_unit, "credits") or 0)


def _teaching_units_niveau_year(filiere, niveau_name, academic_year):
	"""Teaching Units d'un niveau/filière pour une année académique donnée."""
	TeachingUnit = DocType("Teaching Unit")
	CourseLevel = DocType("Course Field of study level item")

	rows = (
		frappe.qb.from_(TeachingUnit)
		.join(CourseLevel).on(CourseLevel.parent == TeachingUnit.name)
		.select(TeachingUnit.name)
		.where(
			(TeachingUnit.academic_year == academic_year)
			& (CourseLevel.filiere == filiere)
			& (CourseLevel.niveau == niveau_name)
		)
	).run(pluck="name")
	return rows or []


def _credits_total_niveau(filiere, niveau_name, academic_year):
	"""Total des crédits d'un niveau pour une filière/année (somme course_poid)."""
	tu_names = _teaching_units_niveau_year(filiere, niveau_name, academic_year)
	if not tu_names:
		return 0
	credits = 0
	for tu in tu_names:
		credits += _credit_from_grid(filiere, niveau_name, tu)
	return credits


def _credits_validated(student, filiere, niveau_name, academic_year):
	"""Crédits validés par l'étudiant pour un niveau donné.

	Returns:
		tuple (credits_validated, list validated_teaching_units)
	"""
	tu_names = _teaching_units_niveau_year(filiere, niveau_name, academic_year)
	if not tu_names:
		return 0, []

	results = frappe.get_all(
		"Resultat Academique",
		filters={
			"student": student,
			"academic_year": academic_year,
			"teaching_unit": ["in", tu_names],
		},
		fields=["teaching_unit", "statut"],
	)

	validated_tu = {r.teaching_unit for r in results if r.statut == "Validé"}
	credits_validated = 0
	for tu in tu_names:
		if tu in validated_tu:
			credits_validated += _credit_from_grid(filiere, niveau_name, tu)

	return credits_validated, list(validated_tu)


def _dettes_with_credits(student, filiere, niveau_name, academic_year):
	"""UE non validées (dettes) avec leurs crédits et semestre."""
	tu_names = _teaching_units_niveau_year(filiere, niveau_name, academic_year)
	if not tu_names:
		return []

	results = frappe.get_all(
		"Resultat Academique",
		filters={
			"student": student,
			"academic_year": academic_year,
			"teaching_unit": ["in", tu_names],
		},
		fields=["teaching_unit", "ue_name", "semestre", "note_finale", "statut"],
	)

	dettes = []
	for r in results:
		if r.statut != "Validé":
			credits = _credit_from_grid(filiere, niveau_name, r.teaching_unit)
			intitule = r.ue_name or frappe.db.get_value(
				"Teaching Unit", r.teaching_unit, "intitule_cours"
			) or r.teaching_unit
			dettes.append({
				"teaching_unit": r.teaching_unit,
				"intitule": intitule,
				"semestre": r.semestre or "",
				"note": r.note_finale or 0,
				"credits": credits,
			})

	return dettes


def _get_all_previous_levels(filiere, niveau_cible_label):
	"""Tous les niveaux antérieurs au niveau cible (par ordre croissant)."""
	if not filiere or not niveau_cible_label:
		return []
	doc = frappe.get_doc("Field of study", filiere)
	levels = sorted(doc.field_of_study_level, key=lambda x: x.order or 0)
	target_order = None
	for l in levels:
		if l.level == niveau_cible_label:
			target_order = l.order
			break
	if target_order is None:
		return []
	return [l.level for l in levels if (l.order or 0) < target_order]


def _get_all_licence_levels(filiere):
	"""Tous les niveaux de cycle Licence d'une filière (par ordre croissant)."""
	if not filiere:
		return []
	doc = frappe.get_doc("Field of study", filiere)
	levels = sorted(doc.field_of_study_level, key=lambda x: x.order or 0)
	return [l.level for l in levels if (l.cycle or "").startswith("Licence")]


def _admission_decision(student, filiere, niveau_precedent_label, niveau_cible_label, academic_year):
	"""Décision d'admission basée sur les crédits (règle de réinscription).

	Règles :
	- L2/BTS2 : au moins 50 % des crédits du niveau précédent validés + dettes ≤ 30
	- L3 : validation complète de L1 + L2 (zéro dette)
	- Master : validation complète de toute la Licence (L1+L2+L3)

	Returns:
		dict: admissible, decision, credits_validated, total_credits,
		      debt_credits, motif, details (par niveau si L3/Master)
	"""
	from udshed.utils.niveaux import cycle_niveau

	niveau_precedent_name = _resolve_level_name(filiere, niveau_precedent_label)
	if not niveau_precedent_name:
		return {
			"admissible": False, "decision": "En attente",
			"motif": "Niveau précédent introuvable",
			"credits_validated": 0, "total_credits": 0, "debt_credits": 0,
			"details": [],
		}

	# Crédits du niveau précédent direct (année des résultats de ce niveau)
	annee_precedent = _annee_resultats_etudiant(student, niveau_precedent_label) or academic_year
	total_credits = _credits_total_niveau(filiere, niveau_precedent_name, annee_precedent)
	credits_validated, _ = _credits_validated(student, filiere, niveau_precedent_name, annee_precedent)
	debt_credits = total_credits - credits_validated

	cycle = cycle_niveau(niveau_cible_label) if niveau_cible_label else ""
	details = []

	# --- Cas spécial : Licence 3 → exige L1 + L2 complets ---
	if niveau_cible_label and "Licence 3" in str(niveau_cible_label):
		previous_levels = _get_all_previous_levels(filiere, niveau_cible_label)
		for prev_label in previous_levels:
			prev_name = _resolve_level_name(filiere, prev_label)
			if not prev_name:
				details.append({"niveau": prev_label, "total": 0, "valides": 0, "ok": False})
				continue
			annee_prev = _annee_resultats_etudiant(student, prev_label) or academic_year
			tot = _credits_total_niveau(filiere, prev_name, annee_prev)
			val, _ = _credits_validated(student, filiere, prev_name, annee_prev)
			details.append({"niveau": prev_label, "total": tot, "valides": val, "ok": val >= tot})
			if val < tot:
				return {
					"admissible": False, "decision": "Ajourné",
					"motif": "Admission en Licence 3 exige la validation complète de {0} ({1}/{2} crédits)".format(
						prev_label, val, tot
					),
					"credits_validated": credits_validated, "total_credits": total_credits,
					"debt_credits": debt_credits, "details": details,
				}

	# --- Cas spécial : Master → exige Licence complète ---
	if cycle == "Master":
		licence_levels = _get_all_licence_levels(filiere)
		for prev_label in licence_levels:
			prev_name = _resolve_level_name(filiere, prev_label)
			if not prev_name:
				details.append({"niveau": prev_label, "total": 0, "valides": 0, "ok": False})
				continue
			annee_prev = _annee_resultats_etudiant(student, prev_label) or academic_year
			tot = _credits_total_niveau(filiere, prev_name, annee_prev)
			val, _ = _credits_validated(student, filiere, prev_name, annee_prev)
			details.append({"niveau": prev_label, "total": tot, "valides": val, "ok": val >= tot})
			if val < tot:
				return {
					"admissible": False, "decision": "Ajourné",
					"motif": "Admission en Master exige la validation complète de {0} ({1}/{2} crédits)".format(
						prev_label, val, tot
					),
					"credits_validated": credits_validated, "total_credits": total_credits,
					"debt_credits": debt_credits, "details": details,
				}

	# --- Règle standard : 50 % + dettes ≤ 30 ---
	if total_credits == 0:
		return {
			"admissible": False, "decision": "En attente",
			"motif": "Aucun crédit trouvé pour le niveau précédent",
			"credits_validated": 0, "total_credits": 0, "debt_credits": 0, "details": details,
		}

	pct = round((credits_validated / total_credits) * 100)
	admissible = pct >= 50 and debt_credits <= 30

	if admissible:
		decision = "Admis"
		motif = "{0}/{1} crédits validés ({2}%) — dettes: {3} crédits".format(
			credits_validated, total_credits, pct, debt_credits
		)
	else:
		decision = "Ajourné"
		if pct < 50:
			motif = "Crédits insuffisants: {0}/{1} ({2}%) — minimum 50% requis".format(
				credits_validated, total_credits, pct
			)
		else:
			motif = "Dettes trop élevées: {0} crédits — maximum 30 autorisés".format(debt_credits)

	return {
		"admissible": admissible,
		"decision": decision,
		"credits_validated": credits_validated,
		"total_credits": total_credits,
		"debt_credits": debt_credits,
		"motif": motif,
		"details": details,
	}


def _determiner_reinscription(student, academic_year, niveau=None):
	"""Détermine le niveau de réinscription et l'admission (règle de crédits).

	Arguments:
		student: Document Student
		academic_year: année de la session de réinscription
		niveau: niveau explicite (entrée en Master, sinon None)

	Returns:
		dict: niveau, niveau_precedent, admission, master, master_levels, redoublement
	"""
	matricule = student.name
	filiere = student.filiere
	dernier_classe = _derniere_classe_etudiant(matricule)
	suivant = prochain_niveau(filiere, dernier_classe) if dernier_classe else None
	master = bool(dernier_classe and not suivant)

	master_levels = [
		r.level for r in _niveaux_filiere(filiere)
		if cycle_niveau(r.level) == "Master"
	] if master else []

	redoublement = False

	if niveau:
		# Niveau explicite (entrée en Master / cas particulier)
		niveau_final = niveau
		niveau_prec = niveau_precedent(filiere, niveau_final) or dernier_classe
	elif not dernier_classe:
		return {
			"niveau": None, "niveau_precedent": None, "admission": None,
			"master": False, "master_levels": [], "redoublement": False,
		}
	elif master:
		# Fin de cycle : admission en Master (Licence complète) sinon redoublement
		master_cible = master_levels[0] if master_levels else dernier_classe
		admission_probe = _admission_decision(
			matricule, filiere, dernier_classe, master_cible, academic_year
		)
		niveau_prec = dernier_classe
		if master_levels and admission_probe.get("admissible"):
			niveau_final = None  # l'étudiant précise son niveau Master
		else:
			niveau_final = dernier_classe
			redoublement = True
	else:
		cible = suivant or dernier_classe
		niveau_prec = niveau_precedent(filiere, cible) or dernier_classe
		niveau_final = cible

	# Admission calculée sur le niveau cible réel
	if niveau_final:
		admission = _admission_decision(
			matricule, filiere, niveau_prec, niveau_final, academic_year
		)
	else:
		admission = admission_probe if master else None

	# Non admis et progression possible → redoublement du dernier niveau suivi
	if (not niveau and not redoublement and niveau_final and admission
			and not admission.get("admissible") and dernier_classe
			and niveau_final != dernier_classe):
		niveau_final = dernier_classe
		niveau_prec = niveau_precedent(filiere, dernier_classe) or niveau_prec
		redoublement = True

	if redoublement:
		# Redoublement : dettes et décision se réfèrent au dernier niveau réellement
		# suivi (l'étudiant a échoué ce niveau, il le reprend intégralement).
		niveau_prec = dernier_classe
		annee_dernier = _annee_resultats_etudiant(matricule, dernier_classe) or academic_year
		admission = _admission_decision(
			matricule, filiere, dernier_classe, niveau_final, annee_dernier
		)
		if admission:
			admission = {
				**admission,
				"decision": _decision_annee_etudiant(matricule, annee_dernier),
			}

	return {
		"niveau": niveau_final,
		"niveau_precedent": niveau_prec,
		"admission": admission,
		"master": bool(master and niveau_final is None),
		"master_levels": master_levels,
		"redoublement": redoublement,
	}


@frappe.whitelist()
def get_reregistration_summary(student, academic_year):
	"""
	Retourne un résumé de la réinscription d'un étudiant
	pour une année académique donnée
	"""
	if not _autorise_etudiant(student):
		frappe.throw("Vous n'êtes pas autorisé à consulter cet étudiant.")

	reregistration = frappe.get_all(
		"Academic Reregistration",
		filters={
			"student": student,
			"academic_year": academic_year
		},
		fields=["name", "statut", "niveau", "filiere", "semestre"]
	)

	if not reregistration:
		return None

	doc = frappe.get_doc("Academic Reregistration", reregistration[0].name)

	# Compter les matières par statut
	inscrits = len([c for c in doc.cours_inscrits if c.statut == "Inscrit"])
	dispenses = len([c for c in doc.cours_inscrits if c.statut == "Dispensé"])
	reportes = len([c for c in doc.cours_inscrits if c.statut == "Reporté"])

	return {
		"name": doc.name,
		"statut": doc.statut,
		"niveau": doc.niveau,
		"filiere": doc.filiere,
		"semestre": doc.semestre,
		"total_matieres": len(doc.cours_inscrits),
		"inscrits": inscrits,
		"dispenses": dispenses,
		"reportes": reportes,
		"dettes": reportes
	}


@frappe.whitelist()
def get_student_registrations(student):
	"""
	Retourne toutes les réinscriptions d'un étudiant
	pour l'affichage dans le tableau de bord
	"""
	if not _autorise_etudiant(student):
		frappe.throw("Vous n'êtes pas autorisé à consulter cet étudiant.")

	reregistrations = frappe.get_all(
		"Academic Reregistration",
		filters={"student": student},
		fields=[
			"name", "academic_year", "reinscription_session",
			"filiere", "niveau", "semestre", "statut", "creation"
		],
		order_by="creation desc"
	)

	return reregistrations





@frappe.whitelist()
def get_cycle_map():
	"""Retourne la carte cycle -> niveaux (tous les niveaux de chaque cycle).

	Source unique de la liste des niveaux possibles, utilises par la page de
	gestion des niveaux pour afficher, sous chaque cycle, chaque niveau du cycle
	(ajoute ou non a la filiere).
	"""
	from udshed.utils.niveaux import niveaux_par_cycle

	return niveaux_par_cycle()


@frappe.whitelist()
def get_all_levels(faculty=None, filiere=None):
	"""Retourne tous les niveaux groupés par filière, triés par ordre.
	Inclut les facultés sans filière pour l'arborescence."""
	filters = {}
	if filiere:
		filters["name"] = filiere
	elif faculty:
		filters["faculte"] = faculty

	fields_of_study = frappe.get_all("Field of study", filters=filters, fields=["name", "name_of_field", "faculte"])
	result = []
	for fos in fields_of_study:
		doc = frappe.get_doc("Field of study", fos.name)
		levels = sorted(doc.field_of_study_level, key=lambda x: x.order or 0)
		result.append({
			"filiere_name": fos.name,
			"filiere_label": fos.name_of_field,
			"faculte": fos.faculte,
			"levels": [
				{
					"name": l.name,
					"level": l.level,
					"cycle": l.cycle,
					"order": l.order,
					"coordonateur": l.coordonateur,
					"calendrier": l.calendrier,
					"gestionnaire_de_planning": l.gestionnaire_de_planning,
				}
				for l in levels
			]
		})

	if not filiere:
		all_faculties = frappe.get_all("Faculty", fields=["name", "faculty_name"])
		faculties_with_fos = set(r.get("faculte") for r in result)
		for fac in all_faculties:
			if fac.name not in faculties_with_fos:
				result.append({
					"filiere_name": None,
					"filiere_label": None,
					"faculte": fac.name,
					"levels": [],
				})

	from udshed.utils.niveaux import niveaux_par_cycle
	return {
		"filieres": result,
		"cycles": niveaux_par_cycle() if not filiere else None,
	}


@frappe.whitelist()
def add_level(filiere, level, cycle=None, coordonateur=None, calendrier="Defaut", gestionnaire_de_planning=None):
	"""Ajoute un niveau à une filière en l'insérant au bon endroit par cycle."""
	doc = frappe.get_doc("Field of study", filiere)
	if any(r.level == level for r in doc.field_of_study_level):
		frappe.throw(f"Le niveau {level} existe déjà dans {filiere}")

	new_cycle = cycle or _cycle_from_level(level)

	doc.append("field_of_study_level", {
		"level": level,
		"cycle": new_cycle,
		"order": 0,
		"coordonateur": coordonateur,
		"calendrier": calendrier or "Defaut",
		"gestionnaire_de_planning": gestionnaire_de_planning,
	})
	doc.save(ignore_permissions=True)
	return {"status": True, "message": f"Niveau {level} ajouté à {filiere}"}


def _cycle_from_level(level_label):
	"""Déduit le cycle depuis le libellé du niveau."""
	if not level_label:
		return None
	for cycle in ("BTS", "Licence", "Master", "Doctorat"):
		if level_label.startswith(cycle):
			return cycle
	return None




@frappe.whitelist()
def reorder_levels(filiere, level_names):
	"""Réordonne les niveaux d'une filière selon le glisser-déposer.

	`level_names` contient les noms des lignes dans l'ordre où elles ont été
	déposées sur la page (les niveaux d'un même cycle). On réordonne UNIQUEMENT
	ces niveaux dans l'ordre déposé, tout en les laissant à leur place relative
	dans la filière : les autres niveaux ne bougent pas. L'ordre ainsi choisi
	est conservé (pas de retour automatique à l'ordre académique).
	"""
	if not level_names:
		return {"status": True, "message": "Aucun niveau à réordonner"}

	doc = frappe.get_doc("Field of study", filiere)
	rows = list(doc.field_of_study_level)
	if not rows:
		return {"status": True, "message": "Aucun niveau à réordonner"}

	# Les names peuvent arriver sous forme de chaînes depuis le front.
	by_str = {str(r.name): r for r in rows}
	if not all(str(n) in by_str for n in level_names):
		return {"status": False, "message": "Niveaux invalides pour le réordonnancement"}

	keys = [str(n) for n in level_names]
	dragged_set = set(keys)
	dragged = [by_str[k] for k in keys]

	ordered = []
	for r in rows:
		if str(r.name) in dragged_set:
			# Premier niveau du groupe déplacé : on insère tout le groupe, dans le
			# nouvel ordre, à cet emplacement.
			if not any(str(x.name) in dragged_set for x in ordered):
				ordered.extend(dragged)
		else:
			ordered.append(r)

	doc.set("field_of_study_level", ordered)
	doc.save(ignore_permissions=True)
	return {"status": True, "message": "Ordre des niveaux mis à jour"}


@frappe.whitelist()
def update_level(filiere, level_row_name, cycle=None, coordonateur=None, calendrier=None, gestionnaire_de_planning=None):
	"""Met à jour les champs d'un niveau existant dans une filière."""
	doc = frappe.get_doc("Field of study", filiere)
	row = None
	for r in doc.field_of_study_level:
		if str(r.name) == str(level_row_name):
			row = r
			break

	if not row:
		frappe.throw("Niveau introuvable")

	if cycle is not None:
		row.cycle = cycle
	if coordonateur is not None:
		row.coordonateur = coordonateur
	if calendrier is not None:
		row.calendrier = calendrier
	if gestionnaire_de_planning is not None:
		row.gestionnaire_de_planning = gestionnaire_de_planning

	doc.save(ignore_permissions=True)
	return {"status": True, "message": f"Niveau {row.level} mis à jour dans {filiere}"}


@frappe.whitelist()
def delete_level(filiere, level_name):
	"""Supprime un niveau d'une filière via SQL direct."""
	level = frappe.db.get_value(
		"Field of study Level",
		{"parent": filiere, "level": level_name},
		"name",
	)
	if not level:
		frappe.throw("Niveau introuvable")
	frappe.delete_doc("Field of study Level", level, ignore_permissions=True)
	frappe.db.commit()
	return {"status": True, "message": f"Niveau {level_name} supprimé de {filiere}"}


@frappe.whitelist()
def get_reregistrations_by_session(reinscription_session):
	"""
	Retourne toutes les réinscriptions d'une session
	avec leurs statuts — pour le tableau de bord du coordonateur
	"""
	reregistrations = frappe.get_all(
		"Academic Reregistration",
		filters={"reinscription_session": reinscription_session},
		fields=[
			"name", "student", "academic_year",
			"filiere", "niveau", "semestre", "statut"
		],
		order_by="creation desc"
	)

	result = []
	student_names = list(set(r.get("student") for r in reregistrations))
	student_map = {}
	for s_name in student_names:
		s = frappe.get_doc("Student", s_name)
		student_map[s_name] = {
			"nom_etudiant": f"{s.nom} {s.prenom}",
			"matricule": s.name,
			"email": s.email
		}

	for r in reregistrations:
		result.append({
			**r,
			**student_map.get(r.get("student"), {})
		})

	return result


@frappe.whitelist()
def get_reregistration_report(reinscription_session=None, filiere=None, statut=None):
	"""Rapport des réinscriptions pour la page « Rapport de réinscription ».

	Retourne les compteurs (total, par statut/filière/niveau) et le détail des
	lignes pour l'export CSV. Filtres optionnels : session, filière, statut.
	"""
	filters = {}
	if reinscription_session:
		filters["reinscription_session"] = reinscription_session
	if filiere:
		filters["filiere"] = filiere
	if statut:
		filters["statut"] = statut

	reregistrations = frappe.get_all(
		"Academic Reregistration",
		filters=filters,
		fields=[
			"name", "student", "academic_year", "filiere", "niveau",
			"semestre", "statut",
		],
		order_by="creation desc",
	)

	student_names = {r.get("student") for r in reregistrations if r.get("student")}
	student_map = {}
	for s_name in student_names:
		s = frappe.get_doc("Student", s_name)
		student_map[s_name] = {
			"matricule": s.name,
			"nom_etudiant": f"{s.nom or ''} {s.prenom or ''}".strip(),
		}

	rows = []
	for r in reregistrations:
		s = student_map.get(r.get("student")) or {}
		filiere_label = frappe.db.get_value("Field of study", r.filiere, "name_of_field") or r.filiere
		rows.append({
			"matricule": s.get("matricule") or r.get("student") or "",
			"nom_etudiant": s.get("nom_etudiant") or "",
			"filiere_label": filiere_label,
			"niveau": r.get("niveau") or "",
			"semestre": r.get("semestre") or "",
			"academic_year": r.get("academic_year") or "",
			"statut": r.get("statut") or "Validée",
		})

	par_statut = {}
	par_filiere = {}
	par_niveau = {}
	for r in rows:
		par_statut[r["statut"]] = par_statut.get(r["statut"], 0) + 1
		par_filiere[r["filiere_label"]] = par_filiere.get(r["filiere_label"], 0) + 1
		par_niveau[r["niveau"] or "—"] = par_niveau.get(r["niveau"] or "—", 0) + 1

	return {
		"total": len(rows),
		"par_statut": par_statut,
		"par_filiere": par_filiere,
		"par_niveau": par_niveau,
		"rows": rows,
	}


@frappe.whitelist()
def telecharger_fiche_reinscription(reregistration_name):
	"""Génère la fiche de réinscription en PDF.

	L'étudiant peut télécharger sa fiche autant de fois qu'il le souhaite.
	Le personnel (Coordonateur / Agent de scolarité / Comptable / System Manager)
	peut aussi la télécharger.
	"""
	doc = frappe.get_doc("Academic Reregistration", reregistration_name)
	student = frappe.get_doc("Student", doc.student)

	roles = frappe.get_roles()
	is_student = student.utilisateur == frappe.session.user
	is_staff = bool(set(roles) & {"System Manager", "Coordonateur", "Agent de scolarité", "Comptable"})
	if not (is_student or is_staff):
		frappe.throw("Vous n'avez pas accès à cette fiche de réinscription.")

	if doc.statut != "Validée":
		frappe.throw("La fiche de réinscription n'est disponible qu'après validation.")

	filiere_label = frappe.db.get_value("Field of study", doc.filiere, "name_of_field") or doc.filiere
	school_name = frappe.get_single("Udshed Setting").school_name or ""
	coordonnateur = _get_coordonnateur(doc.filiere, doc.niveau) or ""

	template_path = os.path.join(frappe.get_app_path("udshed"), "templates", "reinscription_fiche.html")
	with open(template_path, encoding="utf-8") as f:
		html = frappe.render_template(f.read(), {
			"school_name": school_name,
			"student": {
				"matricule": student.name,
				"nom": student.nom or "",
				"prenom": student.prenom or "",
				"email": student.email,
				"date_naissance": student.birth_date,
				"lieu_naissance": student.birth_place,
				"telephone": student.phone,
			},
			"doc": {
				"name": doc.name,
				"reinscription_session": doc.reinscription_session,
				"academic_year": doc.academic_year,
				"filiere_label": filiere_label,
				"niveau": doc.niveau,
				"semestre": doc.semestre,
				"statut": doc.statut,
				# Études antérieures
				"dernier_etablissement": doc.dernier_etablissement,
				"diplome_entree": doc.diplome_entree,
				"matricule_diplome": doc.matricule_diplome,
				# Famille
				"nom_prenom_pere": doc.nom_prenom_pere,
				"pere_telephone": doc.pere_telephone,
				"pere_profession": doc.pere_profession,
				"pere_ville": doc.pere_ville,
				"nom_prenom_mere": doc.nom_prenom_mere,
				"telephone_mere": doc.telephone_mere,
				"profession_mere": doc.profession_mere,
				"mere_ville": doc.mere_ville,
				"nom_prenom_sponsor": doc.nom_prenom_sponsor,
				"telephone_sponsor": doc.telephone_sponsor,
				"profession_sponsor": doc.profession_sponsor,
				"sponsor_ville": doc.sponsor_ville,
				# Activités
				"activites_sportives": doc.activites_sportives,
				"activites_associatives": doc.activites_associatives,
				"activites_culturelles": doc.activites_culturelles,
				"connaissances_informatiques": doc.connaissances_informatiques,
			},
			"coordonnateur": coordonnateur,
			"cours_inscrits": [
				{"intitule": m.intitule, "teaching_unit": m.teaching_unit, "semestre": m.semestre, "statut": m.statut}
				for m in doc.cours_inscrits
			],
			"resultats_precedents": [
				{
					"intitule": r.intitule, "teaching_unit": r.teaching_unit, "semestre": r.semestre,
					"note": r.note, "valide": r.valide, "est_dette": r.est_dette
				}
				for r in doc.resultats_precedents
			]
		})

	try:
		pdf = get_pdf(html)
	except Exception:
		frappe.log_error("reregistration telecharger_fiche_reinscription get_pdf")
		frappe.throw("Erreur lors de la génération du PDF. Veuillez réessayer.")

	frappe.local.response.filename = f"Fiche_Reinscription_{doc.name}.pdf"
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "pdf"


def _get_coordonnateur(filiere, niveau_label):
	"""Nom du coordonnateur d'un niveau (label) dans une filière."""
	if not filiere or not niveau_label:
		return ""
	try:
		filiere_doc = frappe.get_doc("Field of study", filiere)
		for row in filiere_doc.field_of_study_level:
			if row.level == niveau_label:
				return row.coordonateur or ""
	except Exception:
		return ""
	return ""


@frappe.whitelist()
def submit_reinscription(matricule, reinscription_session, semestre, niveau=None, cours=None):
	"""Crée une réinscription (Academic Reregistration) pour l'étudiant connecté.

	L'appelant doit être soit l'étudiant lui-même, soit un membre du personnel
	autorisé (Coordonateur / Agent de scolarité / Comptable / System Manager).

	RÈGLE MÉTIER : Un étudiant ne peut se réinscrire que pour l'année académique
	SUIVANTE sa dernière inscription (ex: inscrit/réinscrit en 2025-2026 -> réinscription 2026-2027).
	Il ne peut jamais se réinscrire pour une année antérieure à la sienne.

	Args:
		matricule: name/ID de l'étudiant (Student)
		reinscription_session: name/ID de la Session Reinscription
		semestre: "Semestre 1", "Semestre 2" ou "Les deux"

	Returns:
		dict: {"status": bool, "message": str, "name": str|None}
	"""
	if not matricule or not frappe.db.exists("Student", matricule):
		frappe.throw("Étudiant introuvable.")

	if not frappe.db.exists("Session Reinscription", reinscription_session):
		frappe.throw("Session de réinscription invalide.")

	# Vérification d'accès : l'étudiant connecté ou un membre du personnel
	student = frappe.get_doc("Student", matricule)
	if not _autorise_etudiant(matricule):
		frappe.throw("Vous n'êtes pas autorisé à soumettre cette réinscription.")

	# RÈGLE : Vérifier que la session correspond à l'année SUIVANTE la dernière inscription
	annee_session = frappe.db.get_value("Session Reinscription", reinscription_session, "academic_year")
	annee_base = get_student_derniere_annee_academique(matricule)

	if not annee_base:
		frappe.throw("Aucune inscription initiale trouvée pour cet étudiant.")

	annee_attendue = get_next_academic_year(annee_base)

	if annee_session != annee_attendue:
		frappe.throw(
			"Réinscription refusée : vous ne pouvez vous réinscrire que pour l'année académique {0} "
			"(suivante votre dernière inscription en {1}). "
			"La session sélectionnée correspond à l'année {2}."
			.format(annee_attendue, annee_base, annee_session)
		)

	# Empêcher les doublons (réinscription déjà validée cette année)
	exists = frappe.db.get_all(
		"Academic Reregistration",
		filters={"student": matricule, "academic_year": annee_session},
		fields=["name"],
		limit_page_length=1,
	)
	if exists:
		return {"status": False, "message": "Vous êtes déjà réinscrit(e) pour cette année académique."}

	# Niveau de réinscription calculé automatiquement via la règle d'admission
	# par crédits (progression / redoublement / fin de cycle-Master).
	info = _determiner_reinscription(student, annee_session, niveau=niveau)
	niveau_final = info["niveau"]

	if info.get("master") and not niveau:
		# Fin de cycle admis : l'étudiant doit préciser son niveau Master
		frappe.throw(
			"Fin de cycle : précisez votre niveau de Master. "
			"La demande reste soumise à l'accord du coordinateur."
		)

	if not niveau_final:
		frappe.throw(
			"Impossible de déterminer automatiquement le niveau de réinscription "
			"(fin de cycle). Précisez le niveau."
		)

	# Récupérer les données de la dernière Inscription Academique
	inscription = frappe.get_all(
		"Inscription Academique",
		filters={"matricule": matricule},
		fields=["name", "dossier_origine", "dernier_etablissement", "diplome_entree",
				"matricule_diplome", "nom_prenom_pere", "pere_telephone",
				"pere_profession", "pere_ville", "nom_prenom_mere", "telephone_mere",
				"profession_mere", "mere_ville", "nom_prenom_sponsor", "telephone_sponsor",
				"profession_sponsor", "sponsor_ville", "activites_sportives",
				"activites_associatives", "activites_culturelles",
				"connaissances_informatiques"],
		order_by="creation desc",
		limit_page_length=1,
	)
	insc = inscription[0] if inscription else {}

	# Construire le document ; le validate() du doctype calcule automatiquement
	# le niveau précédent, la décision, les résultats et les cours inscrits.
	doc = frappe.get_doc({
		"doctype": "Academic Reregistration",
		"student": matricule,
		"reinscription_session": reinscription_session,
		"academic_year": annee_session,
		"filiere": student.filiere,
		"niveau": niveau_final,
		"semestre": semestre,
		# Identité (depuis Student)
		"nom_prenom": f"{student.nom or ''} {student.prenom or ''}".strip(),
		"email": student.email,
		"date_naissance": student.birth_date,
		"lieu_naissance": student.birth_place,
		"telephone": student.phone,
		# Inscription (depuis Inscription Academique)
		"dossier_origine": insc.get("dossier_origine"),
		"dernier_etablissement": insc.get("dernier_etablissement"),
		"diplome_entree": insc.get("diplome_entree"),
		"matricule_diplome": insc.get("matricule_diplome"),
		# Famille
		"nom_prenom_pere": insc.get("nom_prenom_pere"),
		"pere_telephone": insc.get("pere_telephone"),
		"pere_profession": insc.get("pere_profession"),
		"pere_ville": insc.get("pere_ville"),
		"nom_prenom_mere": insc.get("nom_prenom_mere"),
		"telephone_mere": insc.get("telephone_mere"),
		"profession_mere": insc.get("profession_mere"),
		"mere_ville": insc.get("mere_ville"),
		"nom_prenom_sponsor": insc.get("nom_prenom_sponsor"),
		"telephone_sponsor": insc.get("telephone_sponsor"),
		"profession_sponsor": insc.get("profession_sponsor"),
		"sponsor_ville": insc.get("sponsor_ville"),
		# Activités
		"activites_sportives": insc.get("activites_sportives"),
		"activites_associatives": insc.get("activites_associatives"),
		"activites_culturelles": insc.get("activites_culturelles"),
		"connaissances_informatiques": insc.get("connaissances_informatiques"),
		# Matières cochées par l'étudiant (les dettes verrouillées sont reprises
		# automatiquement ; le validate() recalcule la grille en conservant ces choix).
		"cours_inscrits": [
			{"teaching_unit": c["teaching_unit"], "inscrire": 1}
			for c in (cours or []) if c.get("inscrire") and c.get("teaching_unit")
		] if cours else [],
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"status": True, "message": "Réinscription soumise avec succès.", "name": doc.name}


def get_student_premiere_inscription(student):
	"""Année de la première inscription de l'étudiant (Inscription Academique)."""
	return frappe.db.get_value(
		"Inscription Academique",
		{"matricule": student},
		"annee_academique",
		order_by="creation asc"
	)


def _derniere_classe_etudiant(student):
	"""Dernier niveau effectivement suivi par l'étudiant.

	- dernière réinscription validée (Academic Reregistration.niveau) ;
	- à défaut, la classe de sa dernière inscription initiale
	  (Inscription Academique.classe).
	"""
	rer = frappe.get_all(
		"Academic Reregistration",
		filters={"student": student},
		fields=["niveau"],
		order_by="creation desc",
		limit_page_length=1,
	)
	if rer and rer[0].get("niveau"):
		return rer[0].niveau

	row = frappe.get_all(
		"Inscription Academique",
		filters={"matricule": student},
		fields=["classe"],
		order_by="creation desc",
		limit_page_length=1,
	)
	return row[0].get("classe") if row else None


def _niveaux_filiere(filiere):
	"""Lignes de niveaux d'une filière, triées par ordre."""
	doc = frappe.get_doc("Field of study", filiere)
	return sorted(doc.field_of_study_level, key=lambda r: r.order or 0)


def _niveau_reinscription_auto(student, decision, dernier_classe, filiere):
	"""Niveau de réinscription calculé automatiquement.

	- Décision "Admis"  -> classe supérieure (prochain_niveau) ;
	  en fin de cycle (ex. Licence), prochain_niveau est None :
	  l'entrée au niveau supérieur (Master) relève du jury.
	- Autre décision     -> redoublement (dernière classe suivie).
	"""
	if decision == "Admis" and dernier_classe:
		return prochain_niveau(filiere, dernier_classe)
	return dernier_classe


@frappe.whitelist()
def get_reregistration_preview(matricule, reinscription_session, semestre=None):
	"""Évalue la réinscription d'un étudiant AVANT enregistrement (dry-run).

	Retourne les informations pré-remplies calculées par le système :
	- academic_year : année académique de la session ;
	- dernier_classe : dernier niveau effectivement suivi ;
	- decision : Admis / Ajourné / En attente (module de notes) ;
	- niveau : niveau de réinscription calculé automatiquement ;
	- niveau_precedent : niveau dont les résultats conditionnent l'accès ;
	- master : True si le prochain niveau n'existe pas (fin de Licence) ;
	- master_levels : niveaux Master présents dans la filière (si master).
	"""
	student = frappe.get_doc("Student", matricule)

	if not _autorise_etudiant(matricule):
		frappe.throw("Vous n'êtes pas autorisé à consulter cet étudiant.")

	session = frappe.db.get_value(
		"Session Reinscription",
		reinscription_session,
		["academic_year", "statut"],
	)
	if not session:
		frappe.throw("Session de réinscription invalide.")
	academic_year, statut = session[0], session[1]
	if statut != "Ouverte":
		frappe.throw("La session de réinscription sélectionnée n'est pas ouverte.")

	info = _determiner_reinscription(student, academic_year)

	return {
		"academic_year": academic_year,
		"filiere": student.filiere,
		"dernier_classe": _derniere_classe_etudiant(matricule),
		"decision": (info["admission"] or {}).get("decision") or "En attente",
		"admission": info["admission"],
		"niveau": info["niveau"],
		"niveau_precedent": info["niveau_precedent"],
		"master": info["master"],
		"master_levels": info["master_levels"],
	}


@frappe.whitelist()
def get_reregistration_grid(matricule, reinscription_session, semestre=None, niveau=None):
	"""Grille de matières dynamique AVANT enregistrement (dry-run).

	Retourne la grille interactive composée de :
	- dettes du niveau précédent (cochées, verrouillées, obligatoires) ;
	- matières du nouveau niveau (décochées, l'étudiant les coche lui-même).

	Chaque ligne porte ses crédits, sa source (dette/niveau_actuel) et
	l'état de la checkbox (verrouille ou non).

	Args:
		matricule: name/ID de l'étudiant (Student)
		reinscription_session: name/ID de la Session Reinscription
		semestre: "Semestre 1", "Semestre 2" ou "Les deux"
		niveau: niveau explicite (cas entrée en Master, sinon None)
	"""
	student = frappe.get_doc("Student", matricule)

	if not _autorise_etudiant(matricule):
		frappe.throw("Vous n'êtes pas autorisé à consulter cet étudiant.")

	session = frappe.db.get_value(
		"Session Reinscription",
		reinscription_session,
		["academic_year", "statut"],
	)
	if not session:
		frappe.throw("Session de réinscription invalide.")
	academic_year, statut = session[0], session[1]
	if statut != "Ouverte":
		frappe.throw("La session de réinscription sélectionnée n'est pas ouverte.")

	info = _determiner_reinscription(student, academic_year, niveau=niveau)
	niveau_final = niveau or info["niveau"]
	niveau_prec_label = info["niveau_precedent"]
	admission = info["admission"]
	redoublement = info.get("redoublement", False)

	if not niveau_final:
		return {"niveau": None, "admission": admission, "resultats_precedents": [],
				"cours_inscrits": [], "stats": {}, "redoublement": False}

	niveau_final_name = _resolve_level_name(student.filiere, niveau_final)

	# --- Résultats de l'année du niveau précédent (avec crédits) ---
	niveau_prec_name = _resolve_level_name(student.filiere, niveau_prec_label) if niveau_prec_label else None
	annee_resultats = _annee_resultats_etudiant(matricule, niveau_prec_label) if niveau_prec_label else None

	resultats = []
	if niveau_prec_name and annee_resultats:
		rows = frappe.get_all(
			"Resultat Academique",
			filters={
				"student": matricule,
				"academic_year": annee_resultats,
			},
			fields=["teaching_unit", "ue_name", "semestre", "note_finale", "statut", "decision_annee"],
			order_by="semestre asc, ue_name asc",
		)
		for r in rows:
			valide = r.statut == "Validé"
			credits = _credit_from_grid(student.filiere, niveau_prec_name, r.teaching_unit)
			intitule = r.ue_name or frappe.db.get_value(
				"Teaching Unit", r.teaching_unit, "intitule_cours"
			) or r.teaching_unit
			resultats.append({
				"teaching_unit": r.teaching_unit,
				"intitule": intitule,
				"semestre": r.semestre or "",
				"note": r.note_finale or 0,
				"valide": 1 if valide else 0,
				"est_dette": 0 if valide else 1,
				"credits": credits,
				"statut": "Validé" if valide else "Non Validé",
			})

	# --- Grille dynamique : dettes (verrouillées) + matières du niveau (à cocher) ---
	cours = []
	limite = 30  # crédits max par semestre

	if niveau_final_name:
		# 1) Dettes du niveau précédent → cochées, verrouillées
		if niveau_prec_name and annee_resultats:
			dettes = _dettes_with_credits(matricule, student.filiere, niveau_prec_name, annee_resultats)
			for d in dettes:
				cours.append({
					"teaching_unit": d["teaching_unit"],
					"intitule": d["intitule"],
					"semestre": d["semestre"],
					"credits": d["credits"],
					"source": "dette",
					"verrouille": 1,
					"inscrire": 1,
					"motif": "Dette du niveau précédent (note: {0}/20)".format(d["note"]),
				})

		# 2) Matières du nouveau niveau → décochées, l'étudiant coche lui-même
		tu_niveau = _teaching_units_niveau_year(student.filiere, niveau_final_name, academic_year)
		dettes_tu = {c["teaching_unit"] for c in cours}  # déjà en dette
		for tu in tu_niveau:
			if tu in dettes_tu:
				continue
			intitule = frappe.db.get_value("Teaching Unit", tu, "intitule_cours") or tu
			semestre_tu = frappe.db.get_value("Teaching Unit", tu, "semestre") or ""
			credits = _credit_from_grid(student.filiere, niveau_final_name, tu)
			cours.append({
				"teaching_unit": tu,
				"intitule": intitule,
				"semestre": semestre_tu,
				"credits": credits,
				"source": "niveau_actuel",
				"verrouille": 1 if redoublement else 0,
				"inscrire": 1 if redoublement else 0,
				"motif": "Matière du niveau {0}{1}".format(
					niveau_final,
					" — redoublement : programme complet à reprendre" if redoublement else " — à cocher"
				),
			})

	# --- Statistiques par semestre (crédits) ---
	credits_s1 = {"dettes": 0, "niveau": 0}
	credits_s2 = {"dettes": 0, "niveau": 0}
	for c in cours:
		sem = c["semestre"]
		credit = c["credits"]
		if sem == "Semestre 1":
			if c["source"] == "dette":
				credits_s1["dettes"] += credit
			else:
				credits_s1["niveau"] += credit
		elif sem == "Semestre 2":
			if c["source"] == "dette":
				credits_s2["dettes"] += credit
			else:
				credits_s2["niveau"] += credit

	return {
		"niveau": niveau_final,
		"niveau_precedent": niveau_prec_label,
		"academic_year": academic_year,
		"admission": admission,
		"redoublement": redoublement,
		"resultats_precedents": resultats,
		"cours_inscrits": cours,
		"stats": {
			"credit_limit_per_semester": limite,
			"credits_s1": {
				"dettes": credits_s1["dettes"],
				"niveau": credits_s1["niveau"],
				"total": credits_s1["dettes"] + credits_s1["niveau"],
				"limite": limite,
			},
			"credits_s2": {
				"dettes": credits_s2["dettes"],
				"niveau": credits_s2["niveau"],
				"total": credits_s2["dettes"] + credits_s2["niveau"],
				"limite": limite,
			},
			"total_credits_niveau": admission.get("total_credits", 0),
			"credits_validated": admission.get("credits_validated", 0),
			"debt_credits": admission.get("debt_credits", 0),
		},
	}


def get_student_derniere_annee_academique(student):
	"""Dernière année académique où l'étudiant a été inscrit.

	- dernière réinscription (Academic Reregistration) ;
	- à défaut, sa première inscription (Inscription Academique).
	"""
	rer = frappe.get_all(
		"Academic Reregistration",
		filters={"student": student},
		fields=["academic_year"],
		order_by="creation desc",
		limit_page_length=1,
	)
	if rer:
		return rer[0].academic_year
	return get_student_premiere_inscription(student)


def get_next_academic_year(current_year):
	"""Calcule l'année académique suivante.
	Ex: '2025-2026' -> '2026-2027'"""
	if not current_year or "-" not in current_year:
		return None
	try:
		start, end = current_year.split("-")
		next_start = str(int(start) + 1)
		next_end = str(int(end) + 1)
		return f"{next_start}-{next_end}"
	except Exception:
		return None
