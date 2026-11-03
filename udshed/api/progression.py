"""Progression académique automatique après publication officielle des résultats.

Déclenchement : `udshed.api.saisie_notes.publier_session` (publication d'une
Session Examen). Rien n'est calculé à la saisie, au calcul des moyennes ou à
la validation des notes.

Le résultat est stocké dans « Progression Academique » (une ligne par
étudiant et par année des résultats, nom = PROG-{student}-{annee}) :
- une publication répétée met à jour la même ligne, sans jamais créer une
  seconde progression ;
- une ligne corrigée par la scolarité ou déjà utilisée par une réinscription
  n'est plus recalculée.

Les règles académiques ne sont PAS redéfinies ici : elles viennent de
`udshed.api.reregistration` (règle de crédits, redoublement) et de
`udshed.utils.niveaux` (niveau suivant, cycles).
"""

import frappe
from frappe.utils import now_datetime

from udshed.api.reregistration import (
	STAFF_ROLES,
	_autorise_etudiant,
	_decision_annee_etudiant,
	_derniere_classe_etudiant,
	_determiner_reinscription,
	_resolve_level_name,
	_teaching_units_niveau_year,
	get_next_academic_year,
)
from udshed.utils.niveaux import (
	NIVEAUX_PAR_CYCLE,
	_level_rank,
	cycle_niveau,
	lignes_filiere,
	prochain_niveau,
)

DOCTYPE = "Progression Academique"

TYPE_NORMALE = "Examen de session normal"
TYPE_RATTRAPAGE = "Examen de rattrapage"
SESSION_PUBLIEE = "Publiée"

STATUT_ATTENTE = "En attente de publication"
STATUT_ADMIS = "Admis au niveau supérieur"
STATUT_REDOUBLEMENT = "Redoublement"
STATUT_FIN = "Fin de parcours"
STATUT_ADMINISTRATIF = "Décision administrative requise"

STATUTS_AUTORISANT_REINSCRIPTION = (STATUT_ADMIS, STATUT_REDOUBLEMENT)
CHAMPS_DECISION = ("statut", "filiere_cible", "niveau_cible")
ROLES_CORRECTION = {"System Manager", "Coordonateur", "Agent de scolarité", "Registration Manager"}

# Champs recalculés : la ligne n'est réécrite que si l'un d'eux change.
CHAMPS_CALCULES = (
	"statut", "motif", "decision_notes", "credits_valides", "credits_total", "credits_dette",
	"filiere_cible", "niveau_cible", "type_inscription_source", "inscription_source",
	"filiere_source", "niveau_source",
)


# ---------------------------------------------------------------------- #
#  Lecture des données existantes
# ---------------------------------------------------------------------- #

def niveau_existe(filiere, niveau_label):
	"""True si le niveau (libellé) est configuré dans la filière."""
	if not filiere or not niveau_label or not frappe.db.exists("Field of study", filiere):
		return False
	return any(r.level == niveau_label for r in lignes_filiere(filiere))


def inscription_source(student, academic_year):
	"""Inscription de l'étudiant pour l'année des résultats.

	Réinscription (Academic Reregistration) si elle existe, sinon inscription
	initiale (Inscription Academique).

	Returns:
		dict | None: doctype, name, filiere, niveau
	"""
	rer = frappe.get_all(
		"Academic Reregistration",
		filters={"student": student, "academic_year": academic_year},
		fields=["name", "filiere", "niveau"],
		order_by="creation desc",
		limit_page_length=1,
	)
	if rer:
		return {"doctype": "Academic Reregistration", **rer[0]}

	ia = frappe.get_all(
		"Inscription Academique",
		filters={"matricule": student, "annee_academique": academic_year},
		fields=["name", "filiere", "classe"],
		order_by="creation desc",
		limit_page_length=1,
	)
	if ia:
		return {"doctype": "Inscription Academique", "name": ia[0].name,
				"filiere": ia[0].filiere, "niveau": ia[0].classe}
	return None


