# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Édition complète de la grille d'enseignement.

- Code d'un cours : renommage EN CASCADE (comme le « Renommer » de Frappe) ;
  notes, résultats, planning, délibérations… suivent automatiquement. Le
  nouveau code doit être libre pour l'année.
- Code d'une UE : même principe ; refusé si une autre UE de l'année porte déjà ce code.
- Déplacement d'un cours vers une autre UE (fiche du cours ou glisser-déposer).
- Fiche complète d'un cours : code, intitulé, UE, crédits, heures, enseignants,
  enregistrés en une seule fois.

Un cours de tronc commun (partagé par plusieurs classes) a un seul code, un seul
intitulé, une seule UE et les mêmes enseignants : les modifier vaut pour toutes
ses classes et exige `appliquer_au_tronc_commun=1`.
"""

import re

import frappe
from frappe import _

import udshed.api.planning_permission as planning_permission
from udshed.api import teaching_grid as tg
from udshed.utils import grille

CODE_VALIDE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._\-]*$")
TYPES_COURS = ("Cours Magistral (CM)", "Travaux Dirigés (TD)", "Travaux Pratique (TP)")
SANS_UE = "UNKNOW"


# ---------------------------------------------------------------------- #
#  Outils
# ---------------------------------------------------------------------- #
def _code_propre(code, libelle):
	code = " ".join(str(code or "").split())
	if not code:
		frappe.throw(_("{0} : obligatoire.").format(libelle))
	if len(code) > 60 or not CODE_VALIDE.match(code):
		frappe.throw(
			_("Code « {0} » invalide : lettres, chiffres, espaces, « . », « - » et « _ » uniquement.").format(code)
		)
	return code


def _nom_suivant(doctype, prefixe):
	"""Prochain nom libre « PREFIXE-0001 » (format de nommage des cours et des UE)."""
	motif = re.compile(re.escape(prefixe) + r"-(\d+)", re.IGNORECASE)
	numeros = [
		int(m.group(1))
		for nom in frappe.get_all(doctype, filters={"name": ["like", f"{prefixe}-%"]}, pluck="name")
		if (m := motif.fullmatch(nom))
	]
	n = max(numeros, default=0) + 1
	while frappe.db.exists(doctype, f"{prefixe}-{n:04d}"):
		n += 1
	return f"{prefixe}-{n:04d}"


def _renommer(doctype, ancien, nouveau):
	"""rename_doc en cascade, y compris pour un simple changement de casse
	(la base compare les noms sans tenir compte de la casse)."""
	from frappe.model.rename_doc import rename_doc

	options = dict(force=True, ignore_permissions=True, show_alert=False, rebuild_search=False)
	if ancien.lower() == nouveau.lower():
		temporaire = f"{nouveau}-renommage-{frappe.generate_hash(length=6)}"
		rename_doc(doctype, ancien, temporaire, **options)
		ancien = temporaire
	return rename_doc(doctype, ancien, nouveau, **options)


def _libelle_classe(filiere, niveau):
	nom = frappe.db.get_value("Field of study", filiere, "name_of_field") or filiere
	return f"{nom} — {grille.libelle_niveau(niveau)}"


def _classes_ue(ue_name):
	classes = set()
	for tu in frappe.get_all("Teaching Unit", filters={"unite_de_valeur": ue_name}, pluck="name"):
		classes |= grille.classes_du_cours(tu)
	return classes


def _ue_de_la_classe(ue_code, academic_year, filiere, niveau):
	"""UE de l'année portant ce code et contenant au moins un cours de la classe."""
	nom = frappe.db.get_value("Teaching Unit Value", {"code": ue_code, "academic_year": academic_year}, "name")
	if not nom:
		frappe.throw(_("UE introuvable."), frappe.DoesNotExistError)
	if (filiere, str(niveau)) not in _classes_ue(nom):
		frappe.throw(_("Cette UE n'appartient pas à la grille de cette classe."))
	return nom


def _supprimer_ue_si_vide(ue_name):
	if not ue_name or frappe.db.count("Teaching Unit", {"unite_de_valeur": ue_name}):
		return False
	if frappe.db.count("Resultat UE", {"teaching_unit_value": ue_name}):
		return False
	if frappe.db.count("Deliberation Jury Decision", {"unite": ue_name}):
		return False
	frappe.delete_doc("Teaching Unit Value", ue_name, ignore_permissions=True)
	return True


def _avertissement_resultats(teaching_unit):
	if frappe.db.count("Resultat UE Matiere", {"teaching_unit": teaching_unit}):
		return _(
			"Des résultats d'UE ont déjà été calculés avec ce cours : relancez le calcul des résultats "
			"pour qu'ils tiennent compte de la nouvelle UE."
		)
	return None


