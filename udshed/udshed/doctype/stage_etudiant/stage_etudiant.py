# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class StageEtudiant(Document):
	def validate(self):
		from udshed.utils import stages

		stages.valider_stage(self)

	def on_update(self):
		from udshed.utils import stages

		stages.apres_stage(self)
