"""Délibération du jury de fin d'année (DocType « Deliberation Jury »).

Le jury ne modifie JAMAIS une note. Il ajuste la VALIDATION :
  - points de jury : bonus au plus égal à `points_jury_max` (sur 20) ajouté
	à la moyenne d'une unité pour atteindre le seuil ;
  - seuil abaissé : unité validée à partir de `seuil_abaisse` (sur 20) ;
  - décision individuelle motivée : validation d'une unité (ou d'une matière
	hors unité) ou admission au niveau supérieur pour un étudiant ;
  - passage conditionnel : `pourcentage_credits_min` / `dette_max_credits`
	remplacent 50 % / 30 crédits dans la règle de passage standard.

Seule une délibération « Appliquée » produit des effets. Les ajustements sont
recalculés à chaque calcul d'unité (ils survivent donc à une nouvelle saisie
de notes) et chaque unité validée par le jury en garde la trace.
"""

import frappe

from udshed.utils.etablissement import nom_etudiant
from frappe import _
from frappe.utils import flt, now_datetime

DOCTYPE = "Deliberation Jury"
VALIDATION_UNITE = "Validation d'unité"
ADMISSION = "Admission au niveau supérieur"


def _niveau_id(filiere, niveau):
	if not niveau:
		return None
	if frappe.db.exists("Field of study Level", niveau):
		return niveau
	return frappe.db.get_value("Field of study Level", {"parent": filiere, "level": niveau}, "name")


def deliberation_appliquee(academic_year, filiere, niveau):
	"""Délibération appliquée d'une classe (filière + niveau, nom ou libellé), sinon None."""
	niveau_id = _niveau_id(filiere, niveau)
	if not (academic_year and filiere and niveau_id):
		return None
	force = getattr(frappe.local, "udshed_delib_force", None)
	if force and (force.academic_year, force.filiere, force.niveau) == (academic_year, filiere, niveau_id):
		return force  # simulation d'un brouillon
	cle = ("udshed_delib", academic_year, filiere, niveau_id)
	cache = getattr(frappe.local, "udshed_delib_cache", None)
	if cache is None:
		cache = frappe.local.udshed_delib_cache = {}
	if cle not in cache:
		nom = frappe.db.get_value(DOCTYPE, {"academic_year": academic_year, "filiere": filiere,
											"niveau": niveau_id, "statut": "Appliquée"}, "name")
		cache[cle] = frappe.get_doc(DOCTYPE, nom) if nom else None
	return cache[cle]


def vider_cache():
	frappe.local.udshed_delib_cache = {}


def ajuster_validation(student, note_pct, seuil_pct, academic_year, filiere, niveau, unite=None, matiere=None):
	"""Validation d'une unité (ou d'une matière hors unité) après délibération.

	Args:
		note_pct: moyenne en % (None si incalculable) ; seuil_pct: seuil normal en %.
	Returns:
		dict: valide (bool), par_jury (bool), points (sur 20), motif, deliberation
	"""
	brut = note_pct is not None and flt(note_pct) >= flt(seuil_pct)
	res = {"valide": brut, "par_jury": False, "points": 0.0, "motif": "", "deliberation": None}
	if brut:
		return res
	delib = deliberation_appliquee(academic_year, filiere, niveau)
	if not delib:
		return res
	res["deliberation"] = delib.name

	for d in delib.decisions or []:
		if d.student == student and d.type_decision == VALIDATION_UNITE and (
			(unite and d.unite == unite) or (matiere and d.matiere == matiere)
		):
			res.update(valide=True, par_jury=True, motif=_("Décision du jury : {0}").format(d.motif))
			return res

	if note_pct is None:
		return res
	note_20 = flt(note_pct) / 5
	if delib.seuil_abaisse and note_20 >= flt(delib.seuil_abaisse):
		res.update(valide=True, par_jury=True,
				   motif=_("Validée par le jury (seuil abaissé à {0}/20)").format(flt(delib.seuil_abaisse)))
		return res
	if delib.points_jury_max:
		manque = round(flt(seuil_pct) / 5 - note_20, 2)
		if 0 < manque <= flt(delib.points_jury_max):
			res.update(valide=True, par_jury=True, points=manque,
					   motif=_("Validée par le jury (+{0} point(s) de jury)").format(manque))
	return res