# ---------------------------------------------------------------------- #
#  Renommages en cascade
# ---------------------------------------------------------------------- #
def renommer_code_cours(teaching_unit, nouveau_code):
	"""Change le code du cours de cette UE d'enseignement, en cascade. Renvoie le
	nouveau nom de l'UE d'enseignement.

	- Code utilisé seulement par ce cours : le Cours est renommé (toutes les
	  références suivent).
	- Ancien code encore utilisé par d'autres années : il leur reste ; un Cours
	  est créé (ou réutilisé) avec le nouveau code pour cette année seulement.
	"""
	nouveau = _code_propre(nouveau_code, _("Code du cours"))
	tu = frappe.db.get_value("Teaching Unit", teaching_unit, ["name", "course", "academic_year"], as_dict=True)
	ancien = tu.course
	if nouveau == ancien:
		return tu.name

	occupe = frappe.db.get_value(
		"Teaching Unit",
		{"course": nouveau, "academic_year": tu.academic_year, "name": ["!=", tu.name]},
		["name", "intitule_cours"],
		as_dict=True,
	)
	if occupe:
		frappe.throw(
			_("Le code {0} est déjà utilisé en {1} par le cours « {2} ». Choisissez un autre code.").format(
				nouveau, tu.academic_year, occupe.intitule_cours or occupe.name
			),
			title=_("Code déjà utilisé"),
		)

	autres_annees = frappe.db.count("Teaching Unit", {"course": ancien, "name": ["!=", tu.name]})
	simple_casse = ancien.lower() == nouveau.lower()
	if frappe.db.exists("Course", nouveau) and not simple_casse:
		# Le code existe déjà (autre année) : ce cours y est rattaché.
		frappe.db.set_value("Teaching Unit", tu.name, "course", nouveau)
		if not autres_annees:
			frappe.delete_doc("Course", ancien, ignore_permissions=True, ignore_missing=True)
	elif not autres_annees:
		_renommer("Course", ancien, nouveau)
	else:
		if simple_casse:
			frappe.throw(_("Ce code est utilisé par d'autres années : un simple changement de majuscules n'est pas possible."))
		copie = frappe.copy_doc(frappe.get_doc("Course", ancien))
		copie.code = nouveau
		copie.insert(ignore_permissions=True)
		frappe.db.set_value("Teaching Unit", tu.name, "course", copie.name)

	# Nom interne de l'UE d'enseignement (« CODE-0001 ») : renommé lui aussi, en cascade.
	nouveau_nom = _renommer("Teaching Unit", tu.name, _nom_suivant("Teaching Unit", nouveau))
	# Copies du code en texte.
	frappe.db.sql("UPDATE `tabResultat UE Matiere` SET code = %s WHERE teaching_unit = %s", (nouveau, nouveau_nom))
	return nouveau_nom


def renommer_code_ue(ue_name, nouveau_code):
	nouveau = _code_propre(nouveau_code, _("Code de l'UE"))
	ue = frappe.db.get_value("Teaching Unit Value", ue_name, ["name", "code", "academic_year"], as_dict=True)
	if ue.code == SANS_UE or nouveau.upper() == SANS_UE:
		frappe.throw(_("Ce code d'UE est réservé."))
	if nouveau == ue.code:
		return ue.name
	occupe = frappe.db.get_value(
		"Teaching Unit Value", {"code": nouveau, "academic_year": ue.academic_year, "name": ["!=", ue.name]}, "name"
	)
	if occupe:
		frappe.throw(
			_("L'UE {0} existe déjà en {1}. Pour regrouper les deux UE, déplacez les cours vers celle-ci.").format(
				nouveau, ue.academic_year
			),
			title=_("Code déjà utilisé"),
		)
	frappe.db.set_value("Teaching Unit Value", ue.name, "code", nouveau)
	nouveau_nom = _renommer("Teaching Unit Value", ue.name, _nom_suivant("Teaching Unit Value", nouveau))
	frappe.db.sql("UPDATE `tabResultat UE` SET ue_code = %s WHERE teaching_unit_value = %s", (nouveau, nouveau_nom))
	return nouveau_nom


# ---------------------------------------------------------------------- #
#  API : UE
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def infos_ue(ue_code, academic_year, faculty, filiere, niveau, semestre):
	planning_permission.assert_can_manage_grid(academic_year, faculty, filiere, niveau, semestre)
	nom = _ue_de_la_classe(ue_code, academic_year, filiere, niveau)
	ue = frappe.db.get_value("Teaching Unit Value", nom, ["code", "intitule", "semestre"], as_dict=True)
	autres = sorted(c for c in _classes_ue(nom) if c != (filiere, str(niveau)))
	return {
		"ue": nom,
		"code": ue.code,
		"intitule": ue.intitule,
		"autres_classes": [_libelle_classe(f, n) for f, n in autres],
		"resultats": frappe.db.count("Resultat UE", {"teaching_unit_value": nom}),
	}


