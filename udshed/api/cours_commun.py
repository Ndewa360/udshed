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


def _exiger_migration():
	"""Le champ Teaching Unit.groupe_cours_commun n'existe qu'après `bench migrate`."""
	if not frappe.db.has_column("Teaching Unit", "groupe_cours_commun"):
		frappe.throw(
			_("La liaison de cours nécessite une mise à jour de la base : lancez « bench --site {0} migrate ».").format(
				frappe.local.site
			),
			title=_("Mise à jour requise"),
		)


def _verifier_droit(teaching_units):
	"""Un coordinateur relie un cours de SA grille à un cours de n'importe quelle autre grille :
	il suffit qu'un des cours concernés appartienne à une classe de son périmètre."""
	scope = planning_permission.get_scope()
	if scope["is_admin"]:
		return
	if not scope["can_plan"]:
		frappe.throw(_("Accès refusé : réservé aux coordinateurs et gestionnaires de planning."), frappe.PermissionError)
	niveaux = {str(n) for n in scope["niveaux"]}
	if not any(str(n) in niveaux for tu in teaching_units for _f, n in grille.classes_du_cours(tu)):
		frappe.throw(
			_("Accès refusé : au moins un des cours doit appartenir à une classe de votre périmètre."),
			frappe.PermissionError,
		)


def _verifier_classes_distinctes(membres):
	"""Un groupe lie des cours de grilles DIFFÉRENTES : une classe ne peut pas
	suivre deux cours d'un même groupe (ce serait le même enseignement deux fois)."""
	vues = {}
	for tu in sorted(membres):
		for classe in grille.classes_du_cours(tu):
			if classe in vues:
				frappe.throw(
					_("La classe {0} suit déjà « {1} » : elle ne peut pas aussi suivre « {2} » comme cours lié.").format(
						f"{classe[0]} {grille.libelle_niveau(classe[1])}",
						frappe.db.get_value("Teaching Unit", vues[classe], "intitule_cours") or vues[classe],
						frappe.db.get_value("Teaching Unit", tu, "intitule_cours") or tu,
					)
				)
			vues[classe] = tu


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
	_exiger_migration()
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
	_verifier_classes_distinctes(membres)
	for nom in membres:
		frappe.db.set_value("Teaching Unit", nom, "groupe_cours_commun", groupe)
	return groupe_de(noms[0])


@frappe.whitelist()
def delier_cours(teaching_unit):
	"""Retire un cours de son groupe (le groupe disparaît s'il ne reste qu'un cours)."""
	_exiger_migration()
	tu = _cours(teaching_unit)
	if not tu.groupe_cours_commun:
		return {"groupe": None, "cours": []}
	membres = frappe.get_all("Teaching Unit", filters={"groupe_cours_commun": tu.groupe_cours_commun}, pluck="name")
	_verifier_droit(membres or [teaching_unit])
	frappe.db.set_value("Teaching Unit", teaching_unit, "groupe_cours_commun", None)
	restants = frappe.get_all("Teaching Unit", filters={"groupe_cours_commun": tu.groupe_cours_commun}, pluck="name")
	if len(restants) == 1:
		frappe.db.set_value("Teaching Unit", restants[0], "groupe_cours_commun", None)
	return {"groupe": None, "cours": []}


@frappe.whitelist()
def groupe_de(teaching_unit):
	"""Cours du même groupe que `teaching_unit` (lui compris)."""
	_exiger_migration()
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
	_exiger_migration()
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


# ---------------------------------------------------------------------------
# Vue « deux grilles côte à côte »
# ---------------------------------------------------------------------------
def _grille_classe(academic_year, semestre, filiere, niveau):
	"""Cours d'une classe, groupés par UE (ordre : code UE, intitulé)."""
	filtres_semestre = "AND tu.semestre = %(semestre)s" if semestre else ""
	lignes = frappe.db.sql(
		f"""
		SELECT tu.name, tu.course, tu.intitule_cours, tu.semestre, tu.groupe_cours_commun,
		       tu.nombre_dheure_cm, tu.nombre_dheure_td, tu.nombre_dheure_tp, tu.nombre_dheure_tpe,
		       l.course_poid, ue.code AS ue_code, ue.intitule AS ue_intitule
		FROM `tabTeaching Unit` tu
		INNER JOIN `tabCourse Field of study level item` l ON l.parent = tu.name AND l.parenttype = 'Teaching Unit'
		LEFT JOIN `tabTeaching Unit Value` ue ON ue.name = tu.unite_de_valeur
		WHERE tu.academic_year = %(annee)s AND l.filiere = %(filiere)s AND l.niveau = %(niveau)s {filtres_semestre}
		""",
		{"annee": academic_year, "semestre": semestre, "filiere": filiere, "niveau": niveau},
		as_dict=True,
	)
	ues = {}
	for l in lignes:
		code_ue = l.ue_code or "UNKNOW"
		ue = ues.setdefault(code_ue, {"code": code_ue, "intitule": l.ue_intitule or "", "cours": []})
		ue["cours"].append({
			"teaching_unit": l.name,
			"code": l.course,
			"intitule": l.intitule_cours or l.course,
			"semestre": l.semestre,
			"credits": frappe.utils.flt(l.course_poid),
			"heures": grille.heures_face_a_face(l),
			"tpe": frappe.utils.flt(l.nombre_dheure_tpe),
			"groupe": l.groupe_cours_commun or None,
			"classes": len(grille.classes_du_cours(l.name)),
		})
	for ue in ues.values():
		ue["cours"].sort(key=lambda c: (_cle(c["intitule"]), c["code"] or ""))
	return sorted(ues.values(), key=lambda u: (u["code"] == "UNKNOW", u["code"]))


