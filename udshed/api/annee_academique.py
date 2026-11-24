"""Création d'une année académique : reprise des grilles d'une année précédente.

Au lieu de réimporter chaque grille à chaque rentrée, on recopie les grilles
des classes choisies depuis une année source :
  - UE recopiées (même code) ;
  - cours recopiés (même code, intitulé, semestre, heures, crédits par classe),
    enseignants en option ;
  - un cours de tronc commun n'est recopié qu'une fois et rattaché à toutes les
    classes cochées qui le suivent (les classes non cochées ne sont pas reprises) ;
  - liaisons « cours communs » recopiées en option, entre cours recopiés.
Relancer la reprise ne crée aucun doublon (classes déjà présentes ignorées).
"""

import frappe
from frappe import _

from udshed.utils import grille, securite


def _verifier_droits():
	securite.exiger_permission("Academic Year", "write")
	securite.exiger_permission("Teaching Unit", "create")


def annee_precedente(annee):
	"""Année dont la fin correspond au début de `annee`, sinon la plus récente avant elle."""
	debut = frappe.db.get_value("Academic Year", annee, "start_year")
	if debut:
		trouvee = frappe.db.get_value("Academic Year", {"end_year": debut, "name": ["!=", annee]}, "name")
		if trouvee:
			return trouvee
	autres = frappe.get_all("Academic Year", filters={"name": ["!=", annee]}, fields=["name", "start_year"])
	anterieures = [a for a in autres if not debut or str(a.start_year or "") < str(debut)]
	return max(anterieures or autres, key=lambda a: str(a.start_year or ""), default=frappe._dict()).get("name")


def _lignes_source(annee_source):
	return frappe.db.sql(
		"""
		SELECT tu.name AS teaching_unit, tu.semestre, l.filiere, l.niveau, l.course_poid
		FROM `tabTeaching Unit` tu
		INNER JOIN `tabCourse Field of study level item` l ON l.parent = tu.name AND l.parenttype = 'Teaching Unit'
		WHERE tu.academic_year = %s
		""",
		annee_source,
		as_dict=True,
	)


@frappe.whitelist()
def apercu_grilles(annee_cible, annee_source=None):
	"""Classes ayant une grille dans l'année source, avec leurs volumes, et ce
	qui existe déjà dans l'année cible."""
	_verifier_droits()
	annee_source = annee_source or annee_precedente(annee_cible)
	if not annee_source:
		return {"annee_source": None, "classes": []}
	if annee_source == annee_cible:
		frappe.throw(_("L'année source doit être différente de la nouvelle année."))

	classes = {}
	for ligne in _lignes_source(annee_source):
		cle = (ligne.filiere, str(ligne.niveau))
		c = classes.setdefault(cle, {
			"filiere": ligne.filiere,
			"niveau": ligne.niveau,
			"filiere_label": frappe.db.get_value("Field of study", ligne.filiere, "name_of_field") or ligne.filiere,
			"faculte": frappe.db.get_value("Field of study", ligne.filiere, "faculte") or "",
			"niveau_label": grille.libelle_niveau(ligne.niveau),
			"cours": 0,
			"credits": 0.0,
			"semestres": {},
			"deja_presents": 0,
		})
		c["cours"] += 1
		c["credits"] += float(ligne.course_poid or 0)
		c["semestres"][ligne.semestre or ""] = c["semestres"].get(ligne.semestre or "", 0) + 1

	for (filiere, niveau), c in classes.items():
		c["deja_presents"] = frappe.db.sql(
			"""
			SELECT COUNT(*) FROM `tabTeaching Unit` tu
			INNER JOIN `tabCourse Field of study level item` l ON l.parent = tu.name AND l.parenttype = 'Teaching Unit'
			WHERE tu.academic_year = %s AND l.filiere = %s AND l.niveau = %s
			""",
			(annee_cible, filiere, niveau),
		)[0][0]
	return {
		"annee_source": annee_source,
		"classes": sorted(classes.values(), key=lambda c: (c["faculte"], c["filiere_label"], c["niveau_label"])),
	}


