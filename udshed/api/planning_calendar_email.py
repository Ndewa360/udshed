"""Envoi du planning hebdomadaire par email.

Règles :
  - un enseignant reçoit UNIQUEMENT son planning : toutes ses séances de la
    semaine, dans toutes ses classes et toutes les salles (cours liés compris),
    quel que soit le filtre (classe) affiché à l'écran au moment de l'envoi ;
  - « Envoyer à tous les enseignants » vise les enseignants qui ont au moins
    une séance cette semaine dans la classe affichée ;
  - « M'envoyer une copie » : un enseignant reçoit son propre planning, un
    gestionnaire reçoit le planning affiché à l'écran ;
  - chaque mail contient le PDF en pièce jointe ET le détail des séances dans
    le corps, ainsi que les coordonnées de l'établissement et de l'éditeur.

Au-delà de quelques destinataires, l'envoi part en tâche de fond (génération
d'un PDF par enseignant) pour ne pas dépasser le délai d'une requête web.
"""

from datetime import datetime

import frappe
from frappe import _

import udshed.api.planning_calendar as planning_calendar
import udshed.api.planning_calendar_pdf as planning_calendar_pdf
import udshed.api.planning_permission as planning_permission
import udshed.utils.email_utils as email_utils
import udshed.utils.file_utils as file_utils
from udshed.api.planning_calendar_pdf import date_fr

EDITEUR = {
	"nom": "Ndewa360",
	"telephone": "+237 6 80 91 61 59",
	"email": "contact@ndewa-360.com",
}

# Au-delà, l'envoi est mis en file (tâche de fond) au lieu d'être fait dans la requête.
SEUIL_ENVOI_DIRECT = 3

TYPES_COURTS = {
	"Cours Magistral (CM)": "CM",
	"Cours": "CM",
	"Traveaux Pratiques (TP)": "TP",
	"Travaux Pratique (TP)": "TP",
	"Traveaux Dirigés (TD)": "TD",
	"Travaux Dirigés (TD)": "TD",
	"Controlle Continue (CC)": "CC",
	"Examen de session normal": "Examen",
	"Examen de rattrapage": "Rattrapage",
}


# ---------------------------------------------------------------------- #
#  Destinataires
# ---------------------------------------------------------------------- #
def _teacher_doc(name):
	if not name:
		return None
	return frappe.db.get_value(
		"Teacher", name, ["name", "email", "grade", "first_name", "last_name"], as_dict=True
	)


def _teacher_label(teacher):
	return " ".join(
		part for part in [teacher.grade or "", teacher.first_name or "", teacher.last_name or ""] if part
	).strip() or teacher.name


def _filtres_enseignant(filters, teacher):
	"""Planning complet d'un enseignant : seuls l'année, la semaine et
	l'enseignant comptent (pas la classe affichée à l'écran)."""
	return {
		"academic_year": filters.get("academic_year"),
		"week_start": filters.get("week_start"),
		"teacher": teacher,
	}


def _destinataires(filters, items, to_all_teacher, to_teacher, to_me):
	"""(destinataires par email, enseignants sans email)."""
	destinataires = {}
	sans_email = []

	def ajouter_enseignant(name):
		teacher = _teacher_doc(name)
		if not teacher:
			return
		label = _teacher_label(teacher)
		email = (teacher.email or "").strip()
		if not email:
			if label not in sans_email:
				sans_email.append(label)
			return
		destinataires.setdefault(email, {
			"email": email,
			"label": label,
			"teacher": teacher.name,
			"filters": _filtres_enseignant(filters, teacher.name),
		})

	if to_teacher and filters.get("teacher"):
		ajouter_enseignant(filters["teacher"])

	if to_all_teacher:
		ids = {name for item in items for name in (item.get("teacher_ids") or [])}
		if filters.get("teacher"):
			ids.add(filters["teacher"])
		for name in sorted(ids):
			ajouter_enseignant(name)

	if to_me:
		# « M'envoyer » : la vue affichée à l'écran (classe ou enseignant), à l'adresse du compte.
		user = frappe.session.user
		email = frappe.db.get_value("User", user, "email")
		if not email:
			frappe.throw(_("Adresse email introuvable pour l'utilisateur courant."), frappe.ValidationError)
		destinataires.setdefault(email, {
			"email": email,
			"label": frappe.utils.get_fullname(user) or user,
			"teacher": filters.get("teacher"),
			"filters": dict(filters),
		})

	return destinataires, sans_email


