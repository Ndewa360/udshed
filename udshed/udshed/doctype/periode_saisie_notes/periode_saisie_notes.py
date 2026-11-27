# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime


class PeriodeSaisieNotes(Document):
	def validate(self):
		if get_datetime(self.fermeture) <= get_datetime(self.ouverture):
			frappe.throw(_("La date limite doit suivre l'ouverture de la saisie."))
		from udshed.utils import perimetre

		roles = set(frappe.get_roles())
		if frappe.session.user != "Administrator" and not roles & {"System Manager", "Directeur des Affaires Académiques"}:
			# Doyen / vice-doyen : uniquement les périodes de SA faculté.
			if not self.faculte or self.faculte not in perimetre.facultes_dirigees():
				frappe.throw(_("Vous ne pouvez fixer que les périodes de votre faculté."), frappe.PermissionError)
		doublon = frappe.db.get_value("Periode Saisie Notes", {
			"academic_year": self.academic_year, "semestre": self.semestre, "type_evaluation": self.type_evaluation,
			"faculte": self.faculte or ["is", "not set"], "name": ["!=", self.name or ""]}, "name")
		if doublon:
			frappe.throw(_("Une période existe déjà pour ces critères : {0}.").format(doublon))
