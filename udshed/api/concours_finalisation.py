# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Admission — phase 5 : un admis n'est pas encore un étudiant.

« Accepté » est une offre de place. Le candidat :
  - la confirme en finalisant son inscription sur le portail (/inscription) :
	c'est le seul moment où sont créés le matricule, la fiche Student et
	l'Inscription Académique, et où la candidature passe à « Inscrit » ;
  - ou la décline (lui-même sur le portail, ou la scolarité pour lui) : « Désisté » ;
  - ou ne fait rien : à l'échéance (champ `finaliser_avant`), la tâche quotidienne
	le passe à « Désisté ».
Pour un admis au concours, chaque désistement repropose la place au suivant de la
liste d'attente (voir concours_deliberation._completer).
"""

import frappe
from frappe import _
from frappe.utils import add_days, format_date, getdate, today

from udshed.api.concours import STATUT_DESISTE, STATUT_LISTE_ATTENTE
from udshed.api.concours_resultats import _exiger_scolarite

DELAI_PAR_DEFAUT = 15  # jours, pour une admission sur dossier ou un concours sans délai saisi
JOURS_AVANT_RELANCE = 3


# --------------------------------------------------------------------------- #
#  Délai
# --------------------------------------------------------------------------- #
def delai_finalisation(candidature):
	"""Délai (jours) applicable à une candidature (nom ou document)."""
	concours = (frappe.db.get_value("Session Inscription Candidate", candidature, "concours")
				if isinstance(candidature, str) else candidature.get("concours"))
	if concours:
		delai = frappe.db.get_value("Concours", concours, "delai_finalisation")
		if delai:
			return int(delai)
	return DELAI_PAR_DEFAUT


def echeance_finalisation(candidature):
	return add_days(today(), delai_finalisation(candidature))


def delai_depasse(finaliser_avant):
	return bool(finaliser_avant) and getdate(today()) > getdate(finaliser_avant)


def verifier_delai(dossier):
	"""Bloque la finalisation d'une admission dont le délai est passé."""
	if delai_depasse(dossier.get("finaliser_avant")):
		frappe.throw(
			_("Le délai pour finaliser votre inscription a expiré le {0}. "
			  "Rapprochez-vous de la scolarité.").format(format_date(dossier.get("finaliser_avant")))
		)


# --------------------------------------------------------------------------- #
#  Désistement
# --------------------------------------------------------------------------- #
def _fiche_concours(cand):
	if not cand.concours:
		return None
	nom = frappe.db.get_value("Candidat Concours",
							  {"concours": cand.concours, "candidature": cand.name}, "name")
	return frappe.get_doc("Candidat Concours", nom) if nom else None


def desister(candidature, motif):
	"""Désistement sans contrôle de rôle. Retourne la liste des candidats promus."""
	from udshed.api.concours_deliberation import ADMIS, ATTENTE, _changer_statut, _desister

	motif = (motif or "").strip()
	if not motif:
		frappe.throw(_("Indiquez le motif du désistement."))
	cand = frappe.get_doc("Session Inscription Candidate", candidature)
	if cand.candidature_status not in ("Accepté", STATUT_LISTE_ATTENTE):
		frappe.throw(_("Seul un candidat admis (statut « Accepté ») ou sur liste d'attente peut se "
					   "désister. Statut actuel : {0}.").format(cand.candidature_status))
	fiche = _fiche_concours(cand)
	if fiche and fiche.decision in (ADMIS, ATTENTE):
		doc = frappe.get_doc("Concours", fiche.concours)
		return _desister(doc, fiche, motif).get("promus", [])
	# Admission sur dossier : pas de liste d'attente à appeler.
	_changer_statut(cand.name, STATUT_DESISTE, commentaire=_("Désistement : {0}").format(motif))
	return []


@frappe.whitelist()
def desister_candidature(candidature, motif):
	"""Bouton « Enregistrer un désistement » de la fiche candidature (scolarité)."""
	_exiger_scolarite()
	return {"promus": desister(candidature, motif)}


@frappe.whitelist(allow_guest=True)
def renoncer_admission(numero_dossier, nom_candidat, token=None, motif=None):
	"""Le candidat admis décline lui-même sa place depuis le portail d'inscription."""
	from udshed.api.inscription import _get_dossier, _verifier_jeton

	numero_dossier = (numero_dossier or "").strip().upper()
	if not _verifier_jeton(token, numero_dossier, nom_candidat):
		frappe.throw(_("Session d'authentification expirée. Veuillez recommencer."))
	dossier = _get_dossier(numero_dossier, nom_candidat)
	if not dossier or dossier.candidature_status != "Accepté":
		frappe.throw(_("Aucune admission en attente de confirmation pour ce dossier."))
	motif = (motif or "").strip() or _("aucun motif indiqué")
	desister(dossier.name, _("renoncement du candidat ({0})").format(motif))
	return {"status": "ok"}


