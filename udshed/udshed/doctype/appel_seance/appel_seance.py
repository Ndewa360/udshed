# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AppelSeance(Document):
	def validate(self):
		from udshed.utils import assiduite

		assiduite.valider_appel(self)

	def on_update(self):
		from udshed.utils import assiduite

		assiduite.controler_seuils(self)
