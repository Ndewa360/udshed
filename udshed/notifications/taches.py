# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tâches planifiées des automatisations (appelées par udshed.udshed.tasks).

Toutes sont idempotentes (clé d'envoi) : relancées le même jour ou après un arrêt
du serveur, elles n'envoient jamais deux fois le même message.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, cint, format_date, get_datetime, getdate, now_datetime, nowdate

from udshed.notifications import emettre, envoyer_resumes
from udshed.notifications.attentes import daa, doyens, enseignants_du_cours, relancer, utilisateur_etudiant
from udshed.notifications.evenements import etudiants_du_cours, users_etudiants


def _sur(fn, *args):
	try:
		return fn(*args)
	except Exception:
		frappe.log_error(title=f"udshed: tâche {fn.__name__}")
		return None


def quotidien():
	from udshed.utils.stages import rappel_soutenances

	for fn in (relancer, reinscriptions, saisie_ouverte, saisie_rappels, rappel_examens, rappel_soutenances,
			   jalons_non_prepares, echeances_frais, echecs_email, envoyer_resumes):
		_sur(fn)
		frappe.db.commit()


def horaire():
	_sur(publications_programmees)
	frappe.db.commit()


def hebdomadaire():
	_sur(resumes_direction)
	frappe.db.commit()


def planning_hebdomadaire(jour=None):
	"""Vendredi : le planning de la semaine suivante part aux enseignants de chaque classe,
	si l'envoi automatique est activé dans les réglages (sinon l'envoi reste manuel)."""
	if not cint(frappe.db.get_single_value("Udshed Setting", "envoi_planning_automatique")):
		return 0
	from udshed.api.planning_calendar_email import send_planning_to_mail

	jour = getdate(jour or nowdate())
	lundi = add_days(jour, 7 - jour.weekday())
	items = frappe.get_all("Planning Item", filters={"date": ["between", [f"{lundi} 00:00:00",
																		   f"{add_days(lundi, 6)} 23:59:59"]],
													 "status": ["!=", "Annulée"]}, fields=["cours", "academic_year"])
	classes = set()
	for it in items:
		for r in frappe.get_all("Course Field of study level item", filters={"parent": it.cours},
								fields=["filiere", "niveau"]):
			classes.add((it.academic_year, r.filiere, r.niveau))
	utilisateur, n = frappe.session.user, 0
	try:
		frappe.set_user("Administrator")
		for annee, filiere, niveau in sorted(classes):
			try:
				send_planning_to_mail({"academic_year": annee, "week_start": str(lundi), "filiere": filiere,
									   "niveau": niveau, "faculty": frappe.db.get_value("Field of study", filiere, "faculte")},
									  to_all_teacher=1)
				n += 1
			except Exception:
				frappe.log_error(title=f"udshed: planning hebdomadaire {filiere} {niveau}")
	finally:
		frappe.set_user(utilisateur)
	return n


# ---------------------------------------------------------------------- #
#  Réinscription
# ---------------------------------------------------------------------- #
def reinscriptions(jour=None):
	"""Invitation à l'ouverture, rappel 3 jours avant la clôture, liste des
	non-réinscrits à la scolarité après la clôture."""
	jour = getdate(jour or nowdate())
	n = 0
	for s in frappe.get_all("Session Reinscription", filters={"statut": ["in", ["Ouverte", "Fermée"]]},
							fields=["name", "academic_year", "statut", "date_ouverture", "date_cloture"]):
		attendus = frappe.get_all("Progression Academique",
								  filters={"annee_cible": s.academic_year, "reinscription": ["is", "not set"],
										   "statut": ["in", ["Admis au niveau supérieur", "Redouble"]]},
								  fields=["name", "student", "filiere_cible", "niveau_cible", "statut"])
		if s.statut == "Ouverte":
			cloture = format_date(s.date_cloture) if s.date_cloture else ""
			for p in attendus:
				dest = _etudiant(p.student)
				n += emettre("reinscription_ouverte", [dest], _("La réinscription {0} est ouverte").format(s.academic_year),
							 _("Réinscrivez-vous en {0} avant le {1}.").format(p.niveau_cible or "", cloture),
							 lien="/reinscription-etudiant", reference=("Session Reinscription", s.name),
							 cle=f"{s.name}:{p.student}")
				if s.date_cloture and 0 <= (getdate(s.date_cloture) - jour).days <= 3:
					n += emettre("reinscription_rappel", [dest], _("Rappel : réinscription close le {0}").format(cloture),
								 _("Votre réinscription n'est pas encore faite."), lien="/reinscription-etudiant",
								 reference=("Session Reinscription", s.name), cle=f"{s.name}:{p.student}:j-3")
		elif attendus:
			par_filiere = {}
			for p in attendus:
				par_filiere.setdefault(p.filiere_cible, []).append(p)
			from udshed.notifications.attentes import scolarite

			for filiere, lignes in par_filiere.items():
				nom = frappe.db.get_value("Field of study", filiere, "name_of_field") or filiere
				n += emettre("reinscription_non_reinscrits", scolarite(filiere),
							 _("{0} : {1} étudiant(s) non réinscrit(s)").format(nom, len(lignes)),
							 _("La réinscription {0} est close. Contactez ces étudiants ou traitez leur cas.").format(
								 s.academic_year), reference=("Session Reinscription", s.name),
							 lien="/app/progression-academique?reinscription=%5B%22is%22%2C%22not%20set%22%5D",
							 cle=f"{s.name}:{filiere}")
	return n


def _etudiant(student):
	s = frappe.db.get_value("Student", student, ["utilisateur", "email", "phone"], as_dict=True) or {}
	return {"user": s.get("utilisateur"), "email": s.get("email"), "phone": s.get("phone")}


# ---------------------------------------------------------------------- #
#  Saisie des notes
# ---------------------------------------------------------------------- #
def _enseignants_periode(p, seulement_non_confirmes):
	from udshed.notifications.attentes import _ues_de_la_periode

	par_user = {}
	for tu in _ues_de_la_periode(p):
		if seulement_non_confirmes and frappe.db.exists("Confirmation Saisie", {
				"teaching_unit": tu.name, "type_evaluation": p.type_evaluation, "academic_year": p.academic_year,
				"semestre": p.semestre}):
			continue
		for user in enseignants_du_cours(tu.name):
			par_user.setdefault(user, []).append(tu.intitule_cours or tu.name)
	return par_user


def saisie_ouverte():
	n = 0
	maintenant = now_datetime()
	for p in frappe.get_all("Periode Saisie Notes", filters={"ouverture": ["between", [add_days(maintenant, -1), maintenant]]},
							fields=["name", "academic_year", "semestre", "type_evaluation", "faculte", "ouverture",
									"fermeture"]):
		for user, cours in _enseignants_periode(p, False).items():
			n += emettre("saisie_ouverte", [user], _("Saisie des notes ouverte : {0}").format(p.type_evaluation.lower()),
						 _("Jusqu'au {0} pour : {1}.").format(format_date(p.fermeture), ", ".join(cours)),
						 lien="/desk/note-udshed", reference=("Periode Saisie Notes", p.name), cle=f"{p.name}:{user}")
	return n


def saisie_rappels():
	"""Rappel à J-3 et à J-1 aux enseignants qui n'ont pas confirmé."""
	n = 0
	maintenant = now_datetime()
	for p in frappe.get_all("Periode Saisie Notes", filters={"fermeture": ["between", [maintenant, add_days(maintenant, 3)]]},
							fields=["name", "academic_year", "semestre", "type_evaluation", "faculte", "fermeture"]):
		etape = "j-1" if get_datetime(p.fermeture) <= add_days(maintenant, 1) else "j-3"
		for user, cours in _enseignants_periode(p, True).items():
			n += emettre("saisie_rappel", [user], _("Rappel : saisie des notes à confirmer avant le {0}").format(
				format_date(p.fermeture)),
				_("Non encore confirmé : {0}. Après la date limite, une dérogation du doyen sera nécessaire.").format(
					", ".join(cours)), lien="/desk/note-udshed", reference=("Periode Saisie Notes", p.name),
				cle=f"{p.name}:{user}:{etape}")
	return n


# ---------------------------------------------------------------------- #
#  Examens : rappel la veille de chaque épreuve
# ---------------------------------------------------------------------- #
def rappel_examens(jour=None):
	demain = add_days(getdate(jour or nowdate()), 1)
	n = 0
	for item in frappe.get_all("Planning Item", filters={
			"type": ["in", ["Examen de session normal", "Examen de rattrapage", "Controlle Continue (CC)"]],
			"status": ["!=", "Annulée"], "date": ["between", [f"{demain} 00:00:00", f"{demain} 23:59:59"]]},
			fields=["name", "cours", "date", "salle", "type"]):
		intitule = frappe.db.get_value("Teaching Unit", item.cours, "intitule_cours") or item.cours
		dest = enseignants_du_cours(item.cours) + users_etudiants(etudiants_du_cours(item.cours))
		n += emettre("examen_rappel", dest, _("Demain : {0} ({1})").format(intitule, item.type),
					 _("Le {0}{1}. Présentez-vous à l'heure avec votre carte d'étudiant.").format(
						 frappe.utils.format_datetime(item.date, "dd/MM/yyyy"),
						 _(", salle {0}").format(item.salle) if item.salle else ""),
					 lien="/app/mon-espace-etudiant", reference=("Planning Item", item.name), cle=item.name)
	return n


# ---------------------------------------------------------------------- #
#  Calendrier : jalons à venir sans préparation
# ---------------------------------------------------------------------- #
def jalons_non_prepares(jour=None):
	jour = getdate(jour or nowdate())
	n = 0
	for j in frappe.get_all("Jalon Academique", filters={"statut": "À préparer",
														 "date_debut": ["between", [jour, add_days(jour, 7)]]},
							fields=["name", "libelle", "type_jalon", "date_debut", "faculte"]):
		restant = (getdate(j.date_debut) - jour).days
		etape = "j-2" if restant <= 2 else "j-7"
		dest = doyens(faculte=j.faculte) if j.faculte else daa()
		n += emettre("jalon_non_prepare", dest, _("Dans {0} jour(s) : {1} n'est pas préparé").format(restant, j.libelle),
					 _("Le jalon « {0} » ({1}) commence le {2} et aucun objet n'y est encore rattaché.").format(
						 j.libelle, j.type_jalon, format_date(j.date_debut)),
					 reference=("Jalon Academique", j.name), cle=f"{j.name}:{etape}")
	return n


# ---------------------------------------------------------------------- #
#  Frais de scolarité
# ---------------------------------------------------------------------- #
def echeances_frais(jour=None):
	from udshed.utils import frais

	jour = getdate(jour or nowdate())
	frais.mettre_a_jour_retards(jour)
	n = 0
	for e in frappe.get_all("Echeance Etudiant", filters={"statut": "À payer",
														  "date_echeance": ["between", [jour, add_days(jour, 7)]]},
							fields=["name", "student", "libelle", "reste", "date_echeance"]):
		etape = "j0" if getdate(e.date_echeance) == jour else "j-7"
		n += emettre("frais_echeance", [_etudiant(e.student)],
					 _("Échéance le {0} : {1}").format(format_date(e.date_echeance), e.libelle),
					 _("Reste à payer : {0}.").format(frappe.format(e.reste, {"fieldtype": "Currency"})),
					 lien="/app/mon-espace-etudiant", reference=("Echeance Etudiant", e.name), cle=f"{e.name}:{etape}")
	return n


# ---------------------------------------------------------------------- #
#  Publication programmée (décision humaine prise d'avance)
# ---------------------------------------------------------------------- #
def publications_programmees():
	from udshed.api.saisie_notes import publier_session

	publiees = []
	for s in frappe.get_all("Session Examen", filters={"statut": "Brouillon", "publier_le": ["<=", now_datetime()]},
							fields=["name", "programme_par"]):
		utilisateur = frappe.session.user
		try:
			frappe.set_user(s.programme_par or "Administrator")
			publier_session(s.name)
			frappe.db.commit()
			publiees.append(s.name)
		except Exception as e:
			frappe.db.rollback()
			frappe.db.set_value("Session Examen", s.name, "publier_le", None)
			frappe.db.commit()
			frappe.log_error(title=f"udshed: publication programmée {s.name}")
			if s.programme_par:
				emettre("session_a_publier", [s.programme_par], _("Publication programmée impossible : {0}").format(s.name),
						str(e)[:300], reference=("Session Examen", s.name), cle=f"echec:{s.name}:{nowdate()}")
		finally:
			frappe.set_user(utilisateur)
	return publiees


# ---------------------------------------------------------------------- #
#  Pilotage
# ---------------------------------------------------------------------- #
def resumes_direction(jour=None):
	from udshed.api.direction import _indicateurs

	annee = frappe.db.get_single_value("Udshed Setting", "current_year")
	if not annee:
		return 0
	semaine = getdate(jour or nowdate()).isocalendar()
	cle = f"{semaine[0]}-S{semaine[1]}"
	n = 0
	for f in frappe.get_all("Faculty", fields=["name", "faculty_name", "doyen", "vice_doyen"]):
		dest = [u for u in (f.doyen, f.vice_doyen) if u]
		if not dest:
			continue
		filieres = frappe.get_all("Field of study", filters={"faculte": f.name}, pluck="name")
		n += emettre("resume_faculte", dest, _("Semaine {0} : votre faculté en bref").format(semaine[1]),
					 _resume_html(_indicateurs(annee, filieres)), lien="/desk/ma-faculte", cle=f"{f.name}:{cle}")
	dest = daa()
	if dest:
		n += emettre("resume_etablissement", dest, _("Semaine {0} : l'établissement en bref").format(semaine[1]),
					 _resume_html(_indicateurs(annee, frappe.get_all("Field of study", pluck="name"))),
					 lien="/desk/direction-academique", cle=cle)
	return n


def _resume_html(ind):
	libelles = [("inscrits", _("Inscrits")), ("reinscrits", _("Réinscrits")), ("avancement", _("Avancement des cours (%)")),
				("taux_saisie", _("Saisies confirmées (%)")), ("taux_reussite", _("Taux de réussite (%)")),
				("derogations", _("Dérogations à traiter")), ("actes_a_signer", _("Actes à signer"))]
	lignes = []
	for cle, libelle in libelles:
		v = ind.get(cle)
		if isinstance(v, dict):
			v = v.get("valeur", v.get("taux", ""))
		lignes.append(f"<tr><td style='padding:4px 12px 4px 0'>{libelle}</td><td><strong>{frappe.utils.escape_html(str(v if v is not None else '—'))}</strong></td></tr>")
	return "<table>" + "".join(lignes) + "</table>"


def echecs_email():
	depuis = add_to_date(now_datetime(), days=-1)
	echecs = frappe.db.count("Email Queue", {"status": "Error", "modified": [">=", depuis]})
	if not echecs:
		return 0
	from udshed.utils.perimetre import destinataires

	return emettre("echecs_email", destinataires(("System Manager",)),
				   _("{0} e-mail(s) non envoyés depuis 24 h").format(echecs),
				   _("Vérifiez le compte d'envoi (paramètres e-mail) et la file d'envoi."),
				   lien="/app/email-queue?status=Error", cle=f"{nowdate()}")
