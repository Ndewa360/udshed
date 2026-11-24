# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from udshed.api.candidature import (
	_nettoyer_telephone,
	get_school_logo_url,
	jeton_fiche_candidature,
	poser_cookie_fiche,
)
from udshed.utils import securite


class SessionInscriptionCandidate(Document):

	def before_insert(self):
		if self.last_name:
			self.last_name = self.last_name.upper().strip()
		if self.first_name:
			self.first_name = self.first_name.upper().strip()
		modele_full_name = 'f"{first_name} {last_name}"'
		if not self.full_name or self.full_name == modele_full_name:
			self.full_name = " ".join(filter(None, [self.first_name, self.last_name]))
		# Champs absents du formulaire de candidature : on retire les valeurs par
		# défaut (Frappe applique la 1re option d'un Select et les defaults du
		# doctype) afin que le dossier soit vierge tant que ces infos ne sont pas
		# réellement renseignées.
		valeur_par_defaut = {
			"nationality": "CM",
			"religion": "CHRÉTIEN",
			"employment_status": "SANS EMPLOI",
			"marital_status": "CELIBATAIRE",
			"language": "FR",
			"handicap": "NON",
			"father_country": "CM",
			"mother_country": "CM",
			"sponsor_country": "CM",
			"entry_diploma": "BAC",
		}
		for champ, defaut in valeur_par_defaut.items():
			if self.get(champ) == defaut:
				self.set(champ, "")
		self.status_updated_on = frappe.utils.now_datetime()
		if not self.session_inscription:
			self.session_inscription = self._session_inscription_courante()

	def validate(self):
		for champ in ("phone", "parent_phone", "father_phone", "mother_phone", "sponsor_phone"):
			valeur = getattr(self, champ, None)
			if valeur:
				setattr(self, champ, _nettoyer_telephone(valeur))
		self._deduire_filiere_niveau_des_choix()
		self._proteger_statut_accepte()
		if self.candidature_status == "Refusé" and not (self.status_comment or "").strip():
			frappe.throw(_("Le motif du rejet est obligatoire pour un statut « Refusé »."))

	def _deduire_filiere_niveau_des_choix(self):
		"""Le formulaire ne collecte plus filière/niveau en haut de page : on les
		déduit donc du 1er choix. À la création on écrase les valeurs par défaut
		(frappe met automatiquement la 1re option d'un champ Select), ensuite on ne
		complète que si le dossier est encore vide."""
		if not self.is_new() and self.get("filiere") and self.get("niveau"):
			return
		rows = self.get("choix_de_formation") or []
		if not rows:
			return
		premier = rows[0]
		if premier.get("filiere") and (self.is_new() or not self.get("filiere")):
			self.filiere = premier.get("filiere")
		niveau_name = premier.get("niveau")
		if niveau_name and (self.is_new() or not self.get("niveau")):
			niveau_label = frappe.db.get_value(
				"Field of study Level", niveau_name, "level"
			)
			self.niveau = niveau_label or niveau_name

	def _session_inscription_courante(self):
		"""Retourne la session d'inscription ouverte, sinon la plus récente."""
		ouverte = frappe.db.exists("Session Inscription", {"status": "Open"})
		if ouverte:
			return ouverte
		recente = frappe.db.get_value(
			"Session Inscription",
			{},
			"name",
			order_by="creation desc",
		)
		return recente

	def after_insert(self):
		# Le candidat (invité) qui vient de soumettre peut télécharger SA fiche
		# depuis /candidature-success, sans exposer les fiches des autres.
		if frappe.session.user == "Guest":
			poser_cookie_fiche(self.name)
		self._send_candidate_email()
		self._send_coordinator_email()

	def on_update(self):
		old_doc = self.get_doc_before_save()
		if not old_doc:
			return
		if old_doc.candidature_status == self.candidature_status:
			return
		frappe.db.set_value(
			"Session Inscription Candidate",
			self.name,
			"status_updated_on",
			frappe.utils.now_datetime(),
			update_modified=False,
		)
		if self.candidature_status == "Accepté":
			_send_confirmation_email(self)
		elif self.candidature_status == "Refusé":
			_send_rejection_email(self, (self.status_comment or "").strip())
		elif self.candidature_status == "Inscrit":
			_send_validation_email(self)

	def _proteger_statut_accepte(self):
		"""Une fois une candidature acceptée, son statut ne peut plus être modifié,
		excepté son passage à « Inscrit » lors de la finalisation de l'inscription."""
		if not self.get("name"):
			return
		old_doc = self.get_doc_before_save()
		if not old_doc:
			return
		old_status = old_doc.candidature_status
		if old_status in ("Accepté", "Inscrit") and self.candidature_status != old_status:
			frappe.throw(
				_(
					"Le statut d'une candidature déjà {0} est verrouillé et ne peut plus être modifié."
				).format(old_status)
			)

	def _send_candidate_email(self):
		if not self.email:
			frappe.logger().warning(
				f"Impossible d'envoyer l'accusé de réception : aucun e-mail renseigné pour le candidat {self.name}"
			)
			return

		setting = frappe.get_single("Udshed Setting")
		subject = getattr(setting, "email_candidature_subject", None) or _(
			"Accusé de réception de votre candidature - UDSHED"
		)
		sender = _get_sender()

		try:
			frappe.sendmail(
				recipients=[self.email],
				sender=sender,
				subject=_(subject),
				template="candidature_receipt",
				args={
					"first_name": self.first_name,
					"last_name": self.last_name,
					"doc_name": self.name,
					"jeton_fiche": jeton_fiche_candidature(self.name),
					"niveau": self.niveau or "",
					"filiere": self.filiere or "",
					"base_url": frappe.utils.get_url(),
					"logo_url": get_school_logo_url(),
				},
				now=True,
			)
			frappe.logger().info(f"Email accusé de réception envoyé à {self.email} pour {self.name}")
		except Exception as e:
			frappe.log_error(
				message=str(e),
				title=f"Échec envoi e-mail candidat {self.name}",
			)

	def _send_coordinator_email(self):
		setting = frappe.get_single("Udshed Setting")
		coord_email = getattr(setting, "email_coordinateur", None)
		if not coord_email:
			frappe.logger().info("Pas d'email coordonnateur configuré — notification non envoyée.")
			return

		sender = _get_sender()

		choix_text = ""
		if self.choix_de_formation:
			lignes = []
			for row in self.choix_de_formation:
				lignes.append(
					f"<li>{row.get('choix', '')} — {row.get('filiere', '')} ({row.get('niveau', '')})</li>"
				)
			choix_text = "<ul>" + "".join(lignes) + "</ul>"

		try:
			frappe.sendmail(
				recipients=[coord_email],
				sender=sender,
				subject=_("Nouvelle candidature reçue - {0} {1} ({2})").format(
					self.first_name, self.last_name, self.name
				),
				template="candidature_notification_coordinator",
				args={
					"first_name": self.first_name,
					"last_name": self.last_name,
					"doc_name": self.name,
					"email": self.email or "",
					"phone": self.phone or "",
					"niveau": self.niveau or "",
					"filiere": self.filiere or "",
					"examination_centre": self.examination_centre or "",
					"choix_text": choix_text,
					"birth_place": self.birth_place or "",
					"sexe": self.sexe or "",
					"logo_url": get_school_logo_url(),
				},
				now=True,
			)
			frappe.logger().info(
				f"Notification coordonnateur envoyée à {coord_email} pour la candidature {self.name}"
			)
		except Exception as e:
			frappe.log_error(
				message=str(e),
				title=f"Échec notification coordonnateur pour {self.name}",
			)


