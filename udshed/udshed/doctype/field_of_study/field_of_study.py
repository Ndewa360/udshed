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

		La table de niveaux est reordonnable (drag & drop, y compris la page de
		gestion des niveaux). Cette methode garantit que le champ `order` refleche
		la position effective des lignes (1, 2, 3, ...) a chaque sauvegarde, source
		du calcul du niveau precedent/suivant. On renumérote des qu'un ordre ne
		correspond pas deja a sa position (doublon, zero ou apres une permutation).
		"""
		rows = self.get("field_of_study_level")
		if not rows:
			return

		need_renumber = any((row.get("order") or 0) != i + 1 for i, row in enumerate(rows))
		if need_renumber:
			for i, row in enumerate(rows):
				row.order = i + 1

	def normaliser_cycles(self):
		"""Le cycle d'un niveau doit rester cohérent avec son libellé.

		Frappe applique la première option d'un champ Select comme défaut à
		l'insertion d'une ligne (cycle='Licence'), avant before_save. On corrige
		donc le cycle quand il est vide ou incohérent avec le libellé (ex: un
		'BTS 1' avec le défaut 'Licence'), tout en laissant un cycle choisi
		manuellement et cohérent être conservé (édition dans la page de gestion
		des niveaux).
		"""
		for row in self.get("field_of_study_level") or []:
			deduced = cycle_niveau(row.get("level"))
			current = row.get("cycle")
			if not current or (deduced and deduced != "Autre" and current != deduced):
				row.cycle = deduced or current or "Autre"

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
