# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _


class SessionInscriptionCandidate(Document):

	def before_insert(self):
		if self.last_name:
			self.last_name = self.last_name.upper().strip()
		if self.first_name:
			self.first_name = self.first_name.upper().strip()
		self.status_updated_on = frappe.utils.now_datetime()

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

	def _get_sender(self):
		"""Return the formatted sender name from Udshed Setting."""
		setting = frappe.get_single("Udshed Setting")
		sender_name = getattr(setting, "email_candidature_sender_name", None) or "UDSHED"
		email_account = frappe.db.get_value("Email Account", {"default_outgoing": 1}, "email_id")
		if email_account:
			return f"{sender_name} <{email_account}>"
		return None

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
		sender = self._get_sender()

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

		sender = self._get_sender()

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
