# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from udshed.utils.niveaux import cycle_niveau


class Fieldofstudy(Document):

	def before_save(self):
		self.normaliser_ordres_niveaux()
		self.normaliser_cycles()
		self.gerer_coordonateurs()

	def normaliser_ordres_niveaux(self):
		"""L'ordre de chaque niveau = sa position dans le tableau.

		La table de niveaux est reordonnable par drag & drop ; cette methode
		garantit que le champ `order` refleche toujours la position des lignes
		(1, 2, 3, ...), source du calcul du niveau precedent/suivant.
		"""
		for i, row in enumerate(self.get("field_of_study_level") or []):
			row.order = i + 1

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
		new_rows = {row.name: row for row in self.field_of_study_level}
		teacher_to_cordo_list = []

		if old_doc:
			old_rows = {row.name: row for row in old_doc.field_of_study_level}
			for row_name in new_rows:
				if row_name not in old_rows:
					if new_rows[row_name].get("coordonateur") not in teacher_to_cordo_list:
						teacher_to_cordo_list.append(new_rows[row_name].get("coordonateur"))
			for row_name in new_rows:
				if row_name in old_rows:
					if old_rows[row_name].get("coordonateur") != new_rows[row_name].get("coordonateur") and new_rows[row_name].get("coordonateur") not in teacher_to_cordo_list:
						teacher_to_cordo_list.append(new_rows[row_name].get("coordonateur"))
		else:
			for row in self.field_of_study_level:
				if row.get("coordonateur") and row.get("coordonateur") not in teacher_to_cordo_list:
					teacher_to_cordo_list.append(row.get("coordonateur"))

		for teacher in teacher_to_cordo_list:
			t = frappe.get_doc("Teacher", teacher)
			t_user = frappe.get_doc("User", t.user)
			if not frappe.db.exists("Has Role", { "parent": t_user.email, "role": "Coordonateur" }):
				t_user.append("roles", {"role": "Coordonateur"})
				t_user.save()

		