"""Hooks de permission : périmètre par filière (agents de scolarité, doyens) sur les listes et documents.

Chaque DocType lié à une filière (champ direct) ou à un étudiant (filière de sa fiche) reçoit :
  - query_<doctype>   : condition SQL des listes, rapports et recherches ;
  - has_<doctype>     : contrôle d'un document.
Les règles déjà en place (un étudiant ne voit que ses propres documents, un coordonnateur ne
voit que les candidatures de ses filières) sont conservées et combinées (ET logique).
"""

import frappe

from udshed.utils import perimetre

# DocType -> (type de lien, champ(s))
REGLES = {
	"Student": ("filiere", "filiere"),
	"Inscription Academique": ("filiere", "filiere"),
	"Academic Reregistration": ("filiere", "filiere"),
	"Progression Academique": ("filieres", ("filiere_source", "filiere_cible")),
	"Session Inscription Candidate": ("filiere", "filiere"),
	"Session Examen Note": ("filiere", "filiere"),
	"Examen Anonymat": ("filiere", "filiere"),
	"Equivalence UE": ("filiere", "filiere"),
	"Deliberation Jury": ("filiere", "filiere"),
	"Jury Diplomation": ("filiere", "filiere"),
	"Diplome Etudiant": ("filiere", "filiere"),
	"Derogation Saisie": ("filiere", "filiere"),
	"Confirmation Saisie": ("filiere", "filiere"),
	"Resultat Academique": ("student", "student"),
	"Resultat UE": ("student", "student"),
	"Resultat Semestre": ("student", "student"),
	"Acte Academique": ("student", "student"),
	"Requete Etudiant": ("student", "student"),
	"Correction Note": ("student", "student"),
	"Echeance Etudiant": ("student", "student"),
	"Paiement Etudiant": ("student", "student"),
	"Appel Seance": ("filiere", "filiere"),
	"Stage Etudiant": ("filiere", "filiere"),
	"Soutenance": ("filiere", "filiere"),
}
# Règles existantes à conserver (hooks précédents).
EXISTANTS = {
	"Student": ("udshed.permissions.student_query", "udshed.permissions.student_has_permission"),
	"Inscription Academique": ("udshed.permissions.inscription_query", "udshed.permissions.inscription_has_permission"),
	"Resultat Academique": ("udshed.permissions.resultat_query", "udshed.permissions.resultat_has_permission"),
	"Session Inscription Candidate": ("udshed.permissions.candidature_query", "udshed.permissions.candidature_has_permission"),
	"Acte Academique": ("udshed.permissions.acte_query", "udshed.permissions.acte_has_permission"),
	"Diplome Etudiant": ("udshed.permissions.diplome_query", "udshed.permissions.diplome_has_permission"),
	"Requete Etudiant": ("udshed.permissions.requete_query", "udshed.permissions.requete_has_permission"),
	"Academic Reregistration": ("udshed.api.permission.academic_reregistration_query",
								"udshed.api.permission.academic_reregistration_has_permission"),
	"Progression Academique": ("udshed.api.permission.progression_query", "udshed.api.permission.progression_has_permission"),
}


def _slug(doctype):
	return doctype.lower().replace(" ", "_")


def _et(*conditions):
	parts = [c for c in conditions if c]
	return " and ".join(f"({c})" for c in parts)


def _condition(doctype, user):
	genre, champ = REGLES[doctype]
	if genre == "filiere":
		return perimetre.condition_sql(doctype, champ, user)
	if genre == "student":
		return perimetre.condition_sql_etudiant(doctype, champ, user)
	conds = [perimetre.condition_sql(doctype, c, user) for c in champ]
	conds = [c for c in conds if c]
	if not conds:
		return ""
	return "1=0" if all(c == "1=0" for c in conds) else " or ".join(f"({c})" for c in conds if c != "1=0")


def _filiere_du_document(doctype, doc):
	genre, champ = REGLES[doctype]
	if genre == "filiere":
		return [doc.get(champ)]
	if genre == "student":
		return [perimetre.filiere_etudiant(doc.get(champ))]
	return [doc.get(c) for c in champ]


def _query(doctype, user=None):
	user = user or frappe.session.user
	base = frappe.get_attr(EXISTANTS[doctype][0])(user) if doctype in EXISTANTS else ""
	return _et(base, _condition(doctype, user))


def _has(doctype, doc, ptype=None, user=None):
	user = user or frappe.session.user
	if doctype in EXISTANTS:
		ok = frappe.get_attr(EXISTANTS[doctype][1])(doc, ptype=ptype, user=user)
		if ok is False:
			return False
	if not perimetre.restreint(user):
		return True
	filieres = [f for f in _filiere_du_document(doctype, doc) if f]
	if not filieres:
		return ptype == "create"  # nouveau document sans filière encore renseignée
	return any(perimetre.autorisee(f, user) for f in filieres)


def _fabriquer(doctype):
	def query(user=None):
		return _query(doctype, user)

	def has(doc, ptype=None, user=None, debug=False):
		return _has(doctype, doc, ptype, user)

	return query, has


for _dt in REGLES:
	globals()[f"query_{_slug(_dt)}"], globals()[f"has_{_slug(_dt)}"] = _fabriquer(_dt)


def query_periode_saisie_notes(user=None):
	"""Doyen / vice-doyen : périodes de l'établissement et de ses facultés."""
	user = user or frappe.session.user
	if not perimetre.restreint(user):
		return ""
	facs = perimetre.facultes_dirigees(user)
	liste = ", ".join(frappe.db.escape(f) for f in facs)
	cond = "ifnull(`tabPeriode Saisie Notes`.`faculte`, '') = ''"
	return f"{cond} or `tabPeriode Saisie Notes`.`faculte` in ({liste})" if facs else cond


def hooks():
	"""Valeurs des hooks permission_query_conditions et has_permission (voir hooks.py)."""
	q = {dt: f"udshed.perimetre_hooks.query_{_slug(dt)}" for dt in REGLES}
	q["Periode Saisie Notes"] = "udshed.perimetre_hooks.query_periode_saisie_notes"
	h = {dt: f"udshed.perimetre_hooks.has_{_slug(dt)}" for dt in REGLES}
	return q, h
