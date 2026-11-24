"""Règles métier de la grille d'enseignement, partagées par l'import, l'édition
et la duplication de grilles.

Vocabulaire :
  - « cours » = Teaching Unit (un cours d'une année académique), rattaché à une
    ou plusieurs classes (lignes « Course Field of study level item ») ;
  - « classe » = (filière, niveau) où niveau est le name de la ligne
    « Field of study Level ».
"""

import frappe
from frappe import _
from frappe.utils import flt

# Cohérence crédits / volume horaire : 1 crédit ≈ 10 à 15 h de face-à-face.
HEURES_PAR_CREDIT_MIN = 10
HEURES_PAR_CREDIT_MAX = 15
CHAMPS_HEURES = ("nombre_dheure_cm", "nombre_dheure_td", "nombre_dheure_tp", "nombre_dheure_tpe")


def heures_face_a_face(cours):
	"""Volume horaire encadré (CM + TD + TP) ; le TPE (travail personnel) est exclu."""
	return sum(flt(cours.get(f) or 0) for f in ("nombre_dheure_cm", "nombre_dheure_td", "nombre_dheure_tp"))


def coherence_credits(credits, cours):
	"""Avertissement (texte) si le volume horaire sort de 10-15 h par crédit, sinon None.

	Ce n'est jamais bloquant : la règle guide la saisie, l'établissement garde
	la possibilité de déroger (stages, projets…).
	"""
	credits = flt(credits)
	heures = heures_face_a_face(cours)
	if credits <= 0:
		return _("Crédits nuls : vérifiez la saisie.") if heures else None
	mini, maxi = credits * HEURES_PAR_CREDIT_MIN, credits * HEURES_PAR_CREDIT_MAX
	if heures < mini or heures > maxi:
		return _("{0} h de CM+TD+TP pour {1} crédit(s) : la norme est de {2} à {3} h ({4}-{5} h par crédit).").format(
			flt(heures, 1), flt(credits, 1), flt(mini, 0), flt(maxi, 0), HEURES_PAR_CREDIT_MIN, HEURES_PAR_CREDIT_MAX
		)
	return None


def libelle_niveau(niveau):
	return frappe.db.get_value("Field of study Level", niveau, "level") or ""


def classes_du_cours(teaching_unit):
	"""Classes directement rattachées au cours (sans les cours liés)."""
	return {
		(r.filiere, str(r.niveau))
		for r in frappe.get_all(
			"Course Field of study level item",
			filters={"parent": teaching_unit, "parenttype": "Teaching Unit"},
			fields=["filiere", "niveau"],
		)
	}


def dependances_cours_classe(teaching_unit, filiere, niveau):
	"""Données qui lient ce cours à CETTE classe (empêchent de l'en retirer).

	Retourne {libellé: nombre} (vide = retrait sans risque pour la classe).
	"""
	label = libelle_niveau(niveau)
	deps = {}

	def compter(libelle, n):
		if n:
			deps[libelle] = deps.get(libelle, 0) + n

	compter(
		_("notes saisies"),
		frappe.db.count("Session Examen Note", {"teaching_unit": teaching_unit, "filiere": filiere, "niveau": label}),
	)
	compter(
		_("codes d'anonymat"),
		frappe.db.count("Examen Anonymat", {"teaching_unit": teaching_unit, "filiere": filiere, "niveau": label}),
	)
	inscrits = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabReregistration Course Item` i
		INNER JOIN `tabAcademic Reregistration` r ON r.name = i.parent
		WHERE i.teaching_unit = %s AND r.filiere = %s AND r.niveau = %s
		""",
		(teaching_unit, filiere, label),
	)[0][0]
	compter(_("étudiants inscrits au cours"), inscrits)
	# Les séances de planning ne portent pas la classe : elles comptent pour la
	# classe quand le cours n'appartient qu'à elle.
	if classes_du_cours(teaching_unit) <= {(filiere, str(niveau))}:
		compter(_("séances planifiées"), frappe.db.count("Planning Item", {"cours": teaching_unit}))
	return deps


# Toutes les références à un cours (pour sa suppression définitive).
_REFERENCES_COURS = (
	("Planning Item", "cours", "séances planifiées"),
	("Session Examen Note", "teaching_unit", "notes saisies"),
	("Examen Anonymat", "teaching_unit", "codes d'anonymat"),
	("Copie Examen", "teaching_unit", "copies d'examen"),
	("Fiche Report", "teaching_unit", "fiches de report"),
	("Resultat Academique", "teaching_unit", "résultats académiques"),
	("Resultat UE Matiere", "teaching_unit", "résultats d'UE"),
	("Reregistration Course Item", "teaching_unit", "inscriptions aux cours"),
	("Reregistration Previous Result", "teaching_unit", "résultats antérieurs de réinscription"),
	("Note item", "teacher_unit", "lignes de notes"),
	("Note Publication Email Log", "teaching_unit", "notifications de publication"),
)


def dependances_cours(teaching_unit):
	"""Toutes les données qui référencent ce cours, toutes classes confondues."""
	deps = {}
	for doctype, champ, libelle in _REFERENCES_COURS:
		if not frappe.db.table_exists(doctype):
			continue
		n = frappe.db.count(doctype, {champ: teaching_unit})
		if n:
			deps[_(libelle)] = deps.get(_(libelle), 0) + n
	return deps


def decrire_dependances(deps):
	return ", ".join(f"{n} {libelle}" for libelle, n in deps.items())


def retirer_cours_de_classe(teaching_unit, filiere, niveau, forcer=False):
	"""Détache le cours de la classe ; supprime le cours (et son UE) s'il devient
	orphelin et sans aucune référence. Refuse si des données de la classe en
	dépendent (sauf `forcer`, réservé aux appels internes déjà validés).

	Retourne {"retire": bool, "supprime": bool, "ue_supprimee": str|None}.
	"""
	if not forcer:
		deps = dependances_cours_classe(teaching_unit, filiere, niveau)
		if deps:
			frappe.throw(
				_("Impossible de retirer « {0} » de cette classe : {1}.").format(
					frappe.db.get_value("Teaching Unit", teaching_unit, "intitule_cours") or teaching_unit,
					decrire_dependances(deps),
				),
				title=_("Dépendances existantes"),
			)
	doc = frappe.get_doc("Teaching Unit", teaching_unit)
	avant = len(doc.course_levels)
	doc.set(
		"course_levels",
		[r for r in doc.course_levels if not (r.filiere == filiere and str(r.niveau) == str(niveau))],
	)
	retire = len(doc.course_levels) < avant
	if not retire:
		return {"retire": False, "supprime": False, "ue_supprimee": None}
	if doc.course_levels or dependances_cours(teaching_unit):
		doc.save(ignore_permissions=True)
		return {"retire": True, "supprime": False, "ue_supprimee": None}

	ue = doc.unite_de_valeur
	frappe.delete_doc("Teaching Unit", teaching_unit, ignore_permissions=True)
	ue_supprimee = None
	if ue and not frappe.db.count("Teaching Unit", {"unite_de_valeur": ue}) and not (
		frappe.db.table_exists("Resultat UE") and frappe.db.count("Resultat UE", {"teaching_unit_value": ue})
	):
		frappe.delete_doc("Teaching Unit Value", ue, ignore_permissions=True)
		ue_supprimee = ue
	return {"retire": True, "supprime": True, "ue_supprimee": ue_supprimee}
