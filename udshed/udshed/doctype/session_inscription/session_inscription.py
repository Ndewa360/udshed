# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _


class SessionInscription(Document):

	def validate(self):
		self.validate_dates()
		self.validate_unique_open_session()

	def before_save(self):
		old_doc = self.get_doc_before_save()
		if old_doc and old_doc.status == "Open" and self.status == "Open":
			frappe.throw(_("Cannot modify a session that is already Open."))

	def before_delete(self):
		if self.status == "Open":
			frappe.throw(_("Cannot delete a session that is Open. Close it first."))

	def validate_dates(self):
		if self.closing_date <= self.opening_date:
			frappe.throw(_("Closing Date must be after Opening Date."))

	def validate_unique_open_session(self):
		if self.status == "Open":
			existing = frappe.db.exists("Session Inscription", {
				"academic_year": self.academic_year,
				"status": "Open",
				"name": ("!=", self.name)
			})
			if existing:
				frappe.throw(_(
					"An open registration session already exists for Academic Year {0}."
				).format(self.academic_year))

	@frappe.whitelist()
	def open_session(self):
		self.validate_unique_open_session()
		self.status = "Open"
		self.save()

	@frappe.whitelist()
	def close_session(self):
		self.status = "Closed"
		self.save()
