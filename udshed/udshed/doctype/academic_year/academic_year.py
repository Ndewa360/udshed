# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AcademicYear(Document):
	def validate(self):
		if self.start_year and self.end_year and int(self.end_year) < int(self.start_year):
			frappe.throw(_("L'année de fin ne peut pas précéder l'année de début."))

	def on_update(self):
		# Une seule année « en cours » ; Udshed Setting.current_year (lu par
		# toute l'application) suit ce choix.
		if not self.is_current_year:
			return
		for autre in frappe.get_all(
			"Academic Year", filters={"is_current_year": 1, "name": ["!=", self.name]}, pluck="name"
		):
			frappe.db.set_value("Academic Year", autre, "is_current_year", 0)
		if frappe.db.get_single_value("Udshed Setting", "current_year") != self.name:
			frappe.db.set_single_value("Udshed Setting", "current_year", self.name)
