# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Demande de correction d'une note (voir udshed/utils/correction_note.py)."""

import frappe
from frappe.model.document import Document

from udshed.utils import correction_note


class CorrectionNote(Document):
	def validate(self):
		if self.statut == "En attente":
			correction_note.preparer(self)

	def on_trash(self):
		if self.statut == "Appliquée":
			frappe.throw("Une correction appliquée fait partie de l'historique : elle ne peut pas être supprimée.")

	@frappe.whitelist()
	def approuver(self):
		return correction_note.appliquer(self)

	@frappe.whitelist()
	def refuser(self, motif=None):
		return correction_note.refuser(self, motif)