def resultats_annee_publies(filiere, niveau_label, academic_year):
	"""Les résultats de la classe (filière + niveau) sont-ils officiellement publiés ?

	Exigé : pour chaque semestre de la grille d'enseignement de la classe, au
	moins une session normale programmée et toutes publiées ; toute session
	de rattrapage de l'année concernant la classe publiée. Une session sans
	« classes concernées » vaut pour toutes les classes.

	Returns:
		tuple(bool, str): (publiés, motif si non publiés)
	"""
	niveau_name = _resolve_level_name(filiere, niveau_label)
	if not niveau_name:
		return False, "le niveau « {0} » n'existe pas dans la filière {1}".format(niveau_label, filiere)

	tus = _teaching_units_niveau_year(filiere, niveau_name, academic_year)
	if not tus:
		return False, "aucune UE dans la grille d'enseignement {0} {1} ({2})".format(
			filiere, niveau_label, academic_year
		)
	semestres = sorted({
		s for s in frappe.get_all("Teaching Unit", filters={"name": ["in", tus]}, pluck="semestre") if s
	})

	sessions = frappe.get_all(
		"Session Examen",
		filters={"academic_year": academic_year, "type_dexamen": ["in", [TYPE_NORMALE, TYPE_RATTRAPAGE]]},
		fields=["name", "type_dexamen", "semestre", "statut"],
	)
	classes = {}
	if sessions:
		for row in frappe.get_all(
			"Session Examen Field of study Level",
			filters={"parent": ["in", [s.name for s in sessions]], "parenttype": "Session Examen"},
			fields=["parent", "filiere", "niveau"],
		):
			classes.setdefault(row.parent, set()).add((row.filiere, str(row.niveau)))
	cle = (filiere, str(niveau_name))
	concernees = [s for s in sessions if not classes.get(s.name) or cle in classes[s.name]]

	manquants = []
	for semestre in semestres:
		normales = [s for s in concernees if s.type_dexamen == TYPE_NORMALE and s.semestre == semestre]
		if not normales:
			manquants.append("aucune session normale pour le {0}".format(semestre))
		elif any(s.statut != SESSION_PUBLIEE for s in normales):
			manquants.append("session normale du {0} non publiée".format(semestre))
	if any(s.type_dexamen == TYPE_RATTRAPAGE and s.statut != SESSION_PUBLIEE for s in concernees):
		manquants.append("session de rattrapage non publiée")

	return (not manquants), "; ".join(manquants)


# ---------------------------------------------------------------------- #
#  Évaluation (règles existantes)
# ---------------------------------------------------------------------- #

def _admission_vers_champs(admission):
	admission = admission or {}
	return {
		"credits_valides": admission.get("credits_validated") or 0,
		"credits_total": admission.get("total_credits") or 0,
		"credits_dette": admission.get("debt_credits") or 0,
	}


def evaluer_progression(student_doc, filiere, niveau_source, annee_source):
	"""Calcule la progression sans rien écrire.

	Returns:
		dict: statut, motif, decision_notes, filiere_cible, niveau_cible, crédits
	"""
	student = student_doc.name
	annee_cible = get_next_academic_year(annee_source)
	res = {"statut": STATUT_ADMINISTRATIF, "motif": "", "decision_notes": "",
		   "filiere_cible": None, "niveau_cible": None,
		   "credits_valides": 0, "credits_total": 0, "credits_dette": 0}

	publies, motif = resultats_annee_publies(filiere, niveau_source, annee_source)
	if not publies:
		res.update(statut=STATUT_ATTENTE, motif="Résultats {0} non publiés officiellement : {1}.".format(
			annee_source, motif))
		return res
	if not frappe.db.exists("Resultat Academique", {"student": student, "academic_year": annee_source}):
		res.update(statut=STATUT_ATTENTE, motif="Aucun résultat publié pour l'étudiant en {0}.".format(annee_source))
		return res

	if filiere != student_doc.filiere:
		res["motif"] = "La filière de l'inscription ({0}) diffère de celle du dossier étudiant ({1}).".format(
			filiere, student_doc.filiere)
		return res
	dernier = _derniere_classe_etudiant(student)
	if dernier != niveau_source:
		res["motif"] = "Le dernier niveau enregistré ({0}) diffère du niveau de l'inscription {1} ({2}).".format(
			dernier or "—", annee_source, niveau_source)
		return res

	decision = _decision_annee_etudiant(student, annee_source)
	res["decision_notes"] = decision
	suivant = prochain_niveau(filiere, niveau_source)

	if suivant:
		info = _determiner_reinscription(student_doc, annee_cible)
		admission = info.get("admission") or {}
		res.update(_admission_vers_champs(admission))
		res["motif"] = admission.get("motif") or ""
		if not info.get("niveau"):
			res["motif"] = "Niveau de l'année suivante indéterminé. " + res["motif"]
			return res
		if info.get("redoublement"):
			if decision != "Ajourné":
				res["motif"] = "Redoublement calculé par la règle de crédits mais décision annuelle « {0} ». {1}".format(
					decision, res["motif"])
				return res
			res.update(statut=STATUT_REDOUBLEMENT, filiere_cible=filiere, niveau_cible=info["niveau"])
			return res
		if admission.get("admissible"):
			res.update(statut=STATUT_ADMIS, filiere_cible=filiere, niveau_cible=info["niveau"])
			return res
		return res

	# Pas de niveau suivant dans la filière.
	cycle = cycle_niveau(niveau_source)
	rang = _level_rank(niveau_source)
	attendu = next((l for l in NIVEAUX_PAR_CYCLE.get(cycle, []) if _level_rank(l) == rang + 1), None)
	if attendu:
		res["motif"] = ("Le niveau « {0} » n'est pas configuré dans la filière {1} : "
						"la progression ne peut pas être déterminée.").format(attendu, filiere)
		return res

	if decision == "Ajourné":
		res.update(statut=STATUT_REDOUBLEMENT, filiere_cible=filiere, niveau_cible=niveau_source,
				   motif="Dernier niveau du cycle non validé : reprise du niveau {0}.".format(niveau_source))
		return res
	if decision != "Admis":
		res["motif"] = "Décision annuelle indisponible ({0}).".format(decision or "—")
		return res

	masters = [r.level for r in lignes_filiere(filiere) if cycle_niveau(r.level) == "Master"]
	if cycle == "Licence" and masters:
		res["motif"] = ("Fin de Licence validée : l'admission en {0} relève de la décision du jury."
						).format(" / ".join(masters))
		return res
	res.update(statut=STATUT_FIN,
			   motif="Dernier niveau de la formation validé ({0}) : aucun niveau supérieur dans la filière {1}.".format(
				   niveau_source, filiere))
	return res


