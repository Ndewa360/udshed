# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from udshed.utils.niveaux import cycle_niveau


class Fieldofstudy(Document):

	def before_save(self):
		self.normaliser_cycles()
		self.gerer_coordonateurs()

	def normaliser_cycles(self):
		"""Le cycle est TOUJOURS déduit du libellé du niveau.

		Frappe applique la première option d'un champ Select comme défaut à
		l'insertion d'une ligne (cycle='Licence'), avant before_save. On force
		donc le calcul pour éviter qu'un niveau BTS/Master reçoive 'Licence'.
		"""
		for row in self.get("field_of_study_level") or []:
			row.cycle = cycle_niveau(row.get("level")) or row.cycle or "Autre"

	def gerer_coordonateurs(self):
		old_doc = self.get_doc_before_save()
		new_rows = {}
		for row in self.field_of_study_level:
			key = row.get("name") or row.get("level") or id(row)
			new_rows[key] = row
		teacher_to_cordo_list = []

		if old_doc:
			old_rows = {}
			for row in old_doc.field_of_study_level:
				key = row.get("name") or row.get("level") or id(row)
				old_rows[key] = row
			for row_key in new_rows:
				if row_key not in old_rows:
					cordo = new_rows[row_key].get("coordonateur")
					if cordo and cordo not in teacher_to_cordo_list:
						teacher_to_cordo_list.append(cordo)
			for row_key in new_rows:
				if row_key in old_rows:
					if old_rows[row_key].get("coordonateur") != new_rows[row_key].get("coordonateur") and new_rows[row_key].get("coordonateur") not in teacher_to_cordo_list:
						teacher_to_cordo_list.append(new_rows[row_key].get("coordonateur"))
		else:
			for row in self.field_of_study_level:
				cordo = row.get("coordonateur")
				if cordo and cordo not in teacher_to_cordo_list:
					teacher_to_cordo_list.append(cordo)

		for teacher in teacher_to_cordo_list:
			t = frappe.get_doc("Teacher", teacher)
			t_user = frappe.get_doc("User", t.user)
			if not frappe.db.exists("Has Role", { "parent": t_user.email, "role": "Coordonateur" }):
				t_user.append("roles", {"role": "Coordonateur"})
				t_user.save()
