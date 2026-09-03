# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SessionExamen(Document):
	def validate(self):
		self._valider_dates()

	def _valider_dates(self):
		"""Règle métier : la date initiale doit être ≤ à la date finale.

		La date initiale peut être égale à la date finale (session sur une
		seule journée), mais jamais postérieure à celle-ci.
		"""
		if not self.date_debut or not self.date_de_fin:
			return

		if self.date_debut > self.date_de_fin:
			frappe.throw(
				frappe._(
					"La date initiale de la session doit être antérieure ou égale à la date finale."
				)
			)