@frappe.whitelist(allow_guest=True)
def track_candidature(doc_name: str) -> dict:
	"""Rechercher une candidature par son numéro et retourner les infos de suivi.

	Accès public (allow_guest) — utilisé par la page /suivi-candidature.
	Seuls les champs utiles au suivi sont renvoyés.
	"""
	if not doc_name:
		frappe.throw(_("Veuillez saisir un numéro de dossier."))

	doc_name = doc_name.strip().upper()

	# Freine l'énumération des numéros de dossier (séquentiels).
	ip = securite.ip_client()
	securite.verifier_tentatives("suivi-candidature", ip, 30, 15 * 60)
	if not frappe.db.exists("Session Inscription Candidate", doc_name):
		securite.enregistrer_echec("suivi-candidature", ip, 15 * 60)

	doc = frappe.db.get_value(
		"Session Inscription Candidate",
		doc_name,
		[
			"name",
			"first_name",
			"last_name",
			"email",
			"niveau",
			"filiere",
			"examination_centre",
			"candidature_status",
			"status_updated_on",
			"status_comment",
			"creation",
		],
		as_dict=True,
	)

	if not doc:
		frappe.throw(
			_("Aucune candidature trouvée avec le numéro <b>{0}</b>.").format(doc_name)
		)

	return {
		"doc_name": doc.name,
		"first_name": doc.first_name,
		"last_name": doc.last_name,
		"niveau": doc.niveau or "",
		"filiere": doc.filiere or "",
		"examination_centre": doc.examination_centre or "",
		"status": doc.candidature_status or "En attente",
		"status_date": frappe.utils.format_datetime(doc.status_updated_on, "dd/MM/yyyy HH:mm")
			if doc.status_updated_on
			else frappe.utils.format_datetime(doc.creation, "dd/MM/yyyy HH:mm"),
		"status_comment": doc.status_comment or "",
		"submitted_on": frappe.utils.format_datetime(doc.creation, "dd/MM/yyyy HH:mm"),
	}


