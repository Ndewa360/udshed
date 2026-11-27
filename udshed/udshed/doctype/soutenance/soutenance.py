# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class Soutenance(Document):
	def validate(self):
		from udshed.utils import stages

		stages.valider_soutenance(self)

	def on_update(self):
		from udshed.utils import stages

		stages.apres_soutenance(self)
