# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ModeleActe(Document):
	def validate(self):
		from udshed.utils.actes import SUJET_ENSEIGNANT, SUJET_ETUDIANT, TYPES_ENSEIGNANT

		if self.type_acte in TYPES_ENSEIGNANT:
			self.sujet = SUJET_ENSEIGNANT
		elif self.type_acte != "Autre":
			self.sujet = SUJET_ETUDIANT
		if self.modele_word and not self.modele_word.lower().endswith(".docx"):
			frappe.throw(_("Le modèle Word doit être un fichier .docx."))

	def on_update(self):
		# Un seul modèle par défaut par type de document.
		if self.par_defaut:
			for autre in frappe.get_all("Modele Acte", filters={"type_acte": self.type_acte, "par_defaut": 1,
														  "name": ["!=", self.name]}, pluck="name"):
				frappe.db.set_value("Modele Acte", autre, "par_defaut", 0)