# ---------------------------------------------------------------------- #
#  Point d'entrée
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def send_planning_to_mail(filters, to_all_teacher=None, to_teacher=None, to_me=None):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	if not isinstance(filters, dict):
		frappe.throw(_("Filtres invalides."), frappe.ValidationError)
	academic_year = filters.get("academic_year")
	week_start = filters.get("week_start")
	if not academic_year or not week_start:
		frappe.throw(_("Année académique et semaine sont requises."), frappe.ValidationError)
	to_all_teacher, to_teacher, to_me = (frappe.utils.cint(v) for v in (to_all_teacher, to_teacher, to_me))

	scope = planning_permission.assert_can_view_planning(
		academic_year,
		filters.get("faculty"),
		filters.get("filiere"),
		filters.get("niveau"),
		filters.get("teacher"),
	)
	filters = {**filters, **scope["filters"]}

	# Séances de la vue affichée : servent à trouver les enseignants de la classe.
	items = planning_calendar.get_week_planning(
		academic_year=academic_year,
		week_start=week_start,
		filiere=filters.get("filiere"),
		niveau=filters.get("niveau"),
		teacher=filters.get("teacher"),
		faculty=filters.get("faculty"),
	) if to_all_teacher else []

	destinataires, sans_email = _destinataires(filters, items, to_all_teacher, to_teacher, to_me)
	if not destinataires:
		if sans_email:
			frappe.throw(
				_("Aucun email envoyé : adresse email manquante pour {0}.").format(", ".join(sans_email)),
				frappe.ValidationError,
			)
		frappe.throw(_("Aucun destinataire sélectionné."), frappe.ValidationError)

	# Contrôle des droits AVANT tout envoi (et dans la requête de l'utilisateur).
	for entry in destinataires.values():
		f = entry["filters"]
		planning_permission.assert_can_view_planning(
			f.get("academic_year"), f.get("faculty"), f.get("filiere"), f.get("niveau"), f.get("teacher")
		)

	liste = list(destinataires.values())
	if len(liste) > SEUIL_ENVOI_DIRECT:
		frappe.enqueue(
			"udshed.api.planning_calendar_email.envoyer_en_arriere_plan",
			queue="long",
			timeout=3600,
			destinataires=liste,
			sans_email=sans_email,
			demandeur=frappe.session.user,
		)
		return {"queued": True, "total": len(liste), "sans_email": sans_email}

	resultat = _envoyer(liste, immediat=True)
	if not resultat["sent"]:
		frappe.throw(_("Échec de l'envoi : {0}").format("; ".join(resultat["errors"])), frappe.ValidationError)
	resultat["sans_email"] = sans_email
	return resultat


def envoyer_en_arriere_plan(destinataires, sans_email, demandeur):
	"""Tâche de fond : envoie puis notifie l'utilisateur qui a lancé l'envoi."""
	frappe.set_user(demandeur)
	resultat = _envoyer(destinataires, immediat=False)
	lignes = [_("Planning envoyé à {0} destinataire(s) sur {1}.").format(resultat["sent"], len(destinataires))]
	lignes += resultat["errors"]
	lignes += [_("{0} : aucune adresse email renseignée").format(nom) for nom in sans_email]
	frappe.publish_realtime(
		"msgprint",
		{
			"title": _("Envoi du planning"),
			"indicator": "green" if not (resultat["errors"] or sans_email) else "orange",
			"message": "<br>".join(frappe.utils.escape_html(l) for l in lignes),
		},
		user=demandeur,
	)
	return resultat


def _envoyer(destinataires, immediat):
	etablissement = _etablissement()
	erreurs = []
	envoyes = 0
	for entry in destinataires:
		try:
			pdf, nom_pdf, items, start, end = planning_calendar_pdf.generate_planning_pdf(entry["filters"])
			envoyer_planning(entry, etablissement, pdf, nom_pdf, items, start, end, immediat=immediat)
			envoyes += 1
		except Exception as exc:
			frappe.log_error(title="Envoi du planning par email", message=frappe.get_traceback())
			erreurs.append("{0} ({1}) : {2}".format(entry["label"], entry["email"], str(exc) or exc.__class__.__name__))
	return {"sent": envoyes, "failed": len(erreurs), "errors": erreurs}


def envoyer_planning(entry, etablissement, pdf, nom_pdf, items, start, end, immediat=True):
	contexte = contexte_email(entry, etablissement, items, start, end)
	frappe.sendmail(
		recipients=[entry["email"]],
		sender=email_utils.get_formatted_sender(etablissement["nom_expediteur"]),
		reply_to=etablissement["email"] or None,
		subject=contexte["sujet"],
		message=frappe.render_template("udshed/templates/emails/planning_hebdomadaire.html", contexte),
		attachments=[{"fname": nom_pdf, "fcontent": pdf}],
		delayed=not immediat,
	)


