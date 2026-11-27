# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class PaiementEtudiant(Document):
	def validate(self):
		from udshed.utils import frais

		frais.valider_paiement(self)

	def after_insert(self):
		from udshed.utils import frais

		frais.apres_paiement(self)

	def on_trash(self):
		from udshed.utils import frais

		frais.recalculer(self.echeance, sauf=self.name)
