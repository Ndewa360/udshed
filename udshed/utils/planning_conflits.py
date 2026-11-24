"""Détection des conflits de planning (source unique de vérité).

Utilisée par :
  - le contrôleur « Planning Item » (validate) : aucun chemin d'écriture
    (API, formulaire Desk, import, duplication) ne peut enregistrer deux
    cours sur le même créneau d'une même classe ;
  - la duplication de semaine, qui classe les créneaux libres / occupés.

Un créneau = (date, période horaire). Deux séances sont en conflit sur un
même créneau si elles partagent :
  - une classe (filière + niveau ; l'année académique est implicite : les
    dates sont absolues) ;
  - un enseignant ;
  - une salle.
Deux séances d'un même cours (tronc commun) ou de cours liés manuellement
sont considérées comme une seule séance commune : elles occupent toutes les
classes du groupe.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate


def classes_du_cours(teaching_unit):
	"""Classes (filière, niveau) qui suivent ce cours, cours liés compris."""
	if not teaching_unit:
		return set()
	unites = cours_lies(teaching_unit) | {teaching_unit}
	rows = frappe.get_all(
		"Course Field of study level item",
		filters={"parent": ["in", list(unites)], "parenttype": "Teaching Unit"},
		fields=["filiere", "niveau"],
	)
	return {(r.filiere, str(r.niveau)) for r in rows if r.filiere and r.niveau}


def enseignants_du_cours(teaching_unit):
	if not teaching_unit:
		return set()
	return set(
		frappe.get_all(
			"Course Teacher Item",
			filters={"parent": teaching_unit, "parenttype": "Teaching Unit"},
			pluck="enseignant",
		)
	) - {None, ""}


def cours_lies(teaching_unit):
	"""Cours déclarés « identiques » au cours donné (même groupe de liaison).

	Le champ `groupe_cours_commun` est ajouté par la fonctionnalité de liaison
	manuelle ; s'il est absent (base non migrée), aucun lien n'est retourné.
	"""
	if not teaching_unit or not frappe.get_meta("Teaching Unit").has_field("groupe_cours_commun"):
		return set()
	groupe = frappe.db.get_value("Teaching Unit", teaching_unit, "groupe_cours_commun")
	if not groupe:
		return set()
	return set(
		frappe.get_all(
			"Teaching Unit",
			filters={"groupe_cours_commun": groupe, "name": ["!=", teaching_unit]},
			pluck="name",
		)
	)


def _libelle_classe(filiere, niveau):
	label = frappe.db.get_value("Field of study Level", niveau, "level") or niveau
	return f"{filiere} {label}"


def _intitule(teaching_unit):
	return frappe.db.get_value("Teaching Unit", teaching_unit, "intitule_cours") or teaching_unit


def seances_du_creneau(jour, period, exclure=None):
	"""Séances déjà planifiées à cette date (tout horaire du jour) et période."""
	jour = getdate(jour)
	filters = [
		["date", ">=", jour],
		["date", "<", add_days(jour, 1)],
		["period", "=", period],
	]
	if exclure:
		filters.append(["name", "!=", exclure])
	return frappe.get_all("Planning Item", filters=filters, fields=["name", "cours", "salle"])


def conflits(cours, jour, period, salle=None, exclure=None, classes=None):
	"""Liste des conflits d'une séance projetée (vide = créneau libre).

	Chaque conflit : {type: classe|enseignant|salle, item, cours, message, classes}.
	`classes` permet de restreindre la vérification de classe à un sous-ensemble
	(par défaut : toutes les classes du cours, cours liés compris).
	"""
	mes_classes = classes if classes is not None else classes_du_cours(cours)
	mes_enseignants = enseignants_du_cours(cours)
	mon_groupe = cours_lies(cours) | {cours}
	resultat = []
	for seance in seances_du_creneau(jour, period, exclure):
		autre = seance.cours
		if autre in mon_groupe:
			# Même cours (ou cours lié) déjà planifié sur ce créneau : c'est une
			# séance commune en double, pas une autre matière.
			communes = mes_classes & classes_du_cours(autre)
			resultat.append({
				"type": "classe",
				"item": seance.name,
				"cours": autre,
				"classes": sorted(communes),
				"message": _("« {0} » est déjà planifié sur ce créneau (séance commune).").format(_intitule(autre)),
			})
			continue
		communes = mes_classes & classes_du_cours(autre)
		if communes:
			resultat.append({
				"type": "classe",
				"item": seance.name,
				"cours": autre,
				"classes": sorted(communes),
				"message": _("Conflit de planning : la classe {0} est déjà occupée par « {1} » sur ce créneau.").format(
					", ".join(_libelle_classe(f, n) for f, n in sorted(communes)), _intitule(autre)
				),
			})
		profs = mes_enseignants & enseignants_du_cours(autre)
		if profs:
			resultat.append({
				"type": "enseignant",
				"item": seance.name,
				"cours": autre,
				"classes": [],
				"message": _("Conflit de planning : l'enseignant {0} est déjà programmé sur ce créneau (« {1} »).").format(
					", ".join(sorted(profs)), _intitule(autre)
				),
			})
		if salle and seance.salle == salle:
			resultat.append({
				"type": "salle",
				"item": seance.name,
				"cours": autre,
				"classes": [],
				"message": _("Conflit de salle : « {0} » est déjà utilisée par « {1} » sur ce créneau.").format(
					salle, _intitule(autre)
				),
			})
	return resultat


def verifier_conflits(cours, jour, period, salle=None, exclure=None):
	"""Lève une ValidationError listant tous les conflits, s'il y en a."""
	liste = conflits(cours, jour, period, salle=salle, exclure=exclure)
	if liste:
		frappe.throw("<br>".join(dict.fromkeys(c["message"] for c in liste)), title=_("Créneau indisponible"))
