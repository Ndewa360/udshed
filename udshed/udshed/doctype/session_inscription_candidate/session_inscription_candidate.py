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

	def after_insert(self):
		self.send_receipt_email()

	def send_receipt_email(self):
		if not self.email:
			frappe.logger().warning(
				f"Impossible d'envoyer l'accusé de réception : aucun e-mail renseigné pour le candidat {self.name}"
			)
			return

		try:
			frappe.sendmail(
				recipients=[self.email],
				subject=_("Accusé de réception de votre candidature - UDSHED"),
				message=f"""
					<p>Bonjour <strong>{self.first_name} {self.last_name}</strong>,</p>

					<p>Nous avons bien reçu votre candidature sur la plateforme UDSHED.</p>

					<p><strong>Votre numéro de dossier :</strong> {self.name}</p>

					<p>Conservez ce numéro, il vous permettra de suivre l'état de votre candidature.</p>

					<p>Notre équipe examinera votre dossier dans les meilleurs délais.</p>

					<br>
					<p>Cordialement,</p>
					<p><strong>L'équipe UDSHED</strong></p>
				""",
				now=True
			)
		except Exception as e:
			frappe.log_error(message=str(e), title="Échec envoi e-mail accusé réception UDSHED")
