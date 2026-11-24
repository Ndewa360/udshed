# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from udshed.utils.planning_conflits import verifier_conflits


class PlanningItem(Document):
	def validate(self):
		# Garde-fou central : quel que soit le chemin d'écriture (page planning,
		# formulaire Desk, duplication de semaine…), une classe, un enseignant
		# ou une salle ne peut pas être sur deux séances au même créneau.
		if self.cours and self.date and self.period:
			verifier_conflits(
				self.cours,
				self.date,
				self.period,
				salle=self.salle if self.mode != "En ligne" else None,
				exclure=None if self.is_new() else self.name,
			)
