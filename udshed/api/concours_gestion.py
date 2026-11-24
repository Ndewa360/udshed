# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Page « Gestion des concours » : tout le déroulé d'un concours sur une seule page,
étape par étape (candidats, notes, délibération, résultats, admissions).

Ce module lit et agrège ; les règles métier restent dans concours, concours_resultats,
concours_deliberation et concours_finalisation, qu'il appelle.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today

from udshed.api.concours import STATUT_DESISTE, STATUT_LISTE_ATTENTE
from udshed.api.concours_deliberation import ADMIS, ATTENTE, _lignes, _problemes, _resume
from udshed.api.concours_resultats import _est_scolarite, _exiger_scolarite, etat_saisie
from udshed.udshed.doctype.concours.concours import STATUTS

# Passages de statut proposés par la page ; les autres sont automatiques
# (levée de l'anonymat -> Délibération, publication -> Résultats publiés).
TRANSITIONS = {
	"Brouillon": "Candidatures ouvertes",
	"Candidatures ouvertes": "Épreuves",
	"Résultats publiés": "Clôturé",
}


@frappe.whitelist()
def liste_concours():
	frappe.has_permission("Concours", "read", throw=True)
	return frappe.get_all("Concours", fields=["name", "titre", "statut", "academic_year"],
						  order_by="creation desc")


def _libelle_filiere(filiere):
	return frappe.db.get_value("Field of study", filiere, "name_of_field") or filiere


def _niveau(niveau):
	return frappe.db.get_value("Field of study Level", niveau, "level") or niveau


def _etat_admission(statut, finaliser_avant):
	"""Situation d'un admis : clé + libellé lisible."""
	if statut == "Inscrit":
		return "inscrit", _("Inscrit")
	if statut == STATUT_DESISTE:
		return "desiste", _("Désisté")
	if statut == STATUT_LISTE_ATTENTE:
		return "attente", _("Liste d'attente")
	if statut == "Accepté":
		if not finaliser_avant:
			return "a_confirmer", _("À confirmer")
		reste = date_diff(finaliser_avant, today())
		if reste < 0:
			return "depasse", _("Délai dépassé")
		return "a_confirmer", _("À confirmer — J-{0}").format(reste) if reste else _("À confirmer — aujourd'hui")
	return "autre", statut or ""


@frappe.whitelist()
def tableau(concours):
	frappe.has_permission("Concours", "read", concours, throw=True)
	doc = frappe.get_doc("Concours", concours)
	etape = STATUTS.index(doc.statut)
	scolarite = _est_scolarite()

	fiches = frappe.get_all(
		"Candidat Concours", {"concours": concours},
		["name", "candidature", "nom_complet", "centre_examen", "numero_table", "decision",
		 "filiere_admise", "niveau_admis", "motif_desistement"],
		order_by="numero_table asc",
	)
	cands = {c.name: c for c in frappe.get_all(
		"Session Inscription Candidate", {"name": ["in", [f.candidature for f in fiches] or [""]]},
		["name", "candidature_status", "finaliser_avant", "email", "phone", "birthdate", "status_comment"],
	)}
	choix = {}
	for c in frappe.get_all("ChildTable Choise Formation Inscription Candidat",
							{"parenttype": "Session Inscription Candidate", "parent": ["in", list(cands) or [""]]},
							["parent", "choix", "filiere", "niveau"], order_by="idx asc"):
		choix.setdefault(c.parent, []).append(f"{c.filiere} ({_niveau(c.niveau)})")

	lignes = _lignes(concours) if doc.anonymat_leve else []
	par_fiche = {}
	for l in lignes:
		par_fiche.setdefault(l.parent, []).append(l)

	candidats = []
	for f in fiches:
		c = cands.get(f.candidature) or frappe._dict()
		cle, etat = _etat_admission(c.candidature_status, c.finaliser_avant)
		rangs = [
			{"filiere": l.filiere, "niveau": _niveau(l.niveau), "choix": l.choix, "moyenne": l.moyenne,
			 "rang": l.rang, "decision": l.decision, "proposition": l.proposition}
			for l in sorted(par_fiche.get(f.name, []), key=lambda x: x.ordre)
		]
		candidats.append({
			**f, "statut_candidature": c.candidature_status, "finaliser_avant": c.finaliser_avant,
			"email": c.email, "phone": c.phone, "observation": c.status_comment,
			"choix": choix.get(f.candidature, []), "resultats": rangs,
			"etat_admission": cle, "etat_admission_libelle": etat,
			"filiere_admise_libelle": _libelle_filiere(f.filiere_admise) if f.filiere_admise else "",
			"niveau_admis_libelle": _niveau(f.niveau_admis) if f.niveau_admis else "",
		})

	formations = [{
		"filiere": r.filiere, "filiere_libelle": _libelle_filiere(r.filiere), "niveau": r.niveau,
		"niveau_libelle": _niveau(r.niveau), "places": r.places,
	} for r in doc.filieres]

	res = {
		"concours": {
			"name": doc.name, "titre": doc.titre, "statut": doc.statut, "academic_year": doc.academic_year,
			"anonymat_leve": doc.anonymat_leve, "classement_calcule_le": doc.classement_calcule_le,
			"delai_finalisation": doc.delai_finalisation, "president_jury": doc.president_jury,
			"membres_jury": doc.membres_jury, "observations_jury": doc.observations_jury,
			"date_deliberation": doc.date_deliberation, "resultats_publies_le": doc.resultats_publies_le,
			"date_debut_epreuves": doc.date_debut_epreuves, "date_fin_epreuves": doc.date_fin_epreuves,
			"session_inscription": doc.session_inscription,
			"session_ouverte": frappe.db.get_value("Session Inscription", doc.session_inscription, "status") == "Open",
		},
		"etapes": STATUTS, "etape": etape, "statut_suivant": TRANSITIONS.get(doc.statut),
		"scolarite": scolarite, "formations": formations, "candidats": candidats,
		"saisie": etat_saisie(concours) if etape >= STATUTS.index("Épreuves") else [],
		"resultats": [{
			"name": l.name, "fiche": l.parent, "nom_complet": l.nom_complet, "numero_table": l.numero_table,
			"filiere": l.filiere, "niveau": l.niveau, "choix": l.choix, "moyenne": l.moyenne, "rang": l.rang,
			"elimine": l.elimine, "motif": l.motif, "proposition": l.proposition, "ex_aequo": l.ex_aequo,
			"decision": l.decision,
		} for l in sorted(lignes, key=lambda x: (x.filiere, str(x.niveau), x.rang or 9999, x.nom_complet or ""))],
		"resume": _resume(doc, lignes) if lignes else [],
		"problemes": _problemes(doc, lignes) if doc.statut == "Délibération" and lignes else [],
	}
	admis = [c for c in candidats if c["etat_admission"] in ("inscrit", "a_confirmer", "depasse", "desiste")
			 and doc.statut in ("Résultats publiés", "Clôturé")]
	res["kpis"] = {
		"candidats": len(candidats),
		"places": sum(r.places or 0 for r in doc.filieres),
		"admis": sum(1 for c in candidats if c["decision"] == ADMIS),
		"attente": sum(1 for c in candidats if c["decision"] == ATTENTE),
		"inscrits": sum(1 for c in admis if c["etat_admission"] == "inscrit"),
		"a_confirmer": sum(1 for c in admis if c["etat_admission"] == "a_confirmer"),
		"depasse": sum(1 for c in admis if c["etat_admission"] == "depasse"),
		"desistes": sum(1 for c in admis if c["etat_admission"] == "desiste"),
	}
	return res


