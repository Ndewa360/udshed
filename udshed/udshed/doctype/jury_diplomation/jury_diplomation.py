# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Jury de diplomation de fin de cycle (voir udshed/utils/diplomation.py)."""

import frappe
from frappe import _
from frappe.model.document import Document

from udshed.utils import diplomation

ROLES = {"System Manager", "Responsable Diplomation", "Registration Manager"}


def _exiger():
	if not (set(frappe.get_roles()) & ROLES):
		frappe.throw(_("Action réservée au responsable de la diplomation."), frappe.PermissionError)


class JuryDiplomation(Document):
	def validate(self):
		if self.statut == "Proclamé" and self.get_doc_before_save() and self.has_value_changed("candidats"):
			frappe.throw(_("Jury proclamé : annulez la proclamation avant de modifier les décisions."))

	@frappe.whitelist()
	def rechercher_candidats(self):
		_exiger()
		if self.statut == "Proclamé":
			frappe.throw(_("Jury déjà proclamé."))
		n = diplomation.rechercher_candidats(self)
		self.save()
		return n

	@frappe.whitelist()
	def proclamer(self):
		_exiger()
		self.save()
		return diplomation.proclamer(self)

	@frappe.whitelist()
	def annuler_proclamation(self):
		_exiger()
		return diplomation.annuler(self)