# --------------------------------------------------------------------------- #
#  Page publique « Mon admission »
# --------------------------------------------------------------------------- #
@frappe.whitelist(allow_guest=True)
def consulter_admission(numero_dossier, nom_candidat):
	"""Résultat du candidat (numéro de dossier + nom), et ce qu'il peut faire."""
	from frappe.utils import date_diff

	from udshed.api.inscription import (
		_FENETRE_ECHECS_SEC,
		_MAX_ECHECS_DOSSIER,
		_MAX_ECHECS_IP,
		_creer_jeton,
		_get_dossier,
		_pdf_url,
	)
	from udshed.utils import securite

	# Même anti force brute que l'authentification du portail d'inscription :
	# cette page renvoie un jeton qui permet de renoncer à la place.
	cle_dossier = (numero_dossier or "").strip().upper()
	ip = securite.ip_client()
	securite.verifier_tentatives("inscription-dossier", cle_dossier, _MAX_ECHECS_DOSSIER, _FENETRE_ECHECS_SEC)
	securite.verifier_tentatives("inscription-ip", ip, _MAX_ECHECS_IP, _FENETRE_ECHECS_SEC)

	dossier = _get_dossier(cle_dossier, nom_candidat)
	if not dossier:
		securite.enregistrer_echec("inscription-dossier", cle_dossier, _FENETRE_ECHECS_SEC)
		securite.enregistrer_echec("inscription-ip", ip, _FENETRE_ECHECS_SEC)
		frappe.throw(_("Numéro de dossier ou nom incorrect."))
	securite.reinitialiser_tentatives("inscription-dossier", cle_dossier)
	cand = frappe.get_doc("Session Inscription Candidate", dossier.name)
	statut = cand.candidature_status or "En attente"

	def formation(filiere, niveau):
		libelle = frappe.db.get_value("Field of study", filiere, "name_of_field") or filiere
		niv = frappe.db.get_value("Field of study Level", niveau, "level") or niveau
		return f"{libelle} — {niv}" if niv else libelle

	res = {
		"numero_dossier": cand.name, "nom": cand.full_name, "statut": statut,
		"concours": frappe.db.get_value("Concours", cand.concours, "titre") if cand.concours else "",
		"formation": formation(cand.filiere, cand.niveau) if cand.filiere else "",
	}
	if statut == "Accepté":
		res.update({
			"etat": "admis",
			"date_limite": format_date(cand.finaliser_avant) if cand.finaliser_avant else "",
			"jours_restants": date_diff(cand.finaliser_avant, today()) if cand.finaliser_avant else None,
			"delai_depasse": delai_depasse(cand.finaliser_avant),
			"token": _creer_jeton(cand.name, nom_candidat),
		})
	elif statut == "Inscrit":
		matricule = frappe.db.get_value("Inscription Academique", {"dossier_origine": cand.name}, "matricule")
		res.update({"etat": "inscrit", "matricule": matricule or "",
					 "pdf_url": _pdf_url(matricule) if matricule else ""})
	elif statut == STATUT_LISTE_ATTENTE:
		fiche = _fiche_concours(cand)
		res.update({"etat": "attente", "rangs": [
			{"formation": formation(r.filiere, r.niveau), "rang": r.rang}
			for r in (fiche.resultats if fiche else []) if r.decision == "Liste d'attente"
		]})
	elif statut == "Refusé":
		res.update({"etat": "refuse", "motif": cand.status_comment or ""})
	elif statut == STATUT_DESISTE:
		res.update({"etat": "desiste", "motif": cand.status_comment or ""})
	else:
		res["etat"] = "en_cours"
	return res


# --------------------------------------------------------------------------- #
#  Tâche quotidienne
# --------------------------------------------------------------------------- #
def _envoyer(cand, expiree):
	if not cand.email:
		return
	from udshed.api.candidature import get_school_logo_url
	from udshed.udshed.doctype.session_inscription_candidate.session_inscription_candidate import _get_sender

	filiere = frappe.db.get_value("Field of study", cand.filiere, "name_of_field") if cand.filiere else ""
	sujet = (_("Votre place n'a pas été confirmée") if expiree
			 else _("Rappel : confirmez votre inscription avant le {0}").format(format_date(cand.finaliser_avant)))
	try:
		frappe.sendmail(
			recipients=[cand.email],
			sender=_get_sender(),
			subject=sujet,
			template="admission_finalisation",
			args={
				"first_name": cand.first_name,
				"last_name": cand.last_name,
				"doc_name": cand.name,
				"filiere": filiere,
				"niveau": cand.niveau or "",
				"date_limite": format_date(cand.finaliser_avant),
				"expiree": expiree,
				"lien_admission": frappe.utils.get_url("/mon-admission"),
				"logo_url": get_school_logo_url(),
			},
			now=True,
		)
	except Exception:
		frappe.log_error(title=f"Échec e-mail finalisation {cand.name}")


def relancer_et_liberer():
	"""Relance les admis à J-3 ; libère les places dont le délai est passé."""
	relance = add_days(today(), JOURS_AVANT_RELANCE)
	for nom in frappe.get_all("Session Inscription Candidate",
							  {"candidature_status": "Accepté", "finaliser_avant": relance}, pluck="name"):
		_envoyer(frappe.get_doc("Session Inscription Candidate", nom), expiree=False)

	liberees = []
	# « is set » indispensable : pour « < », Frappe compare une date vide comme 0001-01-01.
	# Les admissions antérieures à la phase 5 (sans date limite) ne sont donc jamais libérées.
	for nom in frappe.get_all("Session Inscription Candidate",
							  [["candidature_status", "=", "Accepté"],
							   ["finaliser_avant", "is", "set"],
							   ["finaliser_avant", "<", today()]],
							  pluck="name", order_by="finaliser_avant asc"):
		cand = frappe.get_doc("Session Inscription Candidate", nom)
		try:
			desister(nom, _("inscription non finalisée avant le {0}").format(format_date(cand.finaliser_avant)))
			frappe.db.commit()
			_envoyer(cand, expiree=True)
			liberees.append(nom)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Libération de place impossible : {nom}")
	return liberees