def _ue_cible(ue_source, annee_cible, cache):
	if not ue_source:
		return None
	if ue_source not in cache:
		src = frappe.db.get_value("Teaching Unit Value", ue_source, ["code", "intitule", "semestre"], as_dict=True)
		if not src:
			cache[ue_source] = None
		else:
			nom = frappe.db.get_value("Teaching Unit Value", {"code": src.code, "academic_year": annee_cible}, "name")
			if not nom:
				nom = frappe.get_doc({
					"doctype": "Teaching Unit Value", "code": src.code, "intitule": src.intitule,
					"semestre": src.semestre, "academic_year": annee_cible,
				}).insert(ignore_permissions=True).name
				cache["__crees__"] = cache.get("__crees__", 0) + 1
			cache[ue_source] = nom
	return cache[ue_source]


@frappe.whitelist(methods=["POST"])
def dupliquer_grilles(annee_cible, annee_source, classes, copier_enseignants=1, copier_liaisons=1):
	"""Recopie les grilles des `classes` ([{filiere, niveau}]) de l'année source vers l'année cible."""
	_verifier_droits()
	if annee_source == annee_cible:
		frappe.throw(_("L'année source doit être différente de la nouvelle année."))
	for annee in (annee_source, annee_cible):
		if not frappe.db.exists("Academic Year", annee):
			frappe.throw(_("Année académique introuvable : {0}").format(annee))
	classes = frappe.parse_json(classes) if isinstance(classes, str) else (classes or [])
	choisies = {(c["filiere"], str(c["niveau"])) for c in classes}
	if not choisies:
		frappe.throw(_("Cochez au moins une classe."))
	copier_enseignants = frappe.utils.cint(copier_enseignants)

	par_cours = {}
	for ligne in _lignes_source(annee_source):
		if (ligne.filiere, str(ligne.niveau)) in choisies:
			par_cours.setdefault(ligne.teaching_unit, []).append(ligne)

	stats = {"cours_crees": 0, "cours_rattaches": 0, "classes_deja_presentes": 0, "ue_creees": 0, "liaisons": 0}
	cache_ue, correspondance = {}, {}
	for tu_source, lignes in sorted(par_cours.items()):
		src = frappe.get_doc("Teaching Unit", tu_source)
		existant = frappe.db.get_value("Teaching Unit", {"course": src.course, "academic_year": annee_cible}, "name")
		if existant:
			cible = frappe.get_doc("Teaching Unit", existant)
			presentes = {(r.filiere, str(r.niveau)) for r in cible.course_levels}
			ajouts = [l for l in lignes if (l.filiere, str(l.niveau)) not in presentes]
			stats["classes_deja_presentes"] += len(lignes) - len(ajouts)
			for l in ajouts:
				cible.append("course_levels", {"filiere": l.filiere, "niveau": l.niveau, "course_poid": l.course_poid})
			if ajouts:
				cible.save(ignore_permissions=True)
				stats["cours_rattaches"] += 1
		else:
			cible = frappe.get_doc({
				"doctype": "Teaching Unit",
				"course": src.course,
				"academic_year": annee_cible,
				"intitule_cours": src.intitule_cours,
				"unite_de_valeur": _ue_cible(src.unite_de_valeur, annee_cible, cache_ue),
				"semestre": src.semestre,
				"credits": src.credits,
				"type_ue": src.type_ue,
				"mode": src.mode,
				**{champ: src.get(champ) for champ in grille.CHAMPS_HEURES},
				"table_enseignant": [
					{"enseignant": t.enseignant, "type_de_cours": t.type_de_cours} for t in src.table_enseignant
				] if copier_enseignants else [],
				"course_levels": [
					{"filiere": l.filiere, "niveau": l.niveau, "course_poid": l.course_poid} for l in lignes
				],
			}).insert(ignore_permissions=True)
			stats["cours_crees"] += 1
		correspondance[tu_source] = cible.name

	if frappe.utils.cint(copier_liaisons) and frappe.get_meta("Teaching Unit").has_field("groupe_cours_commun"):
		groupes = {}
		for tu_source, tu_cible in correspondance.items():
			groupe = frappe.db.get_value("Teaching Unit", tu_source, "groupe_cours_commun")
			if groupe:
				groupes.setdefault(groupe, []).append(tu_cible)
		for membres in groupes.values():
			if len(membres) < 2:
				continue
			existants = {frappe.db.get_value("Teaching Unit", m, "groupe_cours_commun") for m in membres} - {None, ""}
			nouveau = sorted(existants)[0] if existants else f"GCC-{frappe.generate_hash(length=10).upper()}"
			for m in membres:
				frappe.db.set_value("Teaching Unit", m, "groupe_cours_commun", nouveau)
			stats["liaisons"] += 1

	stats["ue_creees"] = cache_ue.get("__crees__", 0)
	return stats
