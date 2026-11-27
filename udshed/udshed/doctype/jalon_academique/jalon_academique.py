# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Jalon du calendrier académique.

Les campagnes, réinscriptions, sessions d'examen, périodes de saisie et
délibérations alimentent automatiquement le calendrier (jalon « Préparé »).
Le DAA (ou le doyen pour sa faculté) peut aussi poser un jalon « À préparer » :
s'il approche sans objet rattaché, il est signalé à J-7 puis à J-2.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from udshed.utils import perimetre

ROLES_ETABLISSEMENT = {"System Manager", "Directeur des Affaires Académiques"}


class JalonAcademique(Document):
	def validate(self):
		if self.date_fin and self.date_debut and str(self.date_fin) < str(self.date_debut):
			frappe.throw(_("La date de fin précède la date de début."))
		if frappe.flags.in_test or frappe.session.user == "Administrator" or self.flags.ignore_permissions:
			return
		if set(frappe.get_roles()) & ROLES_ETABLISSEMENT:
			return
		if not self.faculte or not perimetre.est_doyen_de(self.faculte):
			frappe.throw(_("Un doyen ou vice-doyen ne pose des jalons que pour sa propre faculté."),
						 frappe.PermissionError)