@frappe.whitelist()
def enregistrer_ue(ue_code, academic_year, faculty, filiere, niveau, semestre, code=None, intitule=None,
				   appliquer_aux_autres_classes=0):
	"""Code et intitulé d'une UE. L'UE est commune à toutes les classes qui y ont des cours."""
	planning_permission.assert_can_manage_grid(academic_year, faculty, filiere, niveau, semestre)
	nom = _ue_de_la_classe(ue_code, academic_year, filiere, niveau)
	ue = frappe.get_doc("Teaching Unit Value", nom)
	intitule = str(intitule or "").strip() if intitule is not None else ue.intitule
	if not intitule:
		frappe.throw(_("L'intitulé de l'UE ne peut pas être vide."))
	code = " ".join(str(code or "").split()) or ue.code
	if code == ue.code and intitule == ue.intitule:
		return {"ue": nom, "code": code}
	autres = sorted(c for c in _classes_ue(nom) if c != (filiere, str(niveau)))
	if autres and not frappe.utils.cint(appliquer_aux_autres_classes):
		frappe.throw(
			_("Cette UE est aussi utilisée par {0} : la modification vaudra pour ces classes.").format(
				", ".join(_libelle_classe(f, n) for f, n in autres)
			),
			title=_("UE partagée"),
			exc=frappe.ValidationError,
		)
	if intitule != ue.intitule:
		frappe.db.set_value("Teaching Unit Value", nom, "intitule", intitule)
		frappe.db.sql("UPDATE `tabResultat UE` SET ue_intitule = %s WHERE teaching_unit_value = %s", (intitule, nom))
	nom = renommer_code_ue(nom, code)
	return {"ue": nom, "code": code}


@frappe.whitelist()
def changer_ue(teaching_unit, ue_code, academic_year, faculty, filiere, niveau, semestre, ue_intitule=None,
			   appliquer_au_tronc_commun=0):
	"""Déplace un cours vers une autre UE (existante, ou créée avec `ue_intitule`)."""
	planning_permission.assert_can_manage_grid(academic_year, faculty, filiere, niveau, semestre)
	tu, autres = tg._classe_du_cours(teaching_unit, filiere, niveau)
	if autres and not frappe.utils.cint(appliquer_au_tronc_commun):
		_refus_tronc_commun(autres)
	ancienne = tu.unite_de_valeur
	tu.unite_de_valeur = _ue_cible(ue_code, ue_intitule, tu, filiere)
	if tu.unite_de_valeur == ancienne:
		return {"teaching_unit": tu.name, "avertissement": None}
	tu.save(ignore_permissions=True)
	_supprimer_ue_si_vide(ancienne)
	return {"teaching_unit": tu.name, "avertissement": _avertissement_resultats(tu.name)}


def _ue_cible(ue_code, ue_intitule, tu, filiere):
	if not frappe.db.get_value("Field of study", filiere, "has_uv_in_grid"):
		frappe.throw(_("Cette filière n'organise pas sa grille en UE."))
	code = _code_propre(ue_code, _("UE"))
	cible = frappe.db.get_value(
		"Teaching Unit Value", {"code": code, "academic_year": tu.academic_year}, ["name", "semestre"], as_dict=True
	)
	if cible:
		if cible.semestre and tu.semestre and cible.semestre != tu.semestre:
			frappe.throw(_("L'UE {0} est au {1} alors que le cours est au {2}.").format(code, cible.semestre, tu.semestre))
		return cible.name
	if code.upper() == SANS_UE:
		frappe.throw(_("Ce code d'UE est réservé."))
	return tg._appliquer_ue({"code": code, "intitule": str(ue_intitule or "").strip() or code}, tu.academic_year,
						   tu.semestre)


def _refus_tronc_commun(autres):
	frappe.throw(
		_("Ce cours est partagé avec {0} : code, intitulé, heures, UE et enseignants seront modifiés pour toutes ces classes.").format(
			", ".join(autres)
		),
		title=_("Cours de tronc commun"),
		exc=frappe.ValidationError,
	)


