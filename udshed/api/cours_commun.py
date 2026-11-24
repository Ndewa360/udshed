"""Liaison manuelle de cours : « même cours, intitulés différents selon les grilles ».

Deux cours (Teaching Unit) d'une même année, issus de grilles différentes,
peuvent être en réalité le même enseignement. On les place alors dans un même
« groupe de cours commun » (champ Teaching Unit.groupe_cours_commun) :
  - planifier l'un occupe toutes les classes du groupe (pas de double
    programmation, cf. udshed.utils.planning_conflits) ;
  - la séance apparaît dans le planning de chaque classe du groupe.

Droit : il faut gérer au moins une classe de CHACUN des cours liés (un
administrateur peut tout lier). Lier crée une contrainte sur le planning des
autres classes : on ne peut pas l'imposer à une classe hors de son périmètre.
"""

import unicodedata

import frappe
from frappe import _

from udshed.api import planning_permission
from udshed.utils import grille


def _verifier_droit(teaching_units):
	scope = planning_permission.get_scope()
	if scope["is_admin"]:
		return
	if not scope["can_plan"]:
		frappe.throw(_("Accès refusé : réservé aux coordinateurs et gestionnaires de planning."), frappe.PermissionError)
	niveaux = {str(n) for n in scope["niveaux"]}
	for tu in teaching_units:
		if not any(str(n) in niveaux for _f, n in grille.classes_du_cours(tu)):
			frappe.throw(
				_("Accès refusé : le cours {0} n'appartient à aucune classe de votre périmètre.").format(tu),
				frappe.PermissionError,
			)


def _cours(teaching_unit):
	doc = frappe.db.get_value(
		"Teaching Unit", teaching_unit,
		["name", "course", "intitule_cours", "academic_year", "semestre", "groupe_cours_commun",
		 "nombre_dheure_cm", "nombre_dheure_td", "nombre_dheure_tp"],
		as_dict=True,
	)
	if not doc:
		frappe.throw(_("Cours introuvable : {0}").format(teaching_unit), frappe.DoesNotExistError)
	return doc


def _description(tu):
	classes = sorted(grille.classes_du_cours(tu.name))
	return {
		"teaching_unit": tu.name,
		"code": tu.course,
		"intitule": tu.intitule_cours,
		"semestre": tu.semestre,
		"classes": [f"{f} {grille.libelle_niveau(n)}" for f, n in classes],
		"heures": grille.heures_face_a_face(tu),
	}


@frappe.whitelist()
def lier_cours(teaching_units):
	"""Place les cours dans un même groupe (fusionne les groupes existants)."""
	noms = frappe.parse_json(teaching_units) if isinstance(teaching_units, str) else list(teaching_units or [])
	noms = list(dict.fromkeys(n for n in noms if n))
	if len(noms) < 2:
		frappe.throw(_("Sélectionnez au moins deux cours à lier."))
	cours = [_cours(n) for n in noms]
	if len({c.academic_year for c in cours}) > 1:
		frappe.throw(_("Seuls des cours d'une même année académique peuvent être liés."))
	if len({c.semestre for c in cours}) > 1:
		frappe.throw(_("Les cours liés doivent être du même semestre."))
	_verifier_droit(noms)

	groupes = {c.groupe_cours_commun for c in cours if c.groupe_cours_commun}
	groupe = sorted(groupes)[0] if groupes else f"GCC-{frappe.generate_hash(length=10).upper()}"
	membres = set(noms)
	if groupes:
		membres |= set(frappe.get_all("Teaching Unit", filters={"groupe_cours_commun": ["in", list(groupes)]}, pluck="name"))
	for nom in membres:
		frappe.db.set_value("Teaching Unit", nom, "groupe_cours_commun", groupe)
	return groupe_de(noms[0])


@frappe.whitelist()
def delier_cours(teaching_unit):
	"""Retire un cours de son groupe (le groupe disparaît s'il ne reste qu'un cours)."""
	tu = _cours(teaching_unit)
	if not tu.groupe_cours_commun:
		return {"groupe": None, "cours": []}
	_verifier_droit([teaching_unit])
	frappe.db.set_value("Teaching Unit", teaching_unit, "groupe_cours_commun", None)
	restants = frappe.get_all("Teaching Unit", filters={"groupe_cours_commun": tu.groupe_cours_commun}, pluck="name")
	if len(restants) == 1:
		frappe.db.set_value("Teaching Unit", restants[0], "groupe_cours_commun", None)
	return {"groupe": None, "cours": []}


@frappe.whitelist()
def groupe_de(teaching_unit):
	"""Cours du même groupe que `teaching_unit` (lui compris)."""
	tu = _cours(teaching_unit)
	if not tu.groupe_cours_commun:
		return {"groupe": None, "cours": [_description(tu)]}
	membres = frappe.get_all("Teaching Unit", filters={"groupe_cours_commun": tu.groupe_cours_commun}, pluck="name")
	return {"groupe": tu.groupe_cours_commun, "cours": [_description(_cours(m)) for m in sorted(membres)]}


def _cle(texte):
	texte = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode().lower()
	return " ".join("".join(c if c.isalnum() else " " for c in texte).split())


@frappe.whitelist()
def suggestions(academic_year, semestre=None):
	"""Cours probablement identiques, non encore liés : même intitulé normalisé
	(casse, accents, ponctuation) dans des classes différentes."""
	planning_permission.assert_can_plan(academic_year, require_filters=False)
	filtres = {"academic_year": academic_year}
	if semestre:
		filtres["semestre"] = semestre
	cours = frappe.get_all(
		"Teaching Unit", filters=filtres,
		fields=["name", "course", "intitule_cours", "academic_year", "semestre", "groupe_cours_commun",
		        "nombre_dheure_cm", "nombre_dheure_td", "nombre_dheure_tp"],
	)
	par_cle = {}
	for c in cours:
		cle = (_cle(c.intitule_cours), c.semestre)
		if cle[0]:
			par_cle.setdefault(cle, []).append(c)
	resultat = []
	for (cle, _semestre), membres in sorted(par_cle.items()):
		groupes = {m.groupe_cours_commun for m in membres}
		if len(membres) < 2 or (len(groupes) == 1 and None not in groupes and "" not in groupes):
			continue
		resultat.append({"intitule": membres[0].intitule_cours, "cours": [_description(m) for m in membres]})
	return resultat