def _libelle_classe(filiere, niveau):
	nom = frappe.db.get_value("Field of study", filiere, "name_of_field") or filiere
	return f"{nom} — {grille.libelle_niveau(niveau)}"


@frappe.whitelist()
def comparer_grilles(academic_year, filiere_gauche, niveau_gauche, filiere_droite, niveau_droite, semestre=None):
	"""Deux grilles de classes différentes, avec leurs liens :
	  - « tronc_commun » : le même cours (Teaching Unit) est dans les deux grilles ;
	  - « lie » : deux cours différents déclarés identiques (groupe de cours commun) ;
	  - suggestions : intitulés identiques après normalisation, pas encore liés.
	"""
	_exiger_migration()
	scope = planning_permission.get_scope()
	if not (scope["is_admin"] or scope["can_plan"]):
		frappe.throw(_("Accès refusé : réservé aux coordinateurs et gestionnaires de planning."), frappe.PermissionError)
	if (filiere_gauche, str(niveau_gauche)) == (filiere_droite, str(niveau_droite)):
		frappe.throw(_("Choisissez deux classes différentes."))
	for filiere, niveau in ((filiere_gauche, niveau_gauche), (filiere_droite, niveau_droite)):
		if not frappe.db.exists("Field of study Level", {"name": niveau, "parent": filiere}):
			frappe.throw(_("Classe introuvable : ce niveau n'appartient pas à la filière choisie."))

	gauche = _grille_classe(academic_year, semestre, filiere_gauche, niveau_gauche)
	droite = _grille_classe(academic_year, semestre, filiere_droite, niveau_droite)
	cours_g = {c["teaching_unit"]: c for ue in gauche for c in ue["cours"]}
	cours_d = {c["teaching_unit"]: c for ue in droite for c in ue["cours"]}

	liens = []
	for tu in sorted(set(cours_g) & set(cours_d)):
		liens.append({"gauche": tu, "droite": tu, "type": "tronc_commun"})
	for tg, cg in sorted(cours_g.items()):
		if not cg["groupe"] or tg in cours_d:
			continue
		for td, cd in sorted(cours_d.items()):
			if td != tg and cd["groupe"] == cg["groupe"]:
				liens.append({"gauche": tg, "droite": td, "type": "lie"})

	deja = {(l["gauche"], l["droite"]) for l in liens} | {l["gauche"] for l in liens} | {l["droite"] for l in liens}
	suggestions = []
	for tg, cg in sorted(cours_g.items()):
		for td, cd in sorted(cours_d.items()):
			if tg == td or tg in deja or td in deja:
				continue
			if _cle(cg["intitule"]) and _cle(cg["intitule"]) == _cle(cd["intitule"]):
				suggestions.append({"gauche": tg, "droite": td})

	niveaux = {str(n) for n in scope["niveaux"]}
	peut_lier = scope["is_admin"] or str(niveau_gauche) in niveaux or str(niveau_droite) in niveaux
	return {
		"annee": academic_year,
		"semestre": semestre,
		"gauche": {"filiere": filiere_gauche, "niveau": niveau_gauche,
		           "libelle": _libelle_classe(filiere_gauche, niveau_gauche), "ues": gauche},
		"droite": {"filiere": filiere_droite, "niveau": niveau_droite,
		           "libelle": _libelle_classe(filiere_droite, niveau_droite), "ues": droite},
		"liens": liens,
		"suggestions": suggestions,
		"peut_lier": bool(peut_lier),
	}
