# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CandidatConcours(Document):
	"""Participation d'une candidature à un concours. Les fiches sont créées
	automatiquement quand le dossier est autorisé à concourir (phase 2)."""

	def validate(self):
		doublon = frappe.db.exists(
			"Candidat Concours",
			{"concours": self.concours, "candidature": self.candidature, "name": ["!=", self.name]},
		)
		if doublon:
			frappe.throw(
				_("La candidature {0} est déjà inscrite à ce concours ({1}).").format(self.candidature, doublon)
			)
