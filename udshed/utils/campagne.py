"""Campagne d'admission (DocType « Session Inscription »).

La campagne est la source de vérité du parcours candidat :
  - `academic_year` est l'année de RENTRÉE (année cible) : une campagne menée
	pendant 2025-2026 recrute pour 2026-2027. Inscription, UE, matricule,
	fiches et emails utilisent cette année, jamais l'année en cours des réglages ;
  - [opening_date, closing_date] est la période de DÉPÔT des candidatures ;
  - `date_limite_inscription` borne la FINALISATION des inscriptions des admis,
	qui a lieu après la clôture des dépôts (délibération, liste d'attente) ;
  - `delai_finalisation` est le délai individuel accordé à chaque admis
	(un concours peut fixer le sien) ;
  - `centres_examen` liste les centres proposés aux candidats (un par ligne).
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

DOCTYPE = "Session Inscription"
DELAI_PAR_DEFAUT = 15  # jours accordés à un admis pour confirmer sa place


def _doc(nom):
	return frappe.get_cached_doc(DOCTYPE, nom) if nom and frappe.db.exists(DOCTYPE, nom) else None


def campagne_ouverte():
	"""Campagne dont les dépôts sont ouverts aujourd'hui (statut Open et dans
	la période de dépôt), sinon None."""
	jour = getdate(today())
	for nom in frappe.get_all(DOCTYPE, filters={"status": "Open"}, pluck="name", order_by="opening_date desc"):
		doc = _doc(nom)
		if doc and getdate(doc.opening_date) <= jour <= getdate(doc.closing_date):
			return doc
	return None


def campagne_courante():
	"""Campagne de référence pour l'affichage public : l'ouverte, sinon la
	plus récente (pour annoncer « candidatures closes » ou la prochaine)."""
	ouverte = campagne_ouverte()
	if ouverte:
		return ouverte
	nom = frappe.db.get_value(DOCTYPE, {}, "name", order_by="opening_date desc")
	return _doc(nom)


def campagne_du_dossier(dossier):
	"""Campagne d'une candidature (nom, dict ou document)."""
	if isinstance(dossier, str):
		nom = frappe.db.get_value("Session Inscription Candidate", dossier, "session_inscription")
	else:
		nom = dossier.get("session_inscription")
	return _doc(nom)


def annee_cible(dossier=None):
	"""Année de rentrée d'une candidature (celle de sa campagne). Repli : année
	de la campagne courante, puis année en cours des réglages."""
	campagne = campagne_du_dossier(dossier) if dossier else campagne_courante()
	if campagne and campagne.academic_year:
		return campagne.academic_year
	return frappe.db.get_single_value("Udshed Setting", "current_year") or ""


def exiger_depot_ouvert():
	"""Refuse un dépôt de candidature hors période de dépôt."""
	campagne = campagne_ouverte()
	if campagne:
		return campagne
	prochaine = frappe.db.get_value(
		DOCTYPE, {"opening_date": [">", today()]}, ["opening_date", "academic_year"],
		as_dict=True, order_by="opening_date asc",
	)
	if prochaine:
		frappe.throw(
			_("Les candidatures pour l'année {0} ouvriront le {1}.").format(
				prochaine.academic_year, frappe.utils.format_date(prochaine.opening_date)
			),
			title=_("Candidatures fermées"),
		)
	frappe.throw(_("Aucune campagne de candidature n'est ouverte actuellement."), title=_("Candidatures fermées"))


def date_limite_inscription(campagne):
	if not campagne:
		return None
	return campagne.get("date_limite_inscription") or None


def exiger_inscription_ouverte(dossier):
	"""Un admis peut finaliser son inscription tant que la date limite
	d'inscription de SA campagne n'est pas passée (le délai individuel est
	vérifié séparément). La clôture des dépôts ne bloque plus les admis."""
	campagne = campagne_du_dossier(dossier)
	if not campagne:
		frappe.throw(_("Ce dossier n'est rattaché à aucune campagne d'admission. Contactez la scolarité."))
	limite = date_limite_inscription(campagne)
	if limite and getdate(today()) > getdate(limite):
		frappe.throw(
			_("Les inscriptions de la campagne {0} sont closes depuis le {1}. Rapprochez-vous de la scolarité.").format(
				campagne.academic_year, frappe.utils.format_date(limite)
			)
		)
	return campagne


def delai_finalisation(campagne):
	return int((campagne.get("delai_finalisation") if campagne else 0) or DELAI_PAR_DEFAUT)


def echeance_individuelle(campagne, delai):
	"""Date limite d'un admis : aujourd'hui + délai, sans dépasser la date
	limite d'inscription de la campagne."""
	echeance = add_days(today(), delai)
	limite = date_limite_inscription(campagne)
	if limite and getdate(echeance) > getdate(limite):
		return getdate(limite)
	return getdate(echeance)


def centres(campagne=None):
	"""Centres d'examen proposés (un par ligne dans la campagne)."""
	campagne = campagne or campagne_courante()
	texte = (campagne.get("centres_examen") if campagne else "") or ""
	vus = []
	for ligne in texte.replace("\r", "").split("\n"):
		ligne = ligne.strip()
		if ligne and ligne not in vus:
			vus.append(ligne)
	return vus


def titre(campagne):
	if not campagne:
		return ""
	return campagne.get("titre") or _("Candidatures {0}").format(campagne.academic_year)


@frappe.whitelist(allow_guest=True)
def infos_publiques():
	"""Ce que les pages publiques affichent : établissement, campagne, état."""
	from udshed.utils.etablissement import etablissement

	campagne = campagne_courante()
	ouverte = campagne_ouverte()
	jour = getdate(today())
	etat = "aucune"
	if campagne:
		if ouverte and ouverte.name == campagne.name:
			etat = "ouverte"
		elif getdate(campagne.opening_date) > jour:
			etat = "a_venir"
		else:
			etat = "close"
	return {
		"etablissement": etablissement(),
		"campagne": {
			"name": campagne.name,
			"titre": titre(campagne),
			"academic_year": campagne.academic_year,
			"ouverture": frappe.utils.format_date(campagne.opening_date),
			"cloture": frappe.utils.format_date(campagne.closing_date),
			"date_limite_inscription": frappe.utils.format_date(date_limite_inscription(campagne))
			if date_limite_inscription(campagne) else "",
			"centres": centres(campagne),
		} if campagne else None,
		"etat": etat,
		"route_candidature": "/candidature/new",
	}
