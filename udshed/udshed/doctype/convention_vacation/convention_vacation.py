# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class ConventionVacation(Document):
	def validate(self):
		autre = frappe.db.get_value("Convention Vacation", {
			"teacher": self.teacher, "academic_year": self.academic_year, "statut": ["!=", "Résiliée"],
			"name": ["!=", self.name or ""]}, "name")
		if autre and self.statut != "Résiliée":
			frappe.throw(_("Une convention existe déjà pour cet enseignant et cette année : {0}.").format(autre))
		if not self.volume_horaire or not self.taux_horaire:
			from udshed.utils import vacations

			f = vacations.fiche(self.teacher, self.academic_year)
			self.volume_horaire = self.volume_horaire or f.heures_prevues
			self.taux_horaire = self.taux_horaire or f.taux
		self.montant_previsionnel = flt(self.volume_horaire) * flt(self.taux_horaire)
		self.devise = frappe.db.get_single_value("Udshed Setting", "devise") or frappe.db.get_default("currency") or "XAF"
		if self.statut == "Signée":
			if not self.convention_signee:
				frappe.throw(_("Joignez la convention signée (scan) avant de la marquer « Signée »."))
			self.date_signature = self.date_signature or today()