@frappe.whitelist(allow_guest=True)
def get_session_status() -> dict:
	"""Retourne le statut de la dernière Session Inscription active.

	Utilisé dynamiquement sur la page d'accueil pour afficher
	'Ouverte', 'Fermée' ou 'Brouillon'.
	"""
	session = frappe.db.get_value(
		"Session Inscription",
		{},
		["name", "status", "academic_year"],
		order_by="creation desc",
		as_dict=True,
	)

	if not session:
		return {"status": "Aucune", "academic_year": "", "label": "Aucune session disponible"}

	status_map = {
		"Open": {"label": "Session {year} ouverte", "css_class": "open"},
		"Closed": {"label": "Session {year} fermée", "css_class": "closed"},
		"Draft": {"label": "Session {year} — brouillon", "css_class": "draft"},
	}

	info = status_map.get(session.status, {"label": "Session {year}", "css_class": "draft"})
	year = session.academic_year or ""

	return {
		"status": session.status,
		"academic_year": year,
		"label": info["label"].format(year=year),
		"css_class": info["css_class"],
	}


# ---------------------------------------------------------------------------
# Dashboard API — Consultation des candidatures
# ---------------------------------------------------------------------------

def _build_filters(session=None, filiere=None, niveau=None, centre=None, statut=None):
	"""Construit les filtres pour les requêtes dashboard."""
	filters = {}
	if session:
		filters["session_inscription"] = session
	if filiere:
		filters["filiere"] = filiere
	if niveau:
		filters["niveau"] = niveau
	if centre:
		filters["examination_centre"] = centre
	if statut:
		filters["candidature_status"] = statut
	return filters


@frappe.whitelist()
def get_candidate_dashboard_stats(
	session=None, filiere=None, niveau=None, centre=None, statut=None
):
	"""Retourne les compteurs pour les cartes stats du dashboard."""
	securite.exiger_personnel()
	securite.exiger_permission("Session Inscription Candidate", "read")
	filters = _build_filters(session, filiere, niveau, centre, statut)

	counts = {}
	for label, status_val in [
		("total", None),
		("en_attente", "En attente"),
		("en_cours", "Dossier en cours d'examen"),
		("accepte", "Accepté"),
		("refuse", "Refusé"),
		("inscrit", "Inscrit"),
	]:
		if status_val:
			counts[label] = frappe.db.count(
				"Session Inscription Candidate",
				{**filters, "candidature_status": status_val},
			)
		else:
			counts[label] = frappe.db.count("Session Inscription Candidate", filters)

	return counts


@frappe.whitelist()
def get_candidates_list(
	session=None, filiere=None, niveau=None, centre=None,
	statut=None, start=0, limit=20,
):
	"""Liste paginée des candidats avec infos clés."""
	securite.exiger_personnel()
	securite.exiger_permission("Session Inscription Candidate", "read")
	filters = _build_filters(session, filiere, niveau, centre, statut)

	docs = frappe.get_all(
		"Session Inscription Candidate",
		filters=filters,
		fields=[
			"name", "first_name", "last_name", "filiere", "niveau",
			"examination_centre", "candidature_status", "creation",
			"session_inscription",
		],
		order_by="session_inscription asc, creation desc",
		start=start,
		limit_page_length=limit,
	)

	for d in docs:
		d.filiere_label = (
			frappe.db.get_value("Field of study", d.filiere, "name_of_field") or d.filiere
			if d.filiere else ""
		)
		d.submitted_on = frappe.utils.format_datetime(d.creation, "dd/MM/yyyy")
		d.session_label = (
			frappe.db.get_value("Session Inscription", d.session_inscription, "academic_year")
			if d.session_inscription else ""
		)

	total = frappe.db.count("Session Inscription Candidate", filters)
	return {"candidates": docs, "total": total}