# ---------------------------------------------------------------------- #
#  API : fiche complète d'un cours
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def infos_cours(teaching_unit, academic_year, faculty, filiere, niveau, semestre):
	planning_permission.assert_can_manage_grid(academic_year, faculty, filiere, niveau, semestre)
	tu, autres = tg._classe_du_cours(teaching_unit, filiere, niveau)
	ligne = next(r for r in tu.course_levels if r.filiere == filiere and str(r.niveau) == str(niveau))
	deps = grille.dependances_cours(tu.name)
	return {
		"teaching_unit": tu.name,
		"code": tu.course,
		"intitule_cours": tu.intitule_cours,
		"credits": ligne.course_poid,
		**{champ: tu.get(champ) or 0 for champ in tg._CHAMPS_HEURES},
		"ue_code": frappe.db.get_value("Teaching Unit Value", tu.unite_de_valeur, "code") if tu.unite_de_valeur else None,
		"avec_ue": bool(frappe.db.get_value("Field of study", filiere, "has_uv_in_grid")),
		"enseignants": [{"enseignant": r.enseignant, "type_de_cours": r.type_de_cours} for r in tu.table_enseignant],
		"autres_classes": autres,
		"donnees": grille.decrire_dependances(deps) if deps else "",
	}


@frappe.whitelist()
def enregistrer_cours(teaching_unit, academic_year, faculty, filiere, niveau, semestre, valeurs,
					  appliquer_au_tronc_commun=0):
	"""Enregistre la fiche complète d'un cours en une transaction.

	`valeurs` : code, intitule_cours, credits, nombre_dheure_cm/td/tp/tpe,
	ue_code (+ ue_intitule pour une nouvelle UE), enseignants [{enseignant, type_de_cours}].
	Les clés absentes ne sont pas modifiées.
	"""
	planning_permission.assert_can_manage_grid(academic_year, faculty, filiere, niveau, semestre)
	valeurs = frappe.parse_json(valeurs) if isinstance(valeurs, str) else (valeurs or {})
	tu, autres = tg._classe_du_cours(teaching_unit, filiere, niveau)
	ancienne_ue = tu.unite_de_valeur
	avertissements = []

	communs = {}
	if "intitule_cours" in valeurs:
		intitule = str(valeurs.get("intitule_cours") or "").strip()
		if not intitule:
			frappe.throw(_("L'intitulé ne peut pas être vide."))
		communs["intitule_cours"] = intitule
	for champ in tg._CHAMPS_HEURES:
		if champ in valeurs:
			communs[champ] = tg._nombre_positif(valeurs[champ], _("Heures"), entier=True)
	modifies = {k: v for k, v in communs.items() if tu.get(k) != v}

	nouvelle_ue = None
	if valeurs.get("ue_code"):
		nouvelle_ue = _ue_cible(valeurs["ue_code"], valeurs.get("ue_intitule"), tu, filiere)
		if nouvelle_ue == ancienne_ue:
			nouvelle_ue = None

	enseignants = None
	if "enseignants" in valeurs:
		enseignants, vus = [], set()
		for e in valeurs.get("enseignants") or []:
			ens, type_cours = (e or {}).get("enseignant"), (e or {}).get("type_de_cours") or TYPES_COURS[0]
			if not ens:
				continue
			if not frappe.db.exists("Teacher", ens):
				frappe.throw(_("Enseignant « {0} » introuvable.").format(ens))
			if type_cours not in TYPES_COURS:
				frappe.throw(_("Type de séance invalide : {0}.").format(type_cours))
			if (ens, type_cours) not in vus:
				vus.add((ens, type_cours))
				enseignants.append({"enseignant": ens, "type_de_cours": type_cours})
		actuels = [(r.enseignant, r.type_de_cours) for r in tu.table_enseignant]
		if sorted(actuels) == sorted(vus):
			enseignants = None

	code = " ".join(str(valeurs.get("code") or "").split())
	change_code = bool(code) and code != tu.course
	if autres and (modifies or nouvelle_ue or enseignants is not None or change_code) and not frappe.utils.cint(
		appliquer_au_tronc_commun
	):
		_refus_tronc_commun(autres)

	for champ, valeur in modifies.items():
		tu.set(champ, valeur)
	if nouvelle_ue:
		tu.unite_de_valeur = nouvelle_ue
	if enseignants is not None:
		tu.set("table_enseignant", enseignants)
	ligne = next(r for r in tu.course_levels if r.filiere == filiere and str(r.niveau) == str(niveau))
	if "credits" in valeurs:
		ligne.course_poid = tg._nombre_positif(valeurs["credits"], _("Crédits"))
		if not autres:
			tu.credits = int(round(ligne.course_poid))
	tu.save(ignore_permissions=True)

	if nouvelle_ue:
		_supprimer_ue_si_vide(ancienne_ue)
		avertissements.append(_avertissement_resultats(tu.name))
	nom = renommer_code_cours(tu.name, code) if change_code else tu.name
	avertissements.append(grille.coherence_credits(ligne.course_poid, frappe.get_doc("Teaching Unit", nom)))
	return {"teaching_unit": nom, "avertissements": [a for a in avertissements if a]}