# ---------------------------------------------------------------------- #
#  Écriture
# ---------------------------------------------------------------------- #

def calculer_progression(student, annee_source, session_publication=None):
	"""Crée ou met à jour la progression d'un étudiant pour `annee_source`.

	Idempotent : une ligne déjà utilisée par une réinscription ou corrigée par
	la scolarité n'est pas modifiée ; une ligne inchangée n'est pas réécrite.

	Returns:
		Document | None: la progression (None si l'étudiant n'était pas inscrit
		cette année-là ou est déjà réinscrit pour l'année suivante)
	"""
	source = inscription_source(student, annee_source)
	if not source:
		return None

	annee_cible = get_next_academic_year(annee_source)
	name = frappe.db.get_value(DOCTYPE, {"student": student, "annee_source": annee_source}, "name")
	doc = frappe.get_doc(DOCTYPE, name) if name else None
	if doc and (doc.reinscription or doc.corrigee):
		return doc
	if not doc and frappe.db.exists("Academic Reregistration", {"student": student, "academic_year": annee_cible}):
		return None

	student_doc = frappe.get_doc("Student", student)
	valeurs = evaluer_progression(student_doc, source["filiere"], source["niveau"], annee_source)
	valeurs.update(
		type_inscription_source=source["doctype"],
		inscription_source=source["name"],
		filiere_source=source["filiere"],
		niveau_source=source["niveau"],
	)

	if doc and not any((doc.get(f) or None) != (valeurs.get(f) or None) for f in CHAMPS_CALCULES):
		return doc

	if not doc:
		doc = frappe.new_doc(DOCTYPE)
		doc.student = student
		doc.annee_source = annee_source
	doc.update(valeurs)
	if session_publication:
		doc.session_publication = session_publication
	doc.date_calcul = now_datetime()
	doc.flags.calcul_automatique = True
	doc.save(ignore_permissions=True)
	return doc


def progression_apres_publication(session_doc):
	"""Calcule la progression des étudiants dont les notes viennent d'être publiées.

	Appelée par `publier_session`, après le calcul des résultats. Chaque
	étudiant est traité dans un savepoint : un échec n'empêche ni la
	publication ni le traitement des autres étudiants.

	Returns:
		dict: compteurs par statut et liste des échecs
	"""
	students = frappe.db.sql_list(
		"""SELECT DISTINCT student FROM `tabSession Examen Note`
		WHERE session_examen = %s AND statut = 'Publié'""",
		session_doc.name,
	)
	bilan = {"par_statut": {}, "echecs": []}
	for student in students:
		frappe.db.savepoint("udshed_progression")
		try:
			doc = calculer_progression(student, session_doc.academic_year, session_doc.name)
		except Exception as exc:
			frappe.db.rollback(save_point="udshed_progression")
			frappe.log_error(frappe.get_traceback(), "udshed: progression post-publication")
			bilan["echecs"].append({"student": student, "message": str(exc)})
			continue
		if doc:
			bilan["par_statut"][doc.statut] = bilan["par_statut"].get(doc.statut, 0) + 1
	return bilan


