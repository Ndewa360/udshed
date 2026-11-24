# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests de la liaison manuelle de cours (même cours, intitulés différents).

Cas couverts :
  - lier deux cours de grilles différentes crée un groupe commun ;
  - planifié une fois, le groupe occupe toutes ses classes : impossible de
    programmer un autre cours de l'autre classe sur ce créneau, ni le cours lié ;
  - la séance apparaît dans le planning de chaque classe du groupe ;
  - délier supprime la contrainte ;
  - un coordinateur ne peut pas lier un cours hors de son périmètre ;
  - cours d'années différentes : liaison refusée ;
  - suggestions : intitulés identiques après normalisation.
"""

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api import cours_commun, planning_calendar
from udshed.udshed._fixture_factory import (
	make_academic_year,
	make_calendar_planing,
	make_course,
	make_faculty,
	make_field_of_study,
	make_level,
	make_teacher,
	make_teaching_unit,
	make_user_with_role,
)
from udshed.utils.planning_conflits import conflits


class TestCoursCommun(IntegrationTestCase):
	def setUp(self):
		self.annee = make_academic_year("2026", "2027")
		self.calendrier = make_calendar_planing()
		p = self.calendrier.append("heure_planification", {"libelle": "Matin", "heure_de_debut": "08:00:00", "heure_de_fin": "12:00:00"})
		self.calendrier.save(ignore_permissions=True)
		self.matin = p.name
		faculte = make_faculty()
		self.coord_a = make_teacher()
		self.fil_a = make_field_of_study(faculte, self.calendrier, self.coord_a)
		self.niv_a = make_level(self.fil_a)
		self.fil_b = make_field_of_study(faculte, self.calendrier, make_teacher())
		self.niv_b = make_level(self.fil_b)
		self.algebre_a = make_teaching_unit(make_course(intitule="Algèbre"), self.annee, self.fil_a, self.niv_a)
		self.maths_b = make_teaching_unit(make_course(intitule="Mathématiques I"), self.annee, self.fil_b, self.niv_b)
		self.autre_b = make_teaching_unit(make_course(), self.annee, self.fil_b, self.niv_b)

	def tearDown(self):
		frappe.set_user("Administrator")

	def planifier(self, cours, jour="2026-11-02"):
		return frappe.get_doc({
			"doctype": "Planning Item", "cours": cours.name, "type": "Cours Magistral (CM)", "date": jour,
			"period": self.matin, "academic_year": self.annee.name, "mode": "En ligne",
		}).insert(ignore_permissions=True)

	def test_liaison_occupe_toutes_les_classes(self):
		res = cours_commun.lier_cours([self.algebre_a.name, self.maths_b.name])
		self.assertTrue(res["groupe"])
		self.assertEqual(len(res["cours"]), 2)

		self.planifier(self.algebre_a)
		# La classe B est occupée par le cours commun : autre cours de B refusé.
		with self.assertRaises(frappe.ValidationError):
			self.planifier(self.autre_b)
		# Le cours lié lui-même ne peut pas être programmé une 2e fois sur le créneau.
		self.assertTrue(conflits(self.maths_b.name, "2026-11-02", self.matin))

	def test_seance_visible_dans_le_planning_de_l_autre_classe(self):
		cours_commun.lier_cours([self.algebre_a.name, self.maths_b.name])
		item = self.planifier(self.algebre_a)
		lignes = planning_calendar.get_week_planning(
			self.annee.name, "2026-11-02", filiere=self.fil_b.name, niveau=self.niv_b.name
		)
		self.assertIn(item.name, [r["name"] for r in lignes])

	def test_delier_supprime_la_contrainte(self):
		cours_commun.lier_cours([self.algebre_a.name, self.maths_b.name])
		cours_commun.delier_cours(self.maths_b.name)
		self.assertFalse(frappe.db.get_value("Teaching Unit", self.algebre_a.name, "groupe_cours_commun"))
		self.planifier(self.algebre_a)
		self.planifier(self.autre_b)  # B est libre : plus de lien

	def test_coordinateur_ne_peut_pas_lier_hors_perimetre(self):
		user = make_user_with_role("Coordonateur")
		frappe.db.set_value("Teacher", self.coord_a.name, "email", user.name)
		frappe.set_user(user.name)
		with self.assertRaises(frappe.PermissionError):
			cours_commun.lier_cours([self.algebre_a.name, self.maths_b.name])

	def test_annees_differentes_refusees(self):
		autre_annee = make_academic_year("2027", "2028")
		autre = make_teaching_unit(make_course(), autre_annee, self.fil_b, self.niv_b)
		with self.assertRaises(frappe.ValidationError):
			cours_commun.lier_cours([self.algebre_a.name, autre.name])

	def test_suggestions_intitules_normalises(self):
		frappe.db.set_value("Teaching Unit", self.maths_b.name, "intitule_cours", "ALGEBRE")
		frappe.db.set_value("Teaching Unit", self.algebre_a.name, "intitule_cours", "Algèbre")
		noms = [{c["teaching_unit"] for c in s["cours"]} for s in cours_commun.suggestions(self.annee.name, "Semestre 1")]
		self.assertIn({self.algebre_a.name, self.maths_b.name}, noms)
