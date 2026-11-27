# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Réactions aux événements métier (doc_events et appels depuis les API).

Chaque fonction est protégée : un échec de notification ou d'automatisation est
journalisé et n'annule jamais l'action de l'utilisateur.
"""

import functools

import frappe
from frappe import _
from frappe.utils import add_to_date, format_datetime, get_datetime, now_datetime

from udshed.notifications import emettre
from udshed.notifications.attentes import (coordination, doyens, enseignants_du_cours, utilisateur_etudiant,
										   _user_enseignant)

TYPES_COURTS = {"Cours Magistral (CM)": "CM", "Travaux Dirigés (TD)": "TD", "Travaux Pratique (TP)": "TP"}


def protege(fn):
	@functools.wraps(fn)
	def enveloppe(*args, **kwargs):
		if frappe.flags.in_import or frappe.flags.in_migrate or frappe.flags.udshed_sans_notification:
			return None
		try:
			return fn(*args, **kwargs)
		except Exception:
			frappe.log_error(title=f"udshed: automatisation {fn.__name__}")
			return None
	return enveloppe


# ---------------------------------------------------------------------- #
#  Classes et étudiants
# ---------------------------------------------------------------------- #
def classes_du_cours(teaching_unit):
	return [(r.filiere, r.niveau) for r in frappe.get_all("Course Field of study level item",
														   filters={"parent": teaching_unit},
														   fields=["filiere", "niveau"])]


def etudiants_du_cours(teaching_unit):
	from udshed.api.resultats_page import _get_etudiants

	annee = frappe.db.get_value("Teaching Unit", teaching_unit, "academic_year")
	res = set()
	for filiere, niveau in classes_du_cours(teaching_unit):
		libelle = frappe.db.get_value("Field of study Level", niveau, "level") or niveau
		for e in _get_etudiants(annee, filiere, libelle, teaching_unit):
			res.add(e["student"])
	return sorted(res)


def etudiants_de_la_classe(academic_year, filiere, niveau_libelle):
	from udshed.api.resultats_page import _etudiants_classe, _ues_classe

	ues = [u.name for u in _ues_classe(academic_year, filiere, niveau_libelle)]
	return [e["student"] for e in _etudiants_classe(academic_year, filiere, niveau_libelle, ues)]


def users_etudiants(students):
	return [u for u in (utilisateur_etudiant(s) for s in students) if u]


# ---------------------------------------------------------------------- #
#  Enseignement
# ---------------------------------------------------------------------- #
@protege
def teaching_unit_modifie(doc, method=None):
	"""Nouvel enseignant affecté à un cours : il est prévenu."""
	avant = doc.get_doc_before_save()
	anciens = {(r.enseignant, r.type_de_cours) for r in (avant.table_enseignant if avant else [])}
	for r in doc.table_enseignant:
		if (r.enseignant, r.type_de_cours) in anciens:
			continue
		user = _user_enseignant(r.enseignant)
		email = frappe.db.get_value("Teacher", r.enseignant, "email")
		emettre("affectation_cours", [user or email],
				_("Vous êtes affecté(e) au cours {0} ({1})").format(doc.intitule_cours or doc.course,
																	TYPES_COURTS.get(r.type_de_cours, r.type_de_cours)),
				_("Année {0}, {1}. Retrouvez vos cours et votre planning dans votre espace enseignant.").format(
					doc.academic_year, doc.semestre or ""),
				reference=("Teaching Unit", doc.name), lien="/desk/mes-documents-enseignant",
				cle=f"{doc.name}:{r.enseignant}:{r.type_de_cours}")


@protege
def seance_modifiee(doc, method=None):
	"""Séance déplacée ou annulée moins de 72 h avant : enseignants et étudiants prévenus."""
	avant = doc.get_doc_before_save()
	if not avant:
		return
	maintenant = now_datetime()
	limite = add_to_date(maintenant, hours=72)
	date_avant, date_apres = get_datetime(avant.date), get_datetime(doc.date)
	proche = (maintenant <= date_avant <= limite) or (maintenant <= date_apres <= limite)
	if not proche:
		return
	annulee = doc.status == "Annulée" and avant.status != "Annulée"
	deplacee = (date_avant != date_apres or avant.period != doc.period or avant.salle != doc.salle)
	if not (annulee or deplacee):
		return
	intitule = frappe.db.get_value("Teaching Unit", doc.cours, "intitule_cours") or doc.cours
	if annulee:
		sujet = _("Séance annulée : {0} du {1}").format(intitule, format_datetime(date_avant, "dd/MM/yyyy"))
		message = _("La séance de {0} prévue le {1} est annulée.").format(intitule, format_datetime(date_avant, "dd/MM/yyyy"))
	else:
		sujet = _("Séance modifiée : {0}").format(intitule)
		message = _("Nouvelle date : {0}{1}.").format(format_datetime(date_apres, "dd/MM/yyyy"),
													 _(", salle {0}").format(doc.salle) if doc.salle else "")
	destinataires = enseignants_du_cours(doc.cours) + users_etudiants(etudiants_du_cours(doc.cours))
	emettre("seance_modifiee", destinataires, sujet, message, reference=("Planning Item", doc.name),
			lien="/desk/planning-academique", cle=f"{doc.name}:{doc.modified}")


@protege
def convention_creee(doc, method=None):
	user = _user_enseignant(doc.teacher)
	email = frappe.db.get_value("Teacher", doc.teacher, "email")
	emettre("convention_disponible", [user or email], _("Votre convention de vacation {0} est disponible").format(
		doc.academic_year), _("Consultez-la et téléchargez-la dans votre espace enseignant."),
		reference=("Convention Vacation", doc.name), lien="/desk/mes-documents-enseignant", cle=doc.name)


# ---------------------------------------------------------------------- #
#  Évaluations et résultats
# ---------------------------------------------------------------------- #
@protege
def saisie_confirmee(doc, method=None):
	"""Toutes les matières d'une classe confirmées pour une évaluation : la coordination est prévenue."""
	if not (doc.filiere and doc.niveau):
		return
	tus = frappe.get_all("Course Field of study level item", filters={"filiere": doc.filiere, "niveau": doc.niveau},
						 pluck="parent")
	tus = frappe.get_all("Teaching Unit", filters={"name": ["in", tus or [""]], "academic_year": doc.academic_year,
												   "semestre": doc.semestre}, pluck="name")
	confirmees = set(frappe.get_all("Confirmation Saisie", filters={
		"teaching_unit": ["in", tus or [""]], "type_evaluation": doc.type_evaluation,
		"academic_year": doc.academic_year, "semestre": doc.semestre}, pluck="teaching_unit"))
	if not tus or set(tus) - confirmees:
		return
	niveau = frappe.db.get_value("Field of study Level", doc.niveau, "level") or doc.niveau
	nom = frappe.db.get_value("Field of study", doc.filiere, "name_of_field") or doc.filiere
	emettre("classe_notes_completes", coordination(doc.filiere),
			_("{0} — {1} : toutes les notes ({2}) sont confirmées").format(nom, niveau, doc.type_evaluation.lower()),
			_("Les {0} matières de la classe sont confirmées pour le {1}. Vous pouvez valider puis publier la session.").format(
				len(tus), doc.semestre),
			lien="/desk/note-udshed",
			cle=f"{doc.filiere}:{doc.niveau}:{doc.academic_year}:{doc.semestre}:{doc.type_evaluation}")