@frappe.whitelist()
def get_candidate_detail(name):
	"""Détail complet d'un candidat (y compris child tables)."""
	securite.exiger_personnel()
	doc = frappe.get_doc("Session Inscription Candidate", name)
	securite.exiger_permission("Session Inscription Candidate", "read", doc=doc)

	choix = []
	for row in doc.choix_de_formation:
		filiere_label = frappe.db.get_value("Field of study", row.filiere, "name_of_field") if row.filiere else ""
		choix.append({"choix": row.choix, "filiere": filiere_label, "niveau": row.niveau})

	diplomes = []
	for row in doc.diplome_formation:
		diplomes.append({
			"diplome": row.diplome,
			"year": row.year,
			"serie": row.serie__field_of_study,
			"lieu": row.place_of_acquisition,
			"mention": row.mention,
		})

	return {
		"name": doc.name,
		"first_name": doc.first_name,
		"last_name": doc.last_name,
		"full_name": doc.full_name,
		"birthdate": frappe.utils.format_date(doc.birthdate) if doc.birthdate else "",
		"birth_place": doc.birth_place or "",
		"sexe": doc.sexe or "",
		"phone": doc.phone or "",
		"email": doc.email or "",
		"parent_phone": doc.parent_phone or "",
		"email_parent": doc.email_parent or "",
		"home_city": doc.home_city or "",
		"filiere": doc.filiere or "",
		"filiere_label": (
			frappe.db.get_value("Field of study", doc.filiere, "name_of_field")
			if doc.filiere else ""
		),
		"niveau": doc.niveau or "",
		"examination_centre": doc.examination_centre or "",
		"choix_de_formation": choix,
		"diplome_formation": diplomes,
		"birth_certificate": doc.birth_certificate or "",
		"access_diploma_copy": doc.access_diploma_copy or "",
		"id_photo": doc.id_photo or "",
		"remittance_receipt": doc.remittance_receipt or "",
		"candidature_status": doc.candidature_status or "En attente",
		"status_updated_on": (
			frappe.utils.format_datetime(doc.status_updated_on, "dd/MM/yyyy HH:mm")
			if doc.status_updated_on else ""
		),
		"status_comment": doc.status_comment or "",
		"submitted_on": frappe.utils.format_datetime(doc.creation, "dd/MM/yyyy HH:mm"),
	}


@frappe.whitelist()
def update_candidate_status(name, new_status, comment=None):
	"""Change le statut d'un candidat. Motif obligatoire si Refusé."""
	if new_status == "Refusé" and not comment:
		frappe.throw(_("Le motif du rejet est obligatoire."))

	securite.exiger_personnel()
	doc = frappe.get_doc("Session Inscription Candidate", name)
	securite.exiger_permission("Session Inscription Candidate", "write", doc=doc)
	old_status = doc.candidature_status

	doc.candidature_status = new_status
	if comment:
		doc.status_comment = comment
	doc.status_updated_on = frappe.utils.now_datetime()
	doc.save()

	# Les emails (confirmation / rejet / validation) sont envoyés dans on_update

	return {"ok": True, "old_status": old_status, "new_status": new_status}


# ---------------------------------------------------------------------------
# Emails — Confirmation + Validation
# ---------------------------------------------------------------------------

def _get_sender():
	"""Return the formatted sender name from Udshed Setting."""
	setting = frappe.get_single("Udshed Setting")
	sender_name = getattr(setting, "email_candidature_sender_name", None) or "Udshed"
	email_account = frappe.db.get_value("Email Account", {"default_outgoing": 1}, "email_id")
	if email_account:
		return f"{sender_name} <{email_account}>"
	return None