def regle_de_passage(student, filiere, niveau_precedent, academic_year):
	"""Règle de passage pour un étudiant : (pourcentage minimum, dette maximale,
	admission individuelle motivée ou None)."""
	pct, dette, admission = 50, 30, None
	delib = deliberation_appliquee(academic_year, filiere, niveau_precedent)
	if delib:
		if delib.pourcentage_credits_min:
			pct = flt(delib.pourcentage_credits_min)
		if delib.dette_max_credits:
			dette = int(delib.dette_max_credits)
		for d in delib.decisions or []:
			if d.student == student and d.type_decision == ADMISSION:
				admission = d.motif
	return pct, dette, admission


# ---------------------------------------------------------------------- #
#  Simulation et application
# ---------------------------------------------------------------------- #
def _etudiants_classe(delib):
	label = frappe.db.get_value("Field of study Level", delib.niveau, "level")
	return sorted(set(frappe.get_all(
		"Academic Reregistration",
		filters={"academic_year": delib.academic_year, "filiere": delib.filiere, "niveau": label, "statut": "Validée"},
		pluck="student",
	)))


def _unites_classe(delib):
	from udshed.utils.acquis import unites_du_niveau

	return [u for u in unites_du_niveau(delib.filiere, delib.niveau, delib.academic_year) if u["unite"]]


def simuler(delib):
	"""Effet de la délibération, sans rien écrire : unités repêchées par étudiant
	et évolution de la décision de passage."""
	from udshed.api.reregistration import _admission_decision
	from udshed.api.resultat_ue import calculer_ue_etudiant
	from udshed.utils.niveaux import prochain_niveau

	label = frappe.db.get_value("Field of study Level", delib.niveau, "level")
	etudiants = _etudiants_classe(delib)
	unites = _unites_classe(delib)
	cible = prochain_niveau(delib.filiere, label)

	vider_cache()
	frappe.local.udshed_delib_force = delib  # la simulation applique le brouillon
	lignes = []
	try:
		for student in etudiants:
			repechees = []
			for u in unites:
				r = calculer_ue_etudiant(student, u["unite"], delib.academic_year, u["semestre"],
										 delib.filiere, delib.niveau)
				if r and r.get("valide_par_jury"):
					repechees.append({"unite": u["unite"], "intitule": u["intitule"],
									  "note_20": r.get("note_ue_20"), "motif": r.get("motif_jury")})
			passage = _admission_decision(student, delib.filiere, label, cible, delib.academic_year) if cible else {}
			lignes.append({
				"student": student,
				"nom": nom_etudiant(student),
				"unites_repechees": repechees,
				"decision": passage.get("decision"),
				"motif": passage.get("motif"),
				"credits": "{0}/{1}".format(passage.get("credits_validated", 0), passage.get("total_credits", 0))
				if passage else "",
			})
	finally:
		frappe.local.udshed_delib_force = None
		vider_cache()
	return {"etudiants": lignes, "niveau_suivant": cible}


def appliquer(delib):
	"""Applique la délibération : statut « Appliquée », unités recalculées et
	progression des étudiants de la classe recalculée."""
	from udshed.api.progression import calculer_progression
	from udshed.api.resultat_ue import calculer_resultat_ue

	autre = frappe.db.get_value(DOCTYPE, {"academic_year": delib.academic_year, "filiere": delib.filiere,
										  "niveau": delib.niveau, "statut": "Appliquée",
										  "name": ["!=", delib.name]}, "name")
	if autre:
		frappe.throw(_("La délibération {0} est déjà appliquée pour cette classe : annulez-la d'abord.").format(autre))
	delib.db_set({"statut": "Appliquée", "appliquee_le": now_datetime(), "appliquee_par": frappe.session.user})
	vider_cache()
	return _recalculer_classe(delib, calculer_resultat_ue, calculer_progression)


def annuler(delib):
	from udshed.api.progression import calculer_progression
	from udshed.api.resultat_ue import calculer_resultat_ue

	delib.db_set({"statut": "Brouillon", "appliquee_le": None, "appliquee_par": None})
	vider_cache()
	return _recalculer_classe(delib, calculer_resultat_ue, calculer_progression)


def _recalculer_classe(delib, calculer_resultat_ue, calculer_progression):
	etudiants = _etudiants_classe(delib)
	unites = _unites_classe(delib)
	par_jury = 0
	for student in etudiants:
		for u in unites:
			doc = calculer_resultat_ue(student, u["unite"], delib.academic_year, u["semestre"],
									   delib.filiere, delib.niveau)
			if doc and doc.get("valide_par_jury"):
				par_jury += 1
		calculer_progression(student, delib.academic_year)
	bilan = _("{0} étudiant(s), {1} unité(s) validée(s) par le jury.").format(len(etudiants), par_jury)
	delib.db_set("bilan", bilan)
	return {"etudiants": len(etudiants), "unites_jury": par_jury, "bilan": bilan}