@protege
def apres_publication(session):
	"""Après la publication d'une session de fin d'année (S2 normale ou rattrapage) :
	une délibération est préparée en brouillon pour chaque classe et le doyen est prévenu.
	Le jury reste maître de sa décision : rien n'est appliqué automatiquement."""
	doc = frappe.get_doc("Session Examen", session) if isinstance(session, str) else session
	if doc.semestre != "Semestre 2" or doc.type_dexamen not in ("Examen de session normal", "Examen de rattrapage"):
		return []
	creees = []
	for c in doc.classes_concernees:
		if not (c.filiere and c.niveau):
			continue
		existante = frappe.db.get_value("Deliberation Jury", {"academic_year": doc.academic_year, "filiere": c.filiere,
															  "niveau": c.niveau}, "name")
		if not existante:
			delib = frappe.get_doc({"doctype": "Deliberation Jury", "academic_year": doc.academic_year,
									"filiere": c.filiere, "niveau": c.niveau, "statut": "Brouillon"})
			delib.flags.ignore_mandatory = True
			delib.insert(ignore_permissions=True)
			existante = delib.name
			creees.append(existante)
		niveau = frappe.db.get_value("Field of study Level", c.niveau, "level") or c.niveau
		nom = frappe.db.get_value("Field of study", c.filiere, "name_of_field") or c.filiere
		emettre("deliberation_a_tenir", doyens(c.filiere), _("Classe prête à délibérer : {0} — {1}").format(nom, niveau),
				_("Les résultats de fin d'année sont publiés. La délibération est préparée : examinez les cas proches "
				  "du seuil, puis appliquez-la."), reference=("Deliberation Jury", existante),
				cle=f"{existante}:{doc.name}")
	return creees


@protege
def deliberation_modifiee(doc, method=None):
	"""Délibération appliquée : chaque étudiant reçoit sa décision de fin d'année."""
	avant = doc.get_doc_before_save()
	if doc.statut != "Appliquée" or (avant and avant.statut == "Appliquée"):
		return
	for p in frappe.get_all("Progression Academique", filters={"annee_source": doc.academic_year,
															   "filiere_source": doc.filiere},
							fields=["name", "student", "statut", "niveau_cible", "credits_valides", "credits_dette"]):
		if p.statut not in ("Admis au niveau supérieur", "Redouble"):
			continue
		user = utilisateur_etudiant(p.student)
		email = frappe.db.get_value("Student", p.student, "email")
		message = (_("Décision du jury : admis(e) en {0}. Crédits validés : {1}.").format(p.niveau_cible, p.credits_valides)
				   if p.statut == "Admis au niveau supérieur"
				   else _("Décision du jury : redoublement. Crédits validés : {0}.").format(p.credits_valides))
		emettre("resultats_annuels", [{"user": user, "email": email, "phone": frappe.db.get_value("Student", p.student, "phone")}],
				_("Vos résultats de l'année {0} sont disponibles").format(doc.academic_year), message,
				lien="/app/mon-espace-etudiant", reference=("Progression Academique", p.name), cle=f"{doc.name}:{p.name}")


