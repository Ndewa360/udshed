# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EcheanceEtudiant(Document):
	def validate(self):
		from udshed.utils import frais

		frais.calculer_echeance(self)
