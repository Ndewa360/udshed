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

		if self.statut == "Ouverte":
			self.verifier_session_unique_ouverte()

	def verifier_session_unique_ouverte(self):
		"""Une seule session de réinscription peut être ouverte à la fois"""
		autre_ouverte = frappe.db.exists("Session Reinscription", {
			"statut": "Ouverte",
			"name": ["!=", self.name]
		})
		if autre_ouverte:
			frappe.throw("Une autre session de réinscription est déjà ouverte. Fermez-la avant d'en ouvrir une nouvelle.")
