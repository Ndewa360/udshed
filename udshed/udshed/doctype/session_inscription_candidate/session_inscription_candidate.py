# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from udshed.api.candidature import _nettoyer_telephone


class SessionInscriptionCandidate(Document):

	def before_insert(self):
		if self.last_name:
			self.last_name = self.last_name.upper().strip()
		if self.first_name:
			self.first_name = self.first_name.upper().strip()
		self.status_updated_on = frappe.utils.now_datetime()
		if not self.session_inscription:
			self.session_inscription = self._session_inscription_courante()

	def validate(self):
		for champ in ("phone", "parent_phone", "father_phone", "mother_phone", "sponsor_phone"):
			valeur = getattr(self, champ, None)
			if valeur:
				setattr(self, champ, _nettoyer_telephone(valeur))
		self._proteger_statut_accepte()

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
		self._send_candidate_email()
		self._send_coordinator_email()

	def on_update(self):
		if self.has_value_changed("candidature_status"):
			frappe.db.set_value(
				"Session Inscription Candidate",
				self.name,
				"status_updated_on",
				frappe.utils.now_datetime(),
				update_modified=False,
			)

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
					"niveau": self.niveau or "",
					"filiere": self.filiere or "",
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
	doc = frappe.get_doc("Session Inscription Candidate", name)

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

	doc = frappe.get_doc("Session Inscription Candidate", name)
	old_status = doc.candidature_status

	doc.candidature_status = new_status
	if comment:
		doc.status_comment = comment
	doc.status_updated_on = frappe.utils.now_datetime()
	doc.save()

	if new_status == "Accepté" and old_status != "Accepté":
		_send_confirmation_email(doc)

	if new_status == "Inscrit" and old_status != "Inscrit":
		_send_validation_email(doc)

	if new_status == "Refusé":
		_send_rejection_email(doc, comment)

	return {"ok": True, "old_status": old_status, "new_status": new_status}


# ---------------------------------------------------------------------------
# Emails — Confirmation + Validation
# ---------------------------------------------------------------------------

def _get_sender():
	"""Return the formatted sender name from Udshed Setting."""
	setting = frappe.get_single("Udshed Setting")
	sender_name = getattr(setting, "email_candidature_sender_name", None) or "UDSHED"
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

	setting = frappe.get_single("Udshed Setting")
	school_name = getattr(setting, "school_name", "UDSHED")
	sender = _get_sender()

	frappe.sendmail(
		recipients=[doc.email],
		sender=sender,
		subject=_("Félicitations"),
		message=_("Félicitations, votre candidature a été acceptée."),
		now=True,
	)
	frappe.logger().info(f"Email confirmation envoyé à {doc.email} pour {doc.name}")


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

	setting = frappe.get_single("Udshed Setting")
	school_name = getattr(setting, "school_name", "UDSHED")
	sender = _get_sender()
	academic_year = frappe.db.get_value(
		"Session Inscription", {}, "academic_year", order_by="creation desc"
	)
	filiere_label = frappe.db.get_value("Field of study", doc.filiere, "name_of_field") if doc.filiere else ""

	motif_message = motif or ""

	subject = _("Résultat de votre candidature")
	message = _("Désolée, votre candidature a été rejetée.")
	if motif_message:
		message += "\n\n" + _("Motif du rejet : {0}").format(motif_message)

	try:
		frappe.sendmail(
			recipients=[doc.email],
			sender=sender,
			subject=subject,
			message=message,
			now=True,
		)
		frappe.logger().info(f"Email rejet envoyé à {doc.email} pour {doc.name}")
	except Exception as e:
		frappe.log_error(
			message=str(e), title=f"Échec email rejet {doc.name}"
		)