# ---------------------------------------------------------------------- #
#  Contenu du mail
# ---------------------------------------------------------------------- #
def _etablissement():
	s = frappe.get_single("Udshed Setting")
	nom = s.get("school_name") or "Udshed"
	logo = ""
	if s.get("school_logo") and not str(s.school_logo).startswith("/private/"):
		# Les clients mail bloquent souvent les images en data-URI : URL publique.
		logo = file_utils.get_url_school_logo(s.school_logo)
	return {
		"nom": nom,
		"institut": s.get("school_institute") or "",
		"adresse": s.get("school_address") or "",
		"telephone": s.get("school_phone") or "",
		"email": s.get("school_email") or "",
		"site": s.get("school_website") or "",
		"logo": logo,
		"nom_expediteur": s.get("email_candidature_sender_name") or nom,
	}


def _heure(valeur):
	return planning_calendar_pdf._hhmm(valeur)


def _seances(items):
	"""Séances triées par jour puis heure, regroupées par jour."""
	creneaux = {}
	noms = {i.get("period") for i in items if i.get("period")}
	if noms:
		for p in frappe.get_all(
			"Planning Period",
			filters={"name": ["in", list(noms)]},
			fields=["name", "libelle", "heure_de_debut", "heure_de_fin"],
		):
			creneaux[p.name] = p

	lignes = []
	for item in items:
		if item.get("status") == "Annulée":
			continue
		p = creneaux.get(item.get("period")) or {}
		debut, fin = _heure(p.get("heure_de_debut")), _heure(p.get("heure_de_fin"))
		jour = planning_calendar_pdf._date_debut(item.get("date"))
		en_ligne = item.get("mode") == "En ligne"
		lieu = _("En ligne") if en_ligne else " · ".join(
			x for x in [
				"{0} {1}".format(_("Bât."), item.get("batiment")) if item.get("batiment") else "",
				"{0} {1}".format(_("Salle"), item.get("salle")) if item.get("salle") else "",
			] if x
		) or _("Salle à préciser")
		classes = item.get("classes") or [
			" ".join(x for x in [item.get("filiere") or "", item.get("niveau_label") or ""] if x)
		]
		lignes.append({
			"jour": jour,
			"horaire": "{0} – {1}".format(debut, fin) if debut and fin else (p.get("libelle") or ""),
			"debut": debut or "99:99",
			"cours": item.get("intitule_label") or item.get("course_label") or item.get("course") or item.get("cours"),
			"type": TYPES_COURTS.get(item.get("type"), item.get("type") or ""),
			"classes": ", ".join(c for c in classes if c),
			"lieu": lieu,
			"mode": item.get("mode") if item.get("mode") and item.get("mode") != "En présentiel" else "",
			"minutes": _minutes(p.get("heure_de_debut"), p.get("heure_de_fin")),
		})
	lignes.sort(key=lambda l: (l["jour"], l["debut"]))

	jours = []
	for ligne in lignes:
		if not jours or jours[-1]["date"] != ligne["jour"]:
			jours.append({"date": ligne["jour"], "libelle": date_fr(ligne["jour"], annee=False, jour=True), "seances": []})
		jours[-1]["seances"].append(ligne)
	return lignes, jours


def _minutes(debut, fin):
	d, f = _heure(debut), _heure(fin)
	try:
		hd, md = (int(x) for x in d.split(":"))
		hf, mf = (int(x) for x in f.split(":"))
		return max(0, (hf * 60 + mf) - (hd * 60 + md))
	except Exception:
		return 0


def _duree(minutes):
	h, m = divmod(int(minutes), 60)
	return "{0} h {1:02d}".format(h, m) if m else "{0} h".format(h)


def contexte_email(entry, etablissement, items, start, end):
	lignes, jours = _seances(items)
	periode = "du {0} au {1}".format(date_fr(start, annee=start.year != end.year), date_fr(end))
	est_enseignant = bool(entry.get("teacher"))
	classes = sorted({c.strip() for l in lignes for c in l["classes"].split(",") if c.strip()})
	sujet = "{0} – {1} {2}".format(
		etablissement["nom"],
		_("Votre planning de cours") if est_enseignant else _("Planning de cours"),
		periode,
	)
	return {
		"sujet": sujet,
		"destinataire": entry["label"],
		"est_enseignant": est_enseignant,
		"periode": periode,
		"jours": jours,
		"nb_seances": len(lignes),
		"volume": _duree(sum(l["minutes"] for l in lignes)),
		"classes": classes,
		"etablissement": etablissement,
		"editeur": EDITEUR,
		"genere_le": datetime.now().strftime("%d/%m/%Y à %H:%M"),
		"annee": datetime.now().year,
	}
