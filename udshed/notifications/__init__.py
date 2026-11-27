# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Moteur de notifications d'udshed : un point d'entrée unique, `emettre`.

Chaque message appartient à une RÈGLE (DocType « Regle Notification », une par
code du catalogue) qui fixe :
  - ses canaux : dans l'application (Notification Log), e-mail, SMS ;
  - s'il est obligatoire (décision, échéance : non désactivable) ;
  - si l'e-mail du personnel est regroupé dans le résumé quotidien ;
  - les délais de relance et d'escalade (voir `attentes.py`) ;
  - un sujet et un message personnalisables par l'administrateur (Jinja).

Chaque envoi est tracé dans « Journal Notification » ; une clé (`cle`) rend un
envoi idempotent : la même relance n'est jamais envoyée deux fois.

Un envoi ne lève jamais d'exception vers l'appelant : une notification ratée ne
doit pas annuler l'action métier (elle est tracée « Échec » dans le journal).
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, escape_html, get_url, strip_html

from udshed.notifications.catalogue import CATALOGUE

APPLICATION, EMAIL, SMS = "Application", "E-mail", "SMS"
EXCLUS = {"Administrator", "Guest"}


# ---------------------------------------------------------------------- #
#  Règles
# ---------------------------------------------------------------------- #
def regle(code):
	"""Règle active (dict) : base en priorité, sinon valeurs du catalogue."""
	defaut = CATALOGUE.get(code)
	if frappe.db.exists("Regle Notification", code):
		r = frappe.get_cached_doc("Regle Notification", code).as_dict()
		return frappe._dict(r)
	if not defaut:
		return None
	return frappe._dict(valeurs_catalogue(code))


def valeurs_catalogue(code):
	d = CATALOGUE[code]
	canaux = d.get("canaux", (APPLICATION,))
	relance = d.get("relance") or (0, 0, 0)
	return {
		"code": code,
		"libelle": d["libelle"],
		"categorie": d["categorie"],
		"actif": 1,
		"obligatoire": cint(d.get("obligatoire")),
		"canal_application": cint(APPLICATION in canaux),
		"canal_email": cint(EMAIL in canaux),
		"canal_sms": cint(SMS in canaux),
		"email_en_resume": cint(d.get("resume")),
		"delai_relance_jours": relance[0],
		"max_relances": relance[1],
		"escalade_jours": relance[2],
		"destinataires": d.get("destinataires", ""),
		"sujet_personnalise": "",
		"message_personnalise": "",
	}


def synchroniser_catalogue():
	"""Crée les règles manquantes (après migration). Ne touche jamais une règle
	existante : l'administrateur a pu la modifier."""
	for code in CATALOGUE:
		if frappe.db.exists("Regle Notification", code):
			continue
		doc = frappe.get_doc({"doctype": "Regle Notification", **valeurs_catalogue(code)})
		doc.insert(ignore_permissions=True)


# ---------------------------------------------------------------------- #
#  Destinataires
# ---------------------------------------------------------------------- #
def _resoudre(destinataires):
	"""[{user, email, phone, nom}] sans doublon. Accepte des utilisateurs, des
	adresses e-mail ou des dicts déjà résolus."""
	vus, res = set(), []
	for d in destinataires or []:
		if not d:
			continue
		if isinstance(d, dict):
			item = frappe._dict(d)
		elif frappe.db.exists("User", d):
			if d in EXCLUS:
				continue
			u = frappe.db.get_value("User", d, ["name", "email", "mobile_no", "full_name", "enabled"], as_dict=True)
			if not u.enabled:
				continue
			item = frappe._dict(user=u.name, email=u.email, phone=u.mobile_no or _telephone(u.name), nom=u.full_name)
		elif "@" in str(d):
			item = frappe._dict(user=None, email=str(d).strip(), phone=None, nom="")
		else:
			continue
		cle = item.get("user") or (item.get("email") or "").lower()
		if cle and cle not in vus:
			vus.add(cle)
			res.append(item)
	return res


