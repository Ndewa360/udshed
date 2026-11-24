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
		self._controler_decisions_jury()

	def _controler_decisions_jury(self):
		"""Décisions du jury (tableau des résultats) : modifiables seulement pendant
		la délibération, et cohérentes avec le classement."""
		avant = self.get_doc_before_save()
		if not avant:
			return
		anciennes = {r.name: r.decision or "" for r in avant.resultats}
		modifiees = [r for r in self.resultats if (r.decision or "") != anciennes.get(r.name, "")]
		if not modifiees:
			return
		statut = frappe.db.get_value("Concours", self.concours, "statut")
		if statut != "Délibération":
			frappe.throw(
				_("Les décisions du jury se modifient au statut « Délibération » (statut actuel : {0}). "
				  "Après publication, utilisez « Enregistrer un désistement ».").format(statut)
			)
		for r in modifiees:
			if r.decision == "Désisté":
				frappe.throw(_("Ligne {0} : « Désisté » s'enregistre après la publication des résultats.").format(r.idx))
			if r.decision == "Admis" and r.elimine:
				frappe.throw(_("Ligne {0} : un candidat éliminé ({1}) ne peut pas être admis.").format(r.idx, r.motif))
		if sum(1 for r in self.resultats if r.decision == "Admis") > 1:
			frappe.throw(_("Un candidat ne peut être admis que dans une seule formation."))
