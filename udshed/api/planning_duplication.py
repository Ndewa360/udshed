"""Duplication du planning d'une classe d'une semaine à une autre.

Principe : chaque séance de la semaine source est recopiée au même jour et au
même créneau de la semaine cible, uniquement si ce créneau est réellement
libre. Les règles de conflit sont celles du planning (udshed.utils.planning_conflits) :
  - créneau déjà occupé dans la classe (par exemple par un cours de tronc
    commun programmé par une autre classe) : la séance n'est pas recopiée ;
  - tronc commun / cours lié déjà programmé sur ce créneau : rien à faire ;
  - enseignant indisponible : non recopiée ;
  - seule la salle est prise : séance recopiée SANS salle (à réattribuer).

La prévisualisation renvoie aussi un récapitulatif complet de la semaine
cible : créneaux libres, occupés (tronc commun / autre cours) et à créer.
"""

from datetime import timedelta

import frappe
from frappe import _

from udshed.api import planning_calendar
from udshed.api.planning_period import _get_period_impl
from udshed.utils import planning_conflits

TYPES_COURS = {
	"Cours Magistral (CM)",
	"Traveaux Pratiques (TP)",
	"Traveaux Dirigés (TD)",
	"Travaux Pratique (TP)",
	"Travaux Dirigés (TD)",
}
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]


def _lundi(valeur):
	jour = planning_calendar.parse_date(valeur)
	return jour - timedelta(days=jour.weekday())


def _est_commun(teaching_unit):
	"""Tronc commun (plusieurs classes) ou cours lié à un cours d'une autre grille."""
	return len(planning_conflits.classes_du_cours(teaching_unit)) > 1


def _seances(academic_year, lundi, filiere, niveau):
	"""Séances de la classe pour la semaine (tronc commun et cours liés compris), sans doublon."""
	vues = {}
	for row in planning_calendar.get_week_planning(academic_year, lundi, filiere=filiere, niveau=niveau) or []:
		vues.setdefault(row["name"], row)
	return list(vues.values())