def _telephone(user):
	return (frappe.db.get_value("Student", {"utilisateur": user}, "phone")
			or frappe.db.get_value("Teacher", {"user": user}, "phone"))


def _canaux(r, dest):
	canaux = []
	pref = None
	if dest.get("user") and not r.obligatoire:
		pref = frappe.db.get_value("Preference Notification", {"utilisateur": dest.user, "regle": r.code},
								   ["application", "email", "sms"], as_dict=True)
	def actif(champ_regle, champ_pref):
		return cint(r.get(champ_regle)) and (pref is None or cint(pref.get(champ_pref)))
	if dest.get("user") and actif("canal_application", "application"):
		canaux.append(APPLICATION)
	if dest.get("email") and actif("canal_email", "email"):
		canaux.append(EMAIL)
	if dest.get("phone") and actif("canal_sms", "sms") and sms_configure():
		canaux.append(SMS)
	return canaux


def sms_configure():
	try:
		return bool(frappe.db.get_single_value("SMS Settings", "sms_gateway_url"))
	except Exception:
		return False


# ---------------------------------------------------------------------- #
#  Émission
# ---------------------------------------------------------------------- #
def emettre(code, destinataires, sujet, message=None, *, template=None, args=None, reference=None, lien=None,
			cle=None, relance=0, sender=None, now=False, attachments=None):
	"""Prévient `destinataires` selon la règle `code`. Renvoie le nombre d'envois.

	- `message` : texte ou HTML court (notification et e-mail générique) ;
	- `template` + `args` : gabarit e-mail existant (templates/emails), utilisé
	  tant que l'administrateur n'a pas personnalisé la règle ;
	- `reference` : (doctype, name) du document concerné ;
	- `lien` : écran où agir (chemin relatif ou URL) ;
	- `cle` : rend l'envoi unique par (règle, clé, destinataire, canal).
	"""
	try:
		r = regle(code)
	except Exception:
		frappe.log_error(title=f"udshed: règle de notification {code}")
		return 0
	if not r or not cint(r.actif):
		return 0
	ref_dt, ref_nom = (reference or (None, None))
	url = _url(lien, ref_dt, ref_nom)
	n = 0
	for dest in _resoudre(destinataires):
		ctx = dict(args or {})
		ctx.update(sujet=sujet, message=message or "", lien=url, destinataire=dest.get("nom") or "",
				   reference_doctype=ref_dt, reference_name=ref_nom)
		s, m, tpl = _contenu(r, sujet, message, template, ctx)
		for canal in _canaux(r, dest):
			cible = dest.get("phone") if canal == SMS else (dest.get("user") or dest.get("email"))
			if cle and frappe.db.exists("Journal Notification",
										 {"regle": code, "cle": cle, "destinataire": cible, "canal": canal}):
				continue
			statut, erreur = "Envoyé", None
			try:
				if canal == APPLICATION:
					_application(dest.user, s, m, url, ref_dt, ref_nom)
				elif canal == EMAIL:
					if cint(r.email_en_resume) and dest.get("user"):
						statut = "En attente du résumé"
					else:
						_email(dest.email, s, m, tpl, ctx, url, ref_dt, ref_nom, sender, now, attachments)
				else:
					_sms(dest.phone, s, url)
			except Exception as e:
				statut, erreur = "Échec", str(e)[:500]
				frappe.log_error(title=f"udshed: notification {code} ({canal})")
			_journal(code, canal, cible, dest.get("user"), s, m, statut, erreur, cle, relance, ref_dt, ref_nom, url)
			n += statut != "Échec"
	return n


