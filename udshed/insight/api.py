"""API du module Insight (pages « insight-academique » et « insight-financier »).

Un seul point d'entrée pour toutes les vues (année, faculté, filière, classe,
enseignant) : `tableau_de_bord`. Les calculs sont faits par udshed.insight.moteur.

Périmètre (jamais d'erreur masquée : un refus est un refus explicite)
  - Administrateur : tout ;
  - Comptable (page financière) : tout ;
  - Coordinateur / gestionnaire de planning : ses classes ;
  - Enseignant : ses propres cours (et, en finance, sa propre rémunération).
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from udshed.api import planning_permission
from udshed.insight import moteur
from udshed.utils import securite

PAGES = {"academique": "insight-academique", "financier": "insight-financier"}
ROLES_FINANCE_GLOBALE = {"Comptable"}


def _mode(mode):
	if mode not in PAGES:
		frappe.throw(_("Vue inconnue : {0}").format(mode))
	return mode


def perimetre(mode):
	"""{"global": bool, "niveaux": set|None, "enseignant": str|None, "libelle": str}."""
	securite.exiger_acces_page(PAGES[_mode(mode)])
	user = frappe.session.user
	roles = set(frappe.get_roles(user))
	if user == "Administrator" or "System Manager" in roles:
		return {"global": True, "niveaux": None, "enseignant": None, "libelle": _("Tout l'établissement")}
	if mode == "financier" and roles & ROLES_FINANCE_GLOBALE:
		return {"global": True, "niveaux": None, "enseignant": None, "libelle": _("Tout l'établissement")}
	scope = planning_permission.get_scope(user)
	if scope["can_plan"] and scope["niveaux"]:
		return {"global": False, "niveaux": {str(n) for n in scope["niveaux"]}, "enseignant": None,
		        "libelle": _("Vos classes ({0})").format(len(scope["niveaux"]))}
	if scope["teacher"]:
		return {"global": False, "niveaux": None, "enseignant": scope["teacher"], "libelle": _("Vos cours")}
	frappe.throw(_("Aucun périmètre d'analyse ne vous est attribué (aucune classe ni aucun cours)."), frappe.PermissionError)


def _classes_retenues(donnees, perim, faculty=None, filiere=None, niveau=None):
	classes = set()
	for cle, c in donnees.classes.items():
		if perim["niveaux"] is not None and cle[1] not in perim["niveaux"]:
			continue
		if faculty and c["faculte"] != faculty:
			continue
		if filiere and c["filiere"] != filiere:
			continue
		if niveau and c["niveau"] != str(niveau):
			continue
		classes.add(cle)
	return classes


def _verifier_filtres(perim, teacher, faculty, filiere, niveau):
	if perim["enseignant"]:
		if teacher and teacher != perim["enseignant"]:
			frappe.throw(_("Vous ne pouvez consulter que vos propres statistiques."), frappe.PermissionError)
	if perim["niveaux"] is not None and niveau and str(niveau) not in perim["niveaux"]:
		frappe.throw(_("Cette classe n'est pas dans votre périmètre."), frappe.PermissionError)
	if niveau and filiere and not frappe.db.exists("Field of study Level", {"name": niveau, "parent": filiere}):
		frappe.throw(_("Ce niveau n'appartient pas à la filière choisie."))


def _cours_de(resultat, classes):
	return [n for n, s in resultat["stats"].items() if any(tuple(c) in classes for c in s["classes_cles"])]


def _ligne(donnees, resultat, cle, libelle, classes, filtre):
	totaux = moteur.agreger(donnees, resultat, _cours_de(resultat, classes), classes)
	return {"cle": cle, "libelle": libelle, "filtre": filtre, **totaux}


def _repartition(donnees, resultat, vue, classes, enseignant):
	"""Lignes du niveau inférieur (cliquables pour descendre)."""
	groupes = {}
	for cle in classes:
		c = donnees.classes[cle]
		if vue == "annee":
			k, lib, filtre = c["faculte"], c["faculte_libelle"], {"faculty": c["faculte"]}
		elif vue == "faculte":
			k, lib, filtre = c["filiere"], c["filiere_libelle"], {"filiere": c["filiere"]}
		elif vue in ("filiere", "enseignant"):
			k, lib = f"{c['filiere']}|{c['niveau']}", c["libelle"]
			filtre = {"faculty": c["faculte"], "filiere": c["filiere"], "niveau": c["niveau"]}
		else:
			return []
		g = groupes.setdefault(k, {"libelle": lib, "filtre": filtre, "classes": set()})
		g["classes"].add(cle)
	lignes = [_ligne(donnees, resultat, k, g["libelle"], g["classes"], g["filtre"]) for k, g in groupes.items()]
	return sorted((l for l in lignes if l["cours"]), key=lambda l: l["libelle"])


def _alertes(donnees, resultat, kpis, mode, cours):
	alertes = []
	if kpis["en_retard"]:
		noms = ", ".join(c["code"] for c in cours if c["en_retard"])[:300]
		alertes.append({"niveau": "danger", "message": _("{0} cours en retard sur l'avancement attendu : {1}").format(kpis["en_retard"], noms)})
	if kpis["planning_incomplet"]:
		alertes.append({"niveau": "warning", "message": _("{0} cours n'ont pas assez de séances planifiées pour atteindre leur volume horaire.").format(kpis["planning_incomplet"])})
	if kpis["surplanifie"]:
		alertes.append({"niveau": "warning", "message": _("{0} cours ont plus d'heures planifiées que leur volume prévu.").format(kpis["surplanifie"])})
	non_pointees = round(kpis["echu"] - kpis["pointe"], 1)
	if kpis["echu"] and kpis["taux_pointage"] < 100:
		alertes.append({"niveau": "info", "message": _(
			"{0} h de séances passées ne sont pas pointées « Fait » : celles de la semaine en cours le seront "
			"automatiquement dimanche à 23 h ; les autres ont été déclarées non faites."
		).format(non_pointees)})
	sans_prof = [c["code"] for c in cours if c["cible"] and not c["enseignants"]]
	if sans_prof:
		alertes.append({"niveau": "warning", "message": _("{0} cours sans enseignant : {1}").format(len(sans_prof), ", ".join(sans_prof)[:300])})
	if mode == "financier":
		for titre, noms in resultat["alertes_tarifs"].items():
			alertes.append({"niveau": "danger", "message": _("Tarif horaire manquant pour « {0} » (Udshed Setting) : {1}").format(titre, ", ".join(noms)[:300])})
		if kpis["budget"] and kpis["engage"] > kpis["budget"] + 0.01:
			alertes.append({"niveau": "danger", "message": _("Le montant engagé dépasse le budget de {0} %.").format(round(kpis["taux_engage"] - 100, 1))})
	return alertes


def _evolution(resultat):
	cumul = {"planifie": 0.0, "echu": 0.0, "engage": 0.0, "realise": 0.0}
	points = []
	for lundi in sorted(resultat["semaines"]):
		s = resultat["semaines"][lundi]
		for k in cumul:
			cumul[k] += s[k]
		points.append({"semaine": str(lundi), **{k: round(v, 2) for k, v in s.items()},
		               **{f"{k}_cumule": round(v, 2) for k, v in cumul.items()}})
	return points


def _fil_ariane(donnees, faculty, filiere, niveau, teacher, perim):
	fil = [{"libelle": _("Établissement") if perim["global"] else perim["libelle"], "filtre": {}}]
	if faculty:
		fil.append({"libelle": frappe.db.get_value("Faculty", faculty, "faculty_name") or faculty, "filtre": {"faculty": faculty}})
	if filiere:
		fil.append({"libelle": frappe.db.get_value("Field of study", filiere, "name_of_field") or filiere,
		            "filtre": {"faculty": faculty, "filiere": filiere}})
	if niveau:
		fil.append({"libelle": frappe.db.get_value("Field of study Level", niveau, "level") or niveau,
		            "filtre": {"faculty": faculty, "filiere": filiere, "niveau": niveau}})
	if teacher:
		nom = donnees.enseignants.get(teacher, {}).get("nom") or frappe.db.get_value("Teacher", teacher, "full_name") or teacher
		fil.append({"libelle": nom, "filtre": {"teacher": teacher}})
	return fil


@frappe.whitelist()
def tableau_de_bord(mode, academic_year, faculty=None, filiere=None, niveau=None, semestre=None,
                    teacher=None, type_seance=None):
	"""Tableau de bord complet de la vue demandée."""
	if not academic_year:
		frappe.throw(_("Choisissez une année académique."))
	perim = perimetre(mode)
	teacher = teacher or perim["enseignant"]
	_verifier_filtres(perim, teacher, faculty, filiere, niveau)
	type_filtre = type_seance or None

	donnees = moteur.Donnees(academic_year, semestre or None)
	classes = _classes_retenues(donnees, perim, faculty, filiere, niveau)
	resultat = moteur.calculer(donnees, classes, enseignant=teacher, type_filtre=type_filtre)

	if teacher:
		vue = "enseignant"
	elif niveau:
		vue = "classe"
	elif filiere:
		vue = "filiere"
	elif faculty:
		vue = "faculte"
	else:
		vue = "annee"

	tous = _cours_de(resultat, classes)
	kpis = moteur.agreger(donnees, resultat, tous, classes)
	cours = []
	for nom in tous:
		s = dict(resultat["stats"][nom])
		s.pop("classes_cles", None)
		s.pop("attendu", None)
		for k in ("cible", "planifie", "echu", "pointe", "budget", "engage", "realise"):
			s[k] = round(flt(s[k]), 2)
		s["types"] = {k: v for k, v in s["types"].items() if v}
		s["taux_realise"] = moteur._pct(s["realise"], s["budget"])
		cours.append(s)
	ordre = {"non_planifie": 0, "en_cours": 1, "depassement": 2, "termine": 3, "sans_volume": 4}
	cours.sort(key=lambda c: (not c["en_retard"], ordre.get(c["statut"], 9), c["completion"], c["intitule"] or ""))

	types = {}
	for c in cours:
		for k, v in c["types"].items():
			types[k] = types.get(k, 0) + v

	return {
		"mode": mode,
		"vue": vue,
		"perimetre": perim["libelle"],
		"filtres": {"academic_year": academic_year, "faculty": faculty, "filiere": filiere, "niveau": niveau,
		            "semestre": semestre, "teacher": teacher, "type_seance": type_filtre},
		"fil_ariane": _fil_ariane(donnees, faculty, filiere, niveau, teacher, perim),
		"devise": donnees.devise,
		"date": str(getdate()),
		"kpis": kpis,
		"lignes": _repartition(donnees, resultat, vue, classes, teacher),
		"cours": cours,
		"types": [{"code": k, "libelle": moteur.LIBELLES_TYPES.get(k, k), "valeur": v} for k, v in sorted(types.items())],
		"evolution": _evolution(resultat),
		"alertes": _alertes(donnees, resultat, kpis, mode, cours),
		"enseignant_seul": bool(perim["enseignant"]),
	}


@frappe.whitelist()
def options_filtres(mode, academic_year, faculty=None, filiere=None):
	"""Facultés, filières, niveaux et enseignants disponibles DANS le périmètre."""
	perim = perimetre(mode)
	if not academic_year:
		return {"facultes": [], "filieres": [], "niveaux": [], "enseignants": [], "enseignant_seul": bool(perim["enseignant"])}
	donnees = moteur.Donnees(academic_year)
	classes = _classes_retenues(donnees, perim)
	if perim["enseignant"]:
		resultat = moteur.calculer(donnees, classes, enseignant=perim["enseignant"])
		classes = {tuple(c) for s in resultat["stats"].values() for c in s["classes_cles"]}
	facs, fils, nivs = {}, {}, {}
	for cle in classes:
		c = donnees.classes[cle]
		facs[c["faculte"]] = c["faculte_libelle"]
		if not faculty or c["faculte"] == faculty:
			fils[c["filiere"]] = c["filiere_libelle"]
		if filiere and c["filiere"] == filiere:
			nivs[c["niveau"]] = c["niveau_libelle"]
	enseignants = {}
	if not perim["enseignant"]:
		for nom, c in donnees.cours.items():
			if any(cl in classes for cl in c["classes"]):
				for e, _t in donnees.affectations.get(nom, []):
					enseignants[e] = donnees.enseignants.get(e, {}).get("nom", e)
	trier = lambda d: [{"value": k, "label": v} for k, v in sorted(d.items(), key=lambda x: (x[1] or "").lower()) if k]  # noqa: E731
	return {"facultes": trier(facs), "filieres": trier(fils), "niveaux": trier(nivs),
	        "enseignants": trier(enseignants), "enseignant_seul": bool(perim["enseignant"])}


@frappe.whitelist()
def exporter(mode, academic_year, faculty=None, filiere=None, niveau=None, semestre=None, teacher=None, type_seance=None):
	"""Export Excel de la vue courante : synthèse, répartition, cours, évolution, alertes."""
	from frappe.desk.utils import provide_binary_file

	from udshed.utils.excel import classeur_xlsx

	data = tableau_de_bord(mode, academic_year, faculty, filiere, niveau, semestre, teacher, type_seance)
	k = data["kpis"]
	devise = data["devise"]
	statuts = {"non_planifie": "Non planifié", "en_cours": "En cours", "termine": "Terminé",
	           "depassement": "Dépassement", "sans_volume": "Sans volume"}

	synthese = [["Indicateur", "Valeur"],
	            ["Périmètre", " › ".join(f["libelle"] for f in data["fil_ariane"])],
	            ["Année académique", academic_year], ["Semestre", semestre or "Tous"], ["Date", data["date"]],
	            ["Cours", k["cours"]], ["Volume prévu (h)", k["cible"]], ["Heures planifiées", k["planifie"]],
	            ["Heures effectuées (échues)", k["echu"]], ["Heures pointées « Fait »", k["pointe"]],
	            ["Taux de réalisation (%)", k["completion"]], ["Couverture du planning (%)", k["couverture"]],
	            ["Avancement attendu (%)", k["attendu"]], ["Cours en retard", k["en_retard"]],
	            ["Séances", k["seances"]], ["Séances annulées", k["annulees"]], ["Évaluations", k["evaluations"]]]
	if mode == "financier":
		synthese += [[f"Budget vacations ({devise})", k["budget"]], [f"Engagé ({devise})", k["engage"]],
		             [f"Réalisé ({devise})", k["realise"]], ["Taux réalisé (%)", k["taux_realise"]]]

	entete_l = ["Libellé", "Cours", "Prévu (h)", "Planifié (h)", "Effectué (h)", "Réalisation (%)", "En retard"]
	if mode == "financier":
		entete_l += [f"Budget ({devise})", f"Engagé ({devise})", f"Réalisé ({devise})"]
	repartition = [entete_l] + [
		[l["libelle"], l["cours"], l["cible"], l["planifie"], l["echu"], l["completion"], l["en_retard"]]
		+ ([l["budget"], l["engage"], l["realise"]] if mode == "financier" else [])
		for l in data["lignes"]
	]
	entete_c = ["Code", "Intitulé", "Semestre", "Classes", "Enseignants", "Prévu (h)", "Planifié (h)",
	            "Effectué (h)", "Pointé (h)", "Réalisation (%)", "Statut", "En retard"]
	if mode == "financier":
		entete_c += [f"Budget ({devise})", f"Engagé ({devise})", f"Réalisé ({devise})"]
	cours = [entete_c] + [
		[c["code"], c["intitule"], c["semestre"], ", ".join(c["classes"]), ", ".join(c["enseignants"]),
		 c["cible"], c["planifie"], c["echu"], c["pointe"], c["completion"], statuts.get(c["statut"], c["statut"]),
		 "Oui" if c["en_retard"] else ""]
		+ ([c["budget"], c["engage"], c["realise"]] if mode == "financier" else [])
		for c in data["cours"]
	]
	evolution = [["Semaine du", "Planifié (h)", "Effectué (h)", "Planifié cumulé", "Effectué cumulé"]
	             + (["Engagé cumulé", "Réalisé cumulé"] if mode == "financier" else [])] + [
		[e["semaine"], e["planifie"], e["echu"], e["planifie_cumule"], e["echu_cumule"]]
		+ ([e["engage_cumule"], e["realise_cumule"]] if mode == "financier" else [])
		for e in data["evolution"]
	]
	alertes = [["Niveau", "Alerte"]] + [[a["niveau"], a["message"]] for a in data["alertes"]]

	contenu = classeur_xlsx([
		(synthese, "Synthèse", [32, 40]),
		(repartition, "Répartition", [40] + [14] * 9),
		(cours, "Cours", [14, 40, 12, 40, 40] + [14] * 10),
		(evolution, "Évolution", [14, 14, 14, 16, 16, 16, 16]),
		(alertes, "Alertes", [12, 120]),
	])
	nom_fichier = f"insight_{mode}_{academic_year}".replace("/", "-")
	provide_binary_file(nom_fichier, "xlsx", contenu)