@frappe.whitelist(methods=["POST"])
def recalculer_progressions(academic_year):
	"""Relance le calcul pour une année de résultats (scolarité).

	Sert aux résultats publiés avant la mise en place du calcul automatique.
	Les mêmes conditions s'appliquent : sans publication officielle, la
	progression reste « En attente de publication ».
	"""
	frappe.only_for(list(ROLES_CORRECTION))
	if not frappe.db.exists("Academic Year", academic_year):
		frappe.throw("Année académique invalide.")

	students = set(frappe.get_all(
		"Academic Reregistration", filters={"academic_year": academic_year}, pluck="student"
	)) | set(frappe.get_all(
		"Inscription Academique", filters={"annee_academique": academic_year}, pluck="matricule"
	))
	bilan = {"par_statut": {}, "echecs": []}
	for student in sorted(s for s in students if s and frappe.db.exists("Student", s)):
		frappe.db.savepoint("udshed_progression")
		try:
			doc = calculer_progression(student, academic_year)
		except Exception as exc:
			frappe.db.rollback(save_point="udshed_progression")
			frappe.log_error(frappe.get_traceback(), "udshed: recalcul progression")
			bilan["echecs"].append({"student": student, "message": str(exc)})
			continue
		if doc:
			bilan["par_statut"][doc.statut] = bilan["par_statut"].get(doc.statut, 0) + 1
	return bilan


# ---------------------------------------------------------------------- #
#  Lecture pour la réinscription
# ---------------------------------------------------------------------- #

def progression_pour_annee(student, annee_cible):
	name = frappe.db.get_value(DOCTYPE, {"student": student, "annee_cible": annee_cible}, "name")
	return frappe.get_doc(DOCTYPE, name) if name else None


def message_blocage(progression, annee_cible, annee_source=None):
	"""Message expliquant pourquoi la réinscription est impossible (None sinon)."""
	if not progression or progression.statut == STATUT_ATTENTE:
		return ("Vos résultats de l'année {0} n'ont pas encore été publiés officiellement : "
				"la réinscription pour {1} est impossible pour le moment.").format(
			annee_source or (progression.annee_source if progression else "précédente"), annee_cible)
	if progression.statut == STATUT_FIN:
		return ("Vous avez validé le dernier niveau de votre formation ({0}) : aucune réinscription "
				"n'est prévue. Rapprochez-vous de la scolarité pour la suite de votre parcours.").format(
			progression.niveau_source)
	if progression.statut == STATUT_ADMINISTRATIF:
		return ("Votre dossier nécessite une décision de la scolarité avant la réinscription : {0}").format(
			progression.motif or "situation à examiner.")
	if progression.statut not in STATUTS_AUTORISANT_REINSCRIPTION:
		return "Réinscription impossible : statut de progression « {0} ».".format(progression.statut)
	return None


def exiger_progression(student, annee_cible, annee_source=None):
	"""Progression autorisant la réinscription, sinon erreur explicite."""
	progression = progression_pour_annee(student, annee_cible)
	message = message_blocage(progression, annee_cible, annee_source)
	if message:
		frappe.throw(message, title="Réinscription impossible")
	return progression


@frappe.whitelist()
def get_progression_reinscription(student, academic_year):
	"""Niveau et filière imposés pour une réinscription (formulaire Desk / page étudiant)."""
	if not _autorise_etudiant(student):
		frappe.throw("Vous n'êtes pas autorisé à consulter cet étudiant.", frappe.PermissionError)
	progression = progression_pour_annee(student, academic_year)
	return {
		"name": progression.name if progression else None,
		"statut": progression.statut if progression else None,
		"filiere": progression.filiere_cible if progression else None,
		"niveau": progression.niveau_cible if progression else None,
		"motif": progression.motif if progression else None,
		"message": message_blocage(progression, academic_year),
	}


def est_personnel():
	return frappe.session.user == "Administrator" or bool(set(frappe.get_roles()) & STAFF_ROLES)