def _contenu(r, sujet, message, template, ctx):
	"""(sujet, message, gabarit) : la personnalisation de l'administrateur l'emporte."""
	s, m, tpl = sujet, message, template
	try:
		if (r.get("sujet_personnalise") or "").strip():
			s = frappe.render_template(r.sujet_personnalise, ctx)
		if (r.get("message_personnalise") or "").strip():
			m, tpl = frappe.render_template(r.message_personnalise, ctx), None
	except Exception:
		frappe.log_error(title=f"udshed: gabarit personnalisé invalide ({r.code})")
	return s, m, tpl


def _url(lien, ref_dt, ref_nom):
	if lien:
		return lien if lien.startswith("http") else get_url(lien)
	if ref_dt and ref_nom:
		return get_url(f"/app/{frappe.scrub(ref_dt).replace('_', '-')}/{ref_nom}")
	return get_url("/app")


def _application(user, sujet, message, url, ref_dt, ref_nom):
	doc = {"doctype": "Notification Log", "for_user": user, "type": "Alert", "subject": strip_html(sujet)[:140],
		   "email_content": message or ""}
	chemin = re.sub(r"^https?://[^/]+", "", url or "")
	if ref_dt and ref_nom and not chemin.startswith(("/app/mon-espace", "/desk/")):
		doc.update(document_type=ref_dt, document_name=ref_nom)
	else:
		doc["link"] = chemin or None
	frappe.get_doc(doc).insert(ignore_permissions=True)


def _email(email, sujet, message, template, ctx, url, ref_dt, ref_nom, sender, now, attachments):
	options = dict(recipients=[email], subject=strip_html(sujet), reference_doctype=ref_dt, reference_name=ref_nom,
				   now=now, delayed=not now, attachments=attachments)
	if sender:
		options["sender"] = sender
	if template:
		options.update(template=template, args=ctx)
	else:
		options.update(template="udshed_notification", args={**ctx, "message": message or "", "lien": url})
	frappe.sendmail(**options)


def _sms(phone, sujet, url):
	from frappe.core.doctype.sms_settings.sms_settings import send_sms

	texte = strip_html(sujet)
	if url:
		texte = f"{texte} {url}"
	send_sms([phone], texte[:300], success_msg=False)


def _journal(code, canal, cible, user, sujet, message, statut, erreur, cle, relance, ref_dt, ref_nom, url):
	try:
		frappe.get_doc({
			"doctype": "Journal Notification", "regle": code, "canal": canal, "destinataire": cible,
			"utilisateur": user, "sujet": strip_html(sujet)[:140], "message": message or "", "statut": statut,
			"erreur": erreur, "cle": cle, "relance": relance, "reference_doctype": ref_dt,
			"reference_name": ref_nom, "lien": url,
		}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="udshed: journal de notification")


# ---------------------------------------------------------------------- #
#  Résumé quotidien (e-mails du personnel regroupés)
# ---------------------------------------------------------------------- #
def envoyer_resumes():
	lignes = frappe.get_all("Journal Notification", filters={"statut": "En attente du résumé"},
							fields=["name", "utilisateur", "destinataire", "sujet", "lien", "creation"],
							order_by="creation asc")
	par_user = {}
	for l in lignes:
		par_user.setdefault((l.utilisateur, l.destinataire), []).append(l)
	for (user, email), items in par_user.items():
		try:
			frappe.sendmail(
				recipients=[email], subject=_("Votre résumé udshed : {0} élément(s) à suivre").format(len(items)),
				template="udshed_resume", args={"items": items, "lien": get_url("/desk/accueil-udshed")}, delayed=True)
			statut = "Regroupé"
		except Exception:
			frappe.log_error(title="udshed: résumé quotidien")
			statut = "Échec"
		for it in items:
			frappe.db.set_value("Journal Notification", it.name, "statut", statut, update_modified=False)
	return len(par_user)


def nom_affiche(user):
	return frappe.db.get_value("User", user, "full_name") or user


def html_liste(lignes):
	return "<ul>" + "".join(f"<li>{escape_html(str(l))}</li>" for l in lignes) + "</ul>"