def _send_confirmation_email(doc):
	"""Email envoyé au candidat quand sa candidature est Acceptée."""
	if not doc.email:
		frappe.logger().warning(
			f"Pas d'email pour {doc.name} — email confirmation non envoyé."
		)
		return

	sender = _get_sender()
	academic_year = frappe.db.get_value(
		"Session Inscription", {}, "academic_year", order_by="creation desc"
	) or ""
	filiere_label = frappe.db.get_value("Field of study", doc.filiere, "name_of_field") if doc.filiere else ""

	try:
		frappe.sendmail(
			recipients=[doc.email],
			sender=sender,
			subject=_("Félicitations, votre candidature a été acceptée - Udshed"),
			template="candidature_confirmation",
			args={
				"first_name": doc.first_name,
				"last_name": doc.last_name,
				"doc_name": doc.name,
				"academic_year": academic_year,
				"filiere": filiere_label,
				"niveau": doc.niveau or "",
				"centre": doc.examination_centre or "",
				"logo_url": get_school_logo_url(),
			},
			now=True,
		)
		frappe.logger().info(f"Email confirmation envoyé à {doc.email} pour {doc.name}")
	except Exception as e:
		frappe.log_error(
			message=str(e), title=f"Échec email confirmation {doc.name}"
		)


def _send_validation_email(doc):
	"""Email envoyé au candidat quand son inscription est validée."""
	if not doc.email:
		frappe.logger().warning(
			f"Pas d'email pour {doc.name} — email validation non envoyé."
		)
		return

	setting = frappe.get_single("Udshed Setting")
	school_name = getattr(setting, "school_name", "UDSHED")
	sender = _get_sender()
	academic_year = frappe.db.get_value(
		"Session Inscription", {}, "academic_year", order_by="creation desc"
	)
	filiere_label = frappe.db.get_value("Field of study", doc.filiere, "name_of_field") if doc.filiere else ""

	uv_liste = ""
	matricule = ""
	student_name = frappe.db.get_value("Student", {"email": doc.email}, "name")
	if student_name:
		matricule = frappe.db.get_value("Student", student_name, "matricule") or student_name
		uv_records = frappe.get_all(
			"Session Examen Note",
			filters={"student": student_name},
			fields=["teaching_unit"],
			pluck="teaching_unit",
		)
		if uv_records:
			uv_labels = []
			for tu_name in uv_records:
				course = frappe.db.get_value("Teaching Unit", tu_name, "course")
				if course:
					uv_labels.append(course)
			uv_liste = ", ".join(uv_labels)

	try:
		frappe.sendmail(
			recipients=[doc.email],
			sender=sender,
			subject=_("Inscription validée - {0}").format(school_name),
			template="candidature_validation",
			args={
				"first_name": doc.first_name,
				"last_name": doc.last_name,
				"doc_name": doc.name,
				"matricule": matricule,
				"filiere": filiere_label,
				"niveau": doc.niveau or "",
				"centre": doc.examination_centre or "",
				"school_name": school_name,
				"academic_year": academic_year or "",
				"uv_liste": uv_liste,
				"logo_url": get_school_logo_url(),
			},
			now=True,
		)
		frappe.logger().info(f"Email validation envoyé à {doc.email} pour {doc.name}")
	except Exception as e:
		frappe.log_error(
			message=str(e), title=f"Échec email validation {doc.name}"
		)


def _send_rejection_email(doc, motif=None):
	"""Email envoyé au candidat quand sa candidature est Refusée."""
	if not doc.email:
		frappe.logger().warning(
			f"Pas d'email pour {doc.name} — email rejet non envoyé."
		)
		return

	sender = _get_sender()
	academic_year = frappe.db.get_value(
		"Session Inscription", {}, "academic_year", order_by="creation desc"
	) or ""
	filiere_label = frappe.db.get_value("Field of study", doc.filiere, "name_of_field") if doc.filiere else ""

	motif = (motif or doc.status_comment or "").strip()

	try:
		frappe.sendmail(
			recipients=[doc.email],
			sender=sender,
			subject=_("Résultat de votre candidature"),
			template="candidature_rejection",
			args={
				"first_name": doc.first_name,
				"last_name": doc.last_name,
				"doc_name": doc.name,
				"academic_year": academic_year,
				"filiere": filiere_label,
				"niveau": doc.niveau or "",
				"motif": motif,
				"logo_url": get_school_logo_url(),
			},
			now=True,
		)
		frappe.logger().info(f"Email rejet envoyé à {doc.email} pour {doc.name}")
	except Exception as e:
		frappe.log_error(
			message=str(e), title=f"Échec email rejet {doc.name}"
		)
