# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TeachingUnitValue(Document):
	def validate(self):
		self._valider_code_par_annee()

	def _valider_code_par_annee(self):
		"""Un code d'UE est unique au sein d'une année académique.

		Le code peut être réutilisé d'une année sur l'autre (import de la grille
		de l'année suivante avec les mêmes codes), mais pas dupliqué la même
		année.
		"""
		if not (self.code and self.academic_year):
			return

		filters = {"code": self.code, "academic_year": self.academic_year}
		if self.name:
			filters["name"] = ["!=", self.name]

		if frappe.db.exists("Teaching Unit Value", filters):
			frappe.throw(
				_("Le code d'UE {0} existe déjà pour l'année académique {1}.").format(
					frappe.bold(self.code), frappe.bold(self.academic_year)
				)
			)
