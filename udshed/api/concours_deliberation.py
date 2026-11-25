# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Concours d'entrée — phase 4 : délibération du jury, publication des résultats,
désistements et appel de la liste d'attente.

Déroulé :
  1. « Appliquer les propositions » recopie le classement calculé (phase 3) dans
	 la décision du jury ; les ex æquo restent à trancher à la main.
  2. Le jury ajuste les décisions dans les fiches Candidat Concours.
  3. « Contrôler la délibération » liste ce qui bloque la publication.
  4. « Publier les résultats » fixe les décisions et met à jour les candidatures :
	 Admis -> « Accepté » (e-mail, puis finalisation de l'inscription par le candidat),
	 Liste d'attente -> « Liste d'attente » (e-mail avec le rang),
	 Non admis -> « Refusé » (e-mail), ou réexamen sur dossier s'il reste un choix hors concours.
  5. Après publication : un désistement libère la place, qui est proposée au
	 premier de la liste d'attente (en cascade si celui-ci quitte un autre choix).
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, today

from udshed.api.concours import STATUT_DESISTE, STATUT_LISTE_ATTENTE
from udshed.api.concours_resultats import ORDRE_CHOIX, _exiger_scolarite

ADMIS, ATTENTE, NON_ADMIS = "Admis", "Liste d'attente", "Non admis"


# --------------------------------------------------------------------------- #
#  Lecture
# --------------------------------------------------------------------------- #
def _formations(doc):
	return {(r.filiere, str(r.niveau)): r for r in doc.filieres}


def _lignes(concours):
	"""Lignes de résultat du concours, avec le candidat."""
	fiches = {f.name: f for f in frappe.get_all(
		"Candidat Concours", {"concours": concours},
		["name", "candidature", "numero_table", "nom_complet", "decision"])}
	if not fiches:
		return []
	lignes = frappe.get_all(
		"Candidat Concours Resultat",
		{"parenttype": "Candidat Concours", "parent": ["in", list(fiches)]},
		["name", "parent", "choix", "filiere", "niveau", "moyenne", "rang", "elimine", "motif",
		 "proposition", "ex_aequo", "decision"],
	)
	for l in lignes:
		f = fiches[l.parent]
		l.update({"candidature": f.candidature, "numero_table": f.numero_table, "nom_complet": f.nom_complet,
				  "formation": (l.filiere, str(l.niveau)), "ordre": ORDRE_CHOIX.get(l.choix, 9)})
	return lignes


def _libelle(l):
	return f"{l.nom_complet} ({l.numero_table}) — {l.filiere}"


# --------------------------------------------------------------------------- #
#  1. Propositions -> décisions
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def appliquer_propositions(concours, ecraser=0):
	"""Recopie les propositions du classement dans la décision du jury.
	Les ex æquo ne sont pas tranchés automatiquement."""
	_exiger_scolarite()
	doc = frappe.get_doc("Concours", concours)
	if doc.statut != "Délibération" or not doc.classement_calcule_le:
		frappe.throw(_("Calculez d'abord le classement, au statut « Délibération »."))
	ecraser = frappe.utils.cint(ecraser)
	appliquees = ex_aequo = 0
	for l in _lignes(concours):
		if l.ex_aequo:
			ex_aequo += 1
			if ecraser:
				frappe.db.set_value("Candidat Concours Resultat", l.name, "decision", "")
			continue
		if l.decision and not ecraser:
			continue
		frappe.db.set_value("Candidat Concours Resultat", l.name, "decision", l.proposition or "")
		appliquees += 1
	return {"appliquees": appliquees, "ex_aequo": ex_aequo}


# --------------------------------------------------------------------------- #
#  2. Contrôle
# --------------------------------------------------------------------------- #
def _problemes(doc, lignes):
	problemes = []
	par_fiche = {}
	for l in lignes:
		par_fiche.setdefault(l.parent, []).append(l)
	for fiche, ls in par_fiche.items():
		admis = [l for l in ls if l.decision == ADMIS]
		if len(admis) > 1:
			problemes.append(_("{0} est admis dans plusieurs formations.").format(ls[0].nom_complet))
		for l in ls:
			if l.decision == ADMIS and l.elimine:
				problemes.append(_("{0} est admis alors qu'il est éliminé ({1}).").format(_libelle(l), l.motif))
			if l.decision == STATUT_DESISTE:
				problemes.append(_("{0} : « Désisté » ne s'utilise qu'après la publication.").format(_libelle(l)))
			if not l.decision and not admis:
				problemes.append(_("{0} : décision du jury manquante{1}.").format(
					_libelle(l), _(" (ex æquo à départager)") if l.ex_aequo else ""))
			if l.decision == ATTENTE and admis and admis[0].ordre < l.ordre:
				problemes.append(_("{0} : en liste d'attente sur un choix moins prioritaire que son admission.")
								 .format(_libelle(l)))
	for cle, conf in _formations(doc).items():
		n = sum(1 for l in lignes if l.formation == cle and l.decision == ADMIS)
		if n > (conf.places or 0):
			problemes.append(_("{0} : {1} admis pour {2} place(s).").format(conf.filiere, n, conf.places))
	return problemes


def _resume(doc, lignes):
	resume = []
	for cle, conf in _formations(doc).items():
		ls = [l for l in lignes if l.formation == cle]
		resume.append({
			"filiere": conf.filiere, "places": conf.places, "candidats": len(ls),
			"admis": sum(1 for l in ls if l.decision == ADMIS),
			"attente": sum(1 for l in ls if l.decision == ATTENTE),
			"non_admis": sum(1 for l in ls if l.decision == NON_ADMIS),
			"desistes": sum(1 for l in ls if l.decision == STATUT_DESISTE),
			"sans_decision": sum(1 for l in ls if not l.decision),
		})
	return resume


@frappe.whitelist()
def controler_deliberation(concours):
	_exiger_scolarite()
	doc = frappe.get_doc("Concours", concours)
	lignes = _lignes(concours)
	return {"problemes": _problemes(doc, lignes), "resume": _resume(doc, lignes)}


# --------------------------------------------------------------------------- #
#  3. Publication
# --------------------------------------------------------------------------- #
def _changer_statut(candidature, statut, commentaire=None, filiere=None, niveau=None):
	"""Change le statut d'une candidature au nom du jury (déclenche les e-mails)."""
	cand = frappe.get_doc("Session Inscription Candidate", candidature)
	if filiere:
		cand.filiere = filiere
		cand.niveau = frappe.db.get_value("Field of study Level", niveau, "level") or niveau
	cand.candidature_status = statut
	if commentaire:
		cand.status_comment = commentaire
	# Une pièce manquante dans le dossier ne doit pas bloquer la publication des résultats.
	cand.flags.ignore_mandatory = True
	frappe.flags.admission_par_jury = True
	try:
		cand.save(ignore_permissions=True)
	finally:
		frappe.flags.admission_par_jury = False
	return cand


@frappe.whitelist()
def publier_resultats(concours):
	_exiger_scolarite()
	doc = frappe.get_doc("Concours", concours)
	if doc.statut != "Délibération":
		frappe.throw(_("Les résultats se publient au statut « Délibération »."))
	lignes = _lignes(concours)
	if not lignes:
		frappe.throw(_("Aucun résultat à publier."))
	problemes = _problemes(doc, lignes)
	if problemes:
		frappe.throw(_("La délibération n'est pas complète :") + "<br>• " + "<br>• ".join(problemes[:20]))

	formations = _formations(doc)
	par_fiche = {}
	for l in lignes:
		par_fiche.setdefault(l.parent, []).append(l)
	bilan = {ADMIS: 0, ATTENTE: 0, NON_ADMIS: 0, "Absent": 0, "Dossier": 0}
	for fiche_name, ls in par_fiche.items():
		fiche = frappe.get_doc("Candidat Concours", fiche_name)
		admis = next((l for l in ls if l.decision == ADMIS), None)
		if admis:
			fiche.db_set({"decision": ADMIS, "filiere_admise": admis.filiere, "niveau_admis": admis.niveau})
			_changer_statut(fiche.candidature, "Accepté", filiere=admis.filiere, niveau=admis.niveau)
			bilan[ADMIS] += 1
			continue
		if any(l.decision == ATTENTE for l in ls):
			fiche.db_set("decision", ATTENTE)
			_changer_statut(fiche.candidature, STATUT_LISTE_ATTENTE)
			bilan[ATTENTE] += 1
			continue
		absent = fiche.notes and all(n.absent for n in fiche.notes)
		fiche.db_set("decision", "Absent" if absent else NON_ADMIS)
		cand = frappe.get_doc("Session Inscription Candidate", fiche.candidature)
		hors_concours = [c for c in cand.choix_de_formation if (c.filiere, str(c.niveau)) not in formations]
		if hors_concours:
			# Il reste un choix sur dossier : la scolarité l'examine (acceptation manuelle permise).
			c = hors_concours[0]
			_changer_statut(
				cand.name, "Dossier en cours d'examen", filiere=c.filiere, niveau=c.niveau,
				commentaire=_("Non admis au concours « {0} ». Reste à examiner sur dossier : {1}.")
				.format(doc.titre, ", ".join(f"{x.filiere} ({x.choix})" for x in hors_concours)),
			)
			bilan["Dossier"] += 1
		else:
			modele = (_("Absent aux épreuves du concours « {0} ».") if absent
					  else _("Non admis à l'issue de la délibération du jury du concours « {0} »."))
			_changer_statut(cand.name, "Refusé", commentaire=modele.format(doc.titre))
			bilan["Absent" if absent else NON_ADMIS] += 1

	doc.reload()
	doc.statut = "Résultats publiés"
	doc.date_publication_resultats = today()
	doc.date_deliberation = doc.date_deliberation or today()
	doc.resultats_publies_le = now_datetime()
	doc.save()
	return bilan


# --------------------------------------------------------------------------- #
#  4. Désistement et liste d'attente
# --------------------------------------------------------------------------- #
def _exiger_publie(doc):
	if doc.statut != "Résultats publiés":
		frappe.throw(_("Action possible uniquement quand les résultats sont publiés."))


def _completer(doc, formations_a_traiter):
	"""Propose les places libres aux suivants de la liste d'attente, en cascade."""
	promus = []
	confs = _formations(doc)
	file = list(formations_a_traiter)
	while file:
		cle = file.pop(0)
		conf = confs[cle]
		while True:
			lignes = _lignes(doc.name)
			admis = sum(1 for l in lignes if l.formation == cle and l.decision == ADMIS)
			if admis >= (conf.places or 0):
				break
			statuts = dict(frappe.get_all("Session Inscription Candidate",
										  {"name": ["in", list({l.candidature for l in lignes})]},
										  ["name", "candidature_status"], as_list=True))
			attente = sorted(
				[l for l in lignes if l.formation == cle and l.decision == ATTENTE
				 and statuts.get(l.candidature) in (STATUT_LISTE_ATTENTE, "Accepté")],
				key=lambda l: (l.rang or 9999, -(l.moyenne or 0), l.numero_table or ""),
			)
			if not attente:
				break
			promu = attente[0]
			ancienne = next((l for l in lignes if l.parent == promu.parent and l.decision == ADMIS), None)
			frappe.db.set_value("Candidat Concours Resultat", promu.name, "decision", ADMIS)
			# Les autres vœux moins prioritaires de ce candidat n'ont plus lieu d'être.
			for l in lignes:
				if l.parent == promu.parent and l.name != promu.name and l.ordre > promu.ordre \
						and l.decision in (ADMIS, ATTENTE):
					frappe.db.set_value("Candidat Concours Resultat", l.name,
										{"decision": "", "motif": _("Admis sur un choix prioritaire")})
			frappe.db.set_value("Candidat Concours", promu.parent,
								{"decision": ADMIS, "filiere_admise": promu.filiere, "niveau_admis": promu.niveau})
			if statuts.get(promu.candidature) == "Accepté":
				# Déjà admis sur un choix moins prioritaire : il change de formation.
				from udshed.udshed.doctype.session_inscription_candidate.session_inscription_candidate import (
					_send_confirmation_email,
				)
				from udshed.api.concours_finalisation import echeance_finalisation

				niveau = frappe.db.get_value("Field of study Level", promu.niveau, "level") or promu.niveau
				# Nouvelle offre : nouveau délai pour finaliser.
				frappe.db.set_value("Session Inscription Candidate", promu.candidature,
									{"filiere": promu.filiere, "niveau": niveau,
									 "finaliser_avant": echeance_finalisation(promu.candidature)})
				_send_confirmation_email(frappe.get_doc("Session Inscription Candidate", promu.candidature))
				if ancienne:
					file.append(ancienne.formation)  # sa place précédente se libère
			else:
				_changer_statut(promu.candidature, "Accepté", filiere=promu.filiere, niveau=promu.niveau)
			promus.append({"candidat": promu.nom_complet, "numero_table": promu.numero_table,
						   "filiere": promu.filiere, "rang": promu.rang})
	return promus


@frappe.whitelist()
def enregistrer_desistement(concours, candidat_concours, motif):
	_exiger_scolarite()
	doc = frappe.get_doc("Concours", concours)
	_exiger_publie(doc)
	if not (motif or "").strip():
		frappe.throw(_("Indiquez le motif du désistement."))
	fiche = frappe.get_doc("Candidat Concours", candidat_concours)
	if fiche.concours != concours:
		frappe.throw(_("Ce candidat n'appartient pas à ce concours."))
	return _desister(doc, fiche, motif)


def _desister(doc, fiche, motif):
	"""Désistement d'un admis (sa place est reproposée) ou d'un inscrit sur liste d'attente
	(il sort de la liste). Sans contrôle de rôle : appelé par la scolarité, par le candidat
	lui-même depuis le portail, ou par la tâche planifiée d'expiration du délai."""
	motif = (motif or "").strip()
	if fiche.decision not in (ADMIS, ATTENTE):
		frappe.throw(_("Seul un candidat admis ou sur liste d'attente peut se désister."))
	statut = frappe.db.get_value("Session Inscription Candidate", fiche.candidature, "candidature_status")
	if statut not in ("Accepté", STATUT_LISTE_ATTENTE):
		frappe.throw(_("La candidature est au statut « {0} » : le désistement n'est possible que pour un "
					   "admis qui n'a pas encore finalisé son inscription.").format(statut))
	admis = next((r for r in fiche.resultats if r.decision == ADMIS), None)
	for r in fiche.resultats:
		if r.decision in (ADMIS, ATTENTE):
			frappe.db.set_value("Candidat Concours Resultat", r.name, "decision", STATUT_DESISTE)
	fiche.db_set({"decision": STATUT_DESISTE, "motif_desistement": motif})
	_changer_statut(fiche.candidature, STATUT_DESISTE, commentaire=_("Désistement : {0}").format(motif))
	if not admis:
		return {"promus": []}
	return {"promus": _completer(doc, [(admis.filiere, str(admis.niveau))])}


@frappe.whitelist()
def completer_liste_attente(concours):
	"""Pourvoit toutes les places libres (après un désistement ou une hausse des places)."""
	_exiger_scolarite()
	doc = frappe.get_doc("Concours", concours)
	_exiger_publie(doc)
	return {"promus": _completer(doc, list(_formations(doc)))}


# --------------------------------------------------------------------------- #
#  5. PV de délibération
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def telecharger_pv_deliberation(concours, filiere=None):
	from udshed.api.concours_resultats import _pdf_pv

	_exiger_scolarite()
	doc = frappe.get_doc("Concours", concours)
	if doc.statut not in ("Délibération", "Résultats publiés", "Clôturé") or not doc.classement_calcule_le:
		frappe.throw(_("Le PV de délibération est disponible après le calcul du classement."))
	_pdf_pv(doc, filiere, final=True)
