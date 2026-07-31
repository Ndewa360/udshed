# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


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
            frappe.logger().warning(f"Impossible d'envoyer l'accusé de réception : aucun e-mail renseigné pour le candidat {self.name}")
            return

        try:
            frappe.send_mail(
                recipients=[self.email],
                template="Accuse Réception Udshed",
                doc=self
            )
        except Exception as e:
            frappe.log_error(message=str(e), title="Échec envoi e-mail accusé réception Udshed")