def _analyser(academic_year, filiere, niveau, semaine_source, semaine_cible, inclure_evaluations):
	faculty = frappe.db.get_value("Field of study", filiere, "faculte")
	planning_calendar.planning_permission.assert_can_plan(academic_year, faculty, filiere, niveau)
	source, cible = _lundi(semaine_source), _lundi(semaine_cible)
	if source == cible:
		frappe.throw(_("Les semaines source et cible doivent être différentes."))
	decalage = cible - source

	periodes = _get_period_impl(niveau, cible, academic_year) or []
	ordre_periodes = {p["name"]: i for i, p in enumerate(periodes)}

	seances = []
	for s in sorted(_seances(academic_year, source, filiere, niveau),
	                key=lambda r: (str(r["date"]), ordre_periodes.get(r["period"], 99))):
		jour = planning_calendar.parse_date(s["date"]) + decalage
		element = {
			"source": s["name"],
			"cours": s["cours"],
			"intitule": s.get("intitule_label") or s.get("course_label") or s["cours"],
			"type": s["type"],
			"mode": s.get("mode") or "En présentiel",
			"batiment": s.get("batiment_name") or None,
			"salle": s.get("salle_name") or None,
			"date": str(jour),
			"jour": JOURS[jour.weekday()] if jour.weekday() < len(JOURS) else str(jour),
			"period": s["period"],
			"commun": _est_commun(s["cours"]),
			"motif": "",
		}
		if not inclure_evaluations and s["type"] not in TYPES_COURS:
			element["action"] = "ignoree"
			element["motif"] = _("Évaluation (non dupliquée par défaut).")
			seances.append(element)
			continue

		salle = element["salle"] if element["mode"] != "En ligne" else None
		liste = planning_conflits.conflits(s["cours"], jour, s["period"], salle=salle)
		groupe = planning_conflits.cours_lies(s["cours"]) | {s["cours"]}
		if any(c["cours"] in groupe for c in liste):
			element["action"] = "deja_planifiee"
			element["motif"] = _("Déjà programmée sur ce créneau (cours commun planifié par une autre classe).")
		elif any(c["type"] == "classe" for c in liste):
			element["action"] = "conflit"
			element["motif"] = next(c["message"] for c in liste if c["type"] == "classe")
		elif any(c["type"] == "enseignant" for c in liste):
			element["action"] = "conflit"
			element["motif"] = next(c["message"] for c in liste if c["type"] == "enseignant")
		elif liste:
			element["action"] = "sans_salle"
			element["motif"] = _("Salle {0} déjà occupée : séance créée sans salle (à réattribuer).").format(element["salle"])
		else:
			element["action"] = "a_creer"
		seances.append(element)

	# Récapitulatif de la semaine cible, créneau par créneau.
	occupants = {}
	for s in _seances(academic_year, cible, filiere, niveau):
		cle = (str(planning_calendar.parse_date(s["date"])), s["period"])
		occupants.setdefault(cle, []).append(s)
	a_creer = {(e["date"], e["period"]): e for e in seances if e["action"] in ("a_creer", "sans_salle")}
	recap = []
	for periode in periodes:
		ligne = {"period": periode["name"], "libelle": periode.get("libelle") or "",
		         "heures": f"{str(periode.get('heure_de_debut'))[:5]} - {str(periode.get('heure_de_fin'))[:5]}", "jours": []}
		for i in range(len(JOURS)):
			jour = str(cible + timedelta(days=i))
			cle = (jour, periode["name"])
			if cle in occupants:
				s = occupants[cle][0]
				commun = _est_commun(s["cours"])
				ligne["jours"].append({
					"etat": "occupe_commun" if commun else "occupe",
					"texte": s.get("intitule_label") or s["cours"],
				})
			elif cle in a_creer:
				ligne["jours"].append({"etat": a_creer[cle]["action"], "texte": a_creer[cle]["intitule"]})
			else:
				ligne["jours"].append({"etat": "libre", "texte": ""})
		recap.append(ligne)

	actions = [e["action"] for e in seances]
	etats = [c["etat"] for ligne in recap for c in ligne["jours"]]
	return {
		"semaine_source": str(source),
		"semaine_cible": str(cible),
		"jours": [f"{JOURS[i]} {(cible + timedelta(days=i)).strftime('%d/%m')}" for i in range(len(JOURS))],
		"seances": seances,
		"recapitulatif": recap,
		"stats": {
			"a_creer": actions.count("a_creer"),
			"sans_salle": actions.count("sans_salle"),
			"deja_planifiees": actions.count("deja_planifiee"),
			"conflits": actions.count("conflit"),
			"ignorees": actions.count("ignoree"),
			"creneaux_libres": etats.count("libre"),
			"creneaux_tronc_commun": etats.count("occupe_commun"),
			"creneaux_occupes": etats.count("occupe"),
		},
	}


@frappe.whitelist()
def previsualiser_duplication(academic_year, filiere, niveau, semaine_source, semaine_cible, inclure_evaluations=0):
	"""Ce que donnerait la duplication, sans rien écrire."""
	return _analyser(academic_year, filiere, niveau, semaine_source, semaine_cible, frappe.utils.cint(inclure_evaluations))


@frappe.whitelist(methods=["POST"])
def dupliquer_semaine(academic_year, filiere, niveau, semaine_source, semaine_cible, inclure_evaluations=0):
	"""Recopie les séances libres de la semaine source vers la semaine cible.

	Chaque séance est réenregistrée via Planning Item (validate) : un créneau
	pris entre la prévisualisation et la duplication est simplement signalé.
	"""
	analyse = _analyser(academic_year, filiere, niveau, semaine_source, semaine_cible, frappe.utils.cint(inclure_evaluations))
	creees, echecs = [], []
	for e in analyse["seances"]:
		if e["action"] not in ("a_creer", "sans_salle"):
			continue
		sans_salle = e["action"] == "sans_salle"
		frappe.db.savepoint("udshed_duplication")
		try:
			doc = frappe.get_doc({
				"doctype": "Planning Item",
				"cours": e["cours"],
				"type": e["type"],
				"date": e["date"],
				"period": e["period"],
				"academic_year": academic_year,
				"mode": e["mode"],
				"batiment": None if sans_salle else e["batiment"],
				"salle": None if sans_salle else e["salle"],
			}).insert(ignore_permissions=True)
			creees.append(doc.name)
		except frappe.ValidationError as exc:
			# Créneau pris entre-temps : on annule cette seule séance et on continue.
			frappe.db.rollback(save_point="udshed_duplication")
			frappe.clear_messages()
			echecs.append({"intitule": e["intitule"], "date": e["date"], "motif": frappe.utils.strip_html(str(exc))})
	return {"creees": len(creees), "echecs": echecs, "stats": analyse["stats"]}