# --------------------------------------------------------------------------- #
#  Actions
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def changer_statut(concours, statut):
	_exiger_scolarite()
	doc = frappe.get_doc("Concours", concours)
	if TRANSITIONS.get(doc.statut) != statut:
		frappe.throw(_("Passage de « {0} » à « {1} » non proposé ici.").format(doc.statut, statut))
	if statut == "Clôturé":
		en_attente = frappe.db.count("Session Inscription Candidate",
									 {"concours": concours, "candidature_status": "Accepté"})
		if en_attente:
			frappe.throw(_("{0} admis n'ont pas encore confirmé leur place : attendez la fin de leur délai "
						   "ou enregistrez leur désistement avant de clôturer.").format(en_attente))
	doc.statut = statut
	doc.save()
	return doc.statut


@frappe.whitelist()
def definir_decision(resultat, decision):
	"""Décision du jury sur une ligne de résultat (choix d'un candidat)."""
	_exiger_scolarite()
	parent = frappe.db.get_value("Candidat Concours Resultat", resultat, "parent")
	if not parent:
		frappe.throw(_("Ligne de résultat introuvable."))
	fiche = frappe.get_doc("Candidat Concours", parent)
	ligne = next(r for r in fiche.resultats if r.name == resultat)
	ligne.decision = decision or ""
	fiche.save()  # contrôles du jury : statut Délibération, éliminé, admission unique
	return decision


@frappe.whitelist()
def enregistrer_jury(concours, president_jury=None, membres_jury=None, observations_jury=None,
					 date_deliberation=None):
	_exiger_scolarite()
	doc = frappe.get_doc("Concours", concours)
	doc.update({"president_jury": president_jury, "membres_jury": membres_jury,
				"observations_jury": observations_jury, "date_deliberation": date_deliberation or None})
	doc.save()
	return True


@frappe.whitelist()
def prolonger_delai(candidature, date):
	_exiger_scolarite()
	cand = frappe.get_doc("Session Inscription Candidate", candidature)
	if cand.candidature_status != "Accepté":
		frappe.throw(_("Seul le délai d'un admis qui n'a pas encore confirmé peut être modifié."))
	if getdate(date) < getdate(today()):
		frappe.throw(_("La nouvelle date limite ne peut pas être dans le passé."))
	cand.db_set("finaliser_avant", getdate(date))
	cand.add_comment("Info", _("Délai de finalisation reporté au {0}.").format(frappe.utils.format_date(date)))
	return True