@protege
def rattrapage_cree(resultat):
	"""Session de rattrapage créée : les étudiants concernés sont convoqués."""
	session = frappe.get_doc("Session Examen", resultat["session_rattrapage"])
	par_etudiant = {}
	for e in resultat.get("etudiants") or []:
		par_etudiant.setdefault(e["student"], []).extend(
			frappe.db.get_value("Teaching Unit", ue, "intitule_cours") or ue for ue in e.get("ue_concernees") or [])
	for student, matieres in par_etudiant.items():
		s = frappe.db.get_value("Student", student, ["utilisateur", "email", "phone"], as_dict=True) or {}
		emettre("rattrapage_convocation", [{"user": s.get("utilisateur"), "email": s.get("email"), "phone": s.get("phone")}],
				_("Convocation au rattrapage du {0}").format(session.semestre),
				_("Session du {0} au {1}. Matières : {2}.").format(
					frappe.format(session.date_debut, {"fieldtype": "Date"}),
					frappe.format(session.date_de_fin, {"fieldtype": "Date"}), ", ".join(m for m in matieres if m) or "—"),
				lien="/app/mon-espace-etudiant", reference=("Session Examen", session.name),
				cle=f"{session.name}:{student}")


# ---------------------------------------------------------------------- #
#  Calendrier académique : les dates des objets alimentent les jalons
# ---------------------------------------------------------------------- #
SOURCES_JALON = {
	"Periode Saisie Notes": ("Saisie des notes", "ouverture", "fermeture"),
	"Session Inscription": ("Campagne d'admission", "opening_date", "closing_date"),
	"Session Reinscription": ("Réinscription", "date_ouverture", "date_cloture"),
	"Session Examen": ("Session d'examen", "date_debut", "date_de_fin"),
	"Deliberation Jury": ("Délibération", "date_deliberation", None),
}


@protege
def synchroniser_jalon(doc, method=None):
	type_jalon, champ_debut, champ_fin = SOURCES_JALON[doc.doctype]
	debut = doc.get(champ_debut)
	if not debut or not doc.get("academic_year"):
		return
	if doc.doctype == "Session Examen" and doc.type_dexamen == "Examen de rattrapage":
		type_jalon = "Rattrapage"
	libelle = _libelle_jalon(doc, type_jalon)
	valeurs = {"academic_year": doc.academic_year, "type_jalon": type_jalon, "libelle": libelle,
			   "date_debut": get_datetime(debut).date(),
			   "date_fin": get_datetime(doc.get(champ_fin)).date() if champ_fin and doc.get(champ_fin) else None,
			   "semestre": doc.get("semestre") or "", "faculte": doc.get("faculte") or _faculte(doc),
			   "statut": "Préparé", "reference_doctype": doc.doctype, "reference_name": doc.name}
	nom = frappe.db.get_value("Jalon Academique", {"reference_doctype": doc.doctype, "reference_name": doc.name}, "name")
	if nom:
		jalon = frappe.get_doc("Jalon Academique", nom)
		jalon.update({k: v for k, v in valeurs.items() if k != "statut"})
	else:
		# Un jalon prévu « à préparer » du même type et de la même date est rattaché à cet objet.
		prevu = frappe.db.get_value("Jalon Academique", {"academic_year": doc.academic_year, "type_jalon": type_jalon,
														 "statut": "À préparer", "reference_name": ["is", "not set"]},
									"name", order_by="date_debut asc")
		jalon = frappe.get_doc("Jalon Academique", prevu) if prevu else frappe.new_doc("Jalon Academique")
		jalon.update(valeurs)
	jalon.flags.ignore_permissions = True
	jalon.save()


def supprimer_jalon(doc, method=None):
	for nom in frappe.get_all("Jalon Academique", filters={"reference_doctype": doc.doctype, "reference_name": doc.name},
							  pluck="name"):
		frappe.db.set_value("Jalon Academique", nom, {"reference_doctype": None, "reference_name": None,
													   "statut": "À préparer"})


def _faculte(doc):
	if doc.get("filiere"):
		return frappe.db.get_value("Field of study", doc.filiere, "faculte")
	return None


def _libelle_jalon(doc, type_jalon):
	if doc.doctype == "Periode Saisie Notes":
		return _("Saisie : {0}, {1}").format(doc.type_evaluation.lower(), doc.semestre)
	if doc.doctype == "Session Examen":
		return _("{0} — {1}").format(doc.type_dexamen, doc.semestre)
	if doc.doctype == "Deliberation Jury":
		nom = frappe.db.get_value("Field of study", doc.filiere, "name_of_field") or doc.filiere
		niveau = frappe.db.get_value("Field of study Level", doc.niveau, "level") or doc.niveau
		return _("Délibération {0} — {1}").format(nom, niveau)
	return doc.get("titre") or type_jalon