# ---------------------------------------------------------------------------
# Login + Inscription (page /inscription)
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def login_inscription(doc_name: str, password: str) -> dict:
	"""Authentifie un candidat pour finaliser son inscription.

	Identifiant = numéro de dossier (CAND-YYYY-#####)
	Mot de passe = date de naissance (YYYYMMDD)
	"""
	if not doc_name or not password:
		frappe.throw(_("Veuillez remplir tous les champs."))

	doc_name = doc_name.strip().upper()

	doc = frappe.db.get_value(
		"Session Inscription Candidate",
		doc_name,
		["name", "first_name", "last_name", "filiere", "niveau",
		 "candidature_status", "birthdate", "email", "phone", "sexe",
		 "birth_place", "nationality", "examination_centre", "religion",
		 "employment_status", "marital_status", "language", "handicap", "home_city",
		 "father_name", "father_phone", "father_profession", "father_email", "father_city", "father_country",
		 "mother_name", "mother_phone", "mother_profession", "mother_email", "mother_city", "mother_country",
		 "sponsor_name", "sponsor_phone", "sponsor_profession", "sponsor_email", "sponsor_city", "sponsor_country",
		 "last_establishment", "entry_diploma", "diploma_matricule",
		 "sports_activities", "associative_activities", "cultural_activities", "it_knowledge",
		 "email_parent"],
		as_dict=True,
	)

	if not doc:
		frappe.throw(
			_("Aucune candidature trouvée avec le numéro <b>{0}</b>.").format(doc_name)
		)

	if doc.candidature_status not in ("Accepté", "Inscrit"):
		frappe.throw(
			_("Votre candidature n'est pas encore acceptée. Statut actuel : {0}").format(
				doc.candidature_status
			)
		)

	if not doc.birthdate:
		frappe.throw(_("Aucune date de naissance enregistrée."))

	expected_password = frappe.utils.format_date(doc.birthdate, "YYYYMMDD")
	if password != expected_password:
		frappe.throw(_("Mot de passe incorrect."))

	filiere_label = frappe.db.get_value("Field of study", doc.filiere, "name_of_field") if doc.filiere else ""

	return {
		"ok": True,
		"doc_name": doc.name,
		"first_name": doc.first_name or "",
		"last_name": doc.last_name or "",
		"filiere": doc.filiere or "",
		"filiere_label": filiere_label,
		"niveau": doc.niveau or "",
		"candidature_status": doc.candidature_status,
		"email": doc.email or "",
		"phone": doc.phone or "",
		"sexe": doc.sexe or "",
		"birthdate": frappe.utils.format_date(doc.birthdate) if doc.birthdate else "",
		"birth_place": doc.birth_place or "",
		"nationality": doc.nationality or "",
		"examination_centre": doc.examination_centre or "",
		"religion": doc.religion or "",
		"employment_status": doc.employment_status or "",
		"marital_status": doc.marital_status or "",
		"language": doc.language or "",
		"handicap": doc.handicap or "",
		"home_city": doc.home_city or "",
		"father_name": doc.father_name or "",
		"father_phone": doc.father_phone or "",
		"father_profession": doc.father_profession or "",
		"father_email": doc.father_email or "",
		"father_city": doc.father_city or "",
		"father_country": doc.father_country or "",
		"mother_name": doc.mother_name or "",
		"mother_phone": doc.mother_phone or "",
		"mother_profession": doc.mother_profession or "",
		"mother_email": doc.mother_email or "",
		"mother_city": doc.mother_city or "",
		"mother_country": doc.mother_country or "",
		"sponsor_name": doc.sponsor_name or "",
		"sponsor_phone": doc.sponsor_phone or "",
		"sponsor_profession": doc.sponsor_profession or "",
		"sponsor_email": doc.sponsor_email or "",
		"sponsor_city": doc.sponsor_city or "",
		"sponsor_country": doc.sponsor_country or "",
		"last_establishment": doc.last_establishment or "",
		"entry_diploma": doc.entry_diploma or "",
		"diploma_matricule": doc.diploma_matricule or "",
		"sports_activities": doc.sports_activities or "",
		"associative_activities": doc.associative_activities or "",
		"cultural_activities": doc.cultural_activities or "",
		"it_knowledge": doc.it_knowledge or "",
		"email_parent": doc.email_parent or "",
	}


