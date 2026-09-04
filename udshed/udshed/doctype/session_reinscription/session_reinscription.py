# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SessionReinscription(Document):
	_DOCTYPE_NAME = "SessionReinscription"

	def validate(self):
		if self.date_ouverture and self.date_cloture:
			if self.date_ouverture >= self.date_cloture:
				frappe.throw("La date d'ouverture doit être antérieure à la date de clôture")
