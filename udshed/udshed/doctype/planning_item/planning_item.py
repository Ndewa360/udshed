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

		# Pointage : un statut changé à la main (Desk ou page planning) est
		# « fixé manuellement » ; le pointage automatique du dimanche ne le
		# modifiera plus. Le pointage automatique lui-même passe ce drapeau.
		if self.is_new():
			if not self.status:
				self.status = "Non fait"
			return
		if self.has_value_changed("status") and not self.flags.pointage_automatique:
			self.pointage_manuel = 1
		elif (
			self.has_value_changed("date") and not self.pointage_manuel
			and self.status != "Annulée" and self.date
		):
			# Séance déplacée sans statut fixé à la main : son statut suit sa
			# nouvelle date (une séance repoussée à plus tard redevient « Non fait »).
			from udshed.utils.pointage import statut_automatique

			self.status = statut_automatique(self.date)