@frappe.whitelist(allow_guest=True)
def submit_inscription(doc_name: str, data: str) -> dict:
	"""Finalise l'inscription d'un candidat accepté (flux page /inscription).

	Délègue à la fonction unifiée dans inscription.py pour éviter la duplication.
	"""
	from udshed.udshed.api.inscription import _finaliser_inscription_complete

	if not doc_name:
		frappe.throw(_("Numéro de dossier manquant."))

	import json as _json
	if isinstance(data, str):
		data = _json.loads(data)

	doc_name = doc_name.strip().upper()
	candidate = frappe.get_doc("Session Inscription Candidate", doc_name)

	if candidate.candidature_status != "Accepté":
		frappe.throw(_("Seules les candidatures acceptées peuvent finaliser l'inscription."))

	# Préparer les données pour la finalisation unifiée
	donnees = {
		"annee_academique": data.get("annee_academique"),
		"sexe": data.get("sexe"),
		"nationalite": data.get("nationalite"),
		"region_origine": data.get("region_origine"),
		"langue": data.get("langue"),
		"religion": data.get("religion"),
		"situation_matrimoniale": data.get("situation_matrimoniale"),
		"situatio_emploi": data.get("situatio_emploi"),
		"handicape": data.get("handicape"),
		"nom_prenom_pere": data.get("nom_prenom_pere"),
		"pere_telephone": data.get("pere_telephone"),
		"pere_profession": data.get("pere_profession"),
		"pere_ville": data.get("pere_ville"),
		"nom_prenom_mere": data.get("nom_prenom_mere"),
		"telephone_mere": data.get("telephone_mere"),
		"profession_mere": data.get("profession_mere"),
		"mere_ville": data.get("mere_ville"),
		"nom_prenom_sponsor": data.get("nom_prenom_sponsor"),
		"telephone_sponsor": data.get("telephone_sponsor"),
		"profession_sponsor": data.get("profession_sponsor"),
		"sponsor_ville": data.get("sponsor_ville"),
		"dernier_etablissement": data.get("dernier_etablissement"),
		"diplome_entree": data.get("diplome_entree"),
		"matricule_diplome": data.get("matricule_diplome"),
		"activites_sportives": data.get("activites_sportives"),
		"activites_associatives": data.get("activites_associatives"),
		"activites_culturelles": data.get("activites_culturelles"),
		"connaissances_informatiques": data.get("connaissances_informatiques"),
	}

	result = _finaliser_inscription_complete(candidate, donnees)

	# Format de retour compatible avec l'ancien code
	if result.get("already_registered"):
		# Déjà inscrit, récupérer infos pour le retour
		student_name = frappe.db.get_value("Student", {"email": candidate.email}, "name")
		enrolled = frappe.get_all(
			"Academic Reregistration",
			filters={"student": student_name, "academic_year": frappe.db.get_single_value("Udshed Setting", "current_year")},
			fields=["cours_inscrits"],
			pluck="cours_inscrits",
		)
		enrolled_tus = [item.teaching_unit for sublist in enrolled for item in sublist] if enrolled else []
	else:
		enrolled_tus = []
		student_name = result.get("student_name")

	filiere_label = frappe.db.get_value("Field of study", candidate.filiere, "name_of_field") if candidate.filiere else ""

	return {
		"ok": True,
		"student_name": student_name,
		"matricule": result.get("matricule"),
		"first_name": candidate.first_name or "",
		"last_name": candidate.last_name or "",
		"filiere_label": filiere_label,
		"niveau": candidate.niveau or "",
		"centre": candidate.examination_centre or "",
		"semestre_courses": {},
		"enrolled_uv": result.get("enrolled_count", len(enrolled_tus)),
	}
