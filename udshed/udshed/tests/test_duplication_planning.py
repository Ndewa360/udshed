# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests de la duplication du planning d'une semaine à une autre.

Scénario (classe A) — semaine source du lundi 2 novembre 2026 :
  lundi matin  : a1             | mardi matin : a2
  mercredi     : tronc (A + B)  | jeudi       : examen sur a1 (évaluation)
Semaine cible (9 novembre) déjà partiellement remplie depuis la classe B :
  lundi matin  : tc2 (tronc commun A + B)  -> a1 ne peut pas y aller
  mercredi     : tronc déjà programmé       -> rien à faire

Cas couverts : prévisualisation sans écriture, classement de chaque séance,
récapitulatif des créneaux (libres / tronc commun / à créer), application,
évaluations ignorées par défaut, semaines identiques refusées, droits.
"""

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api import planning_duplication
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

SOURCE, CIBLE = "2026-11-02", "2026-11-09"


class TestDuplicationPlanning(IntegrationTestCase):
	def setUp(self):
		self.annee = make_academic_year("2026", "2027")
		self.calendrier = make_calendar_planing()
		p = self.calendrier.append("heure_planification", {"libelle": "Matin", "heure_de_debut": "08:00:00", "heure_de_fin": "12:00:00"})
		self.calendrier.save(ignore_permissions=True)
		self.matin = p.name
		faculte = make_faculty()
		self.fil_a = make_field_of_study(faculte, self.calendrier, make_teacher())
		self.niv_a = make_level(self.fil_a)
		self.coord_b = make_teacher()
		self.fil_b = make_field_of_study(faculte, self.calendrier, self.coord_b)
		self.niv_b = make_level(self.fil_b)

		def cours(*classes):
			tu = make_teaching_unit(make_course(), self.annee, classes[0][0], classes[0][1])
			for fil, niv in classes[1:]:
				tu.append("course_levels", {"filiere": fil.name, "niveau": niv.name, "course_poid": 3})
			tu.append("table_enseignant", {"enseignant": make_teacher().name, "type_de_cours": "Cours Magistral (CM)"})
			tu.save(ignore_permissions=True)
			return tu

		a, b = (self.fil_a, self.niv_a), (self.fil_b, self.niv_b)
		self.a1, self.a2 = cours(a), cours(a)
		self.tronc, self.tc2 = cours(a, b), cours(a, b)

		self.seance(self.a1, "2026-11-02")
		self.seance(self.a2, "2026-11-03")
		self.seance(self.tronc, "2026-11-04")
		self.seance(self.a1, "2026-11-05", type_="Examen de session normal")
		self.seance(self.tc2, "2026-11-09")
		self.seance(self.tronc, "2026-11-11")

	def tearDown(self):
		frappe.set_user("Administrator")

	def seance(self, cours, jour, type_="Cours Magistral (CM)"):
		return frappe.get_doc({
			"doctype": "Planning Item", "cours": cours.name, "type": type_, "date": jour,
			"period": self.matin, "academic_year": self.annee.name, "mode": "En ligne",
		}).insert(ignore_permissions=True)

	def args(self, **extra):
		return dict(academic_year=self.annee.name, filiere=self.fil_a.name, niveau=self.niv_a.name,
		            semaine_source=SOURCE, semaine_cible=CIBLE, **extra)

	def test_previsualisation_classe_chaque_seance(self):
		avant = frappe.db.count("Planning Item")
		data = planning_duplication.previsualiser_duplication(**self.args())
		self.assertEqual(frappe.db.count("Planning Item"), avant)
		actions = {(e["cours"], e["type"]): e["action"] for e in data["seances"]}
		self.assertEqual(actions[(self.a1.name, "Cours Magistral (CM)")], "conflit")
		self.assertEqual(actions[(self.a2.name, "Cours Magistral (CM)")], "a_creer")
		self.assertEqual(actions[(self.tronc.name, "Cours Magistral (CM)")], "deja_planifiee")
		self.assertEqual(actions[(self.a1.name, "Examen de session normal")], "ignoree")

		matin = data["recapitulatif"][0]["jours"]
		self.assertEqual([c["etat"] for c in matin[:4]], ["occupe_commun", "a_creer", "occupe_commun", "libre"])
		self.assertEqual(data["stats"]["creneaux_tronc_commun"], 2)

	def test_duplication_cree_uniquement_les_creneaux_libres(self):
		resultat = planning_duplication.dupliquer_semaine(**self.args())
		self.assertEqual((resultat["creees"], resultat["echecs"]), (1, []))
		self.assertTrue(frappe.db.exists("Planning Item", {"cours": self.a2.name, "date": ["between", ["2026-11-10", "2026-11-10 23:59:59"]]}))
		self.assertFalse(frappe.db.exists("Planning Item", {"cours": self.a1.name, "date": ["between", ["2026-11-09", "2026-11-14 23:59:59"]]}))
		# Relancer ne duplique rien de plus.
		self.assertEqual(planning_duplication.dupliquer_semaine(**self.args())["creees"], 0)

	def test_evaluations_incluses_sur_demande(self):
		data = planning_duplication.previsualiser_duplication(**self.args(inclure_evaluations=1))
		examen = next(e for e in data["seances"] if e["type"] == "Examen de session normal")
		self.assertEqual(examen["action"], "a_creer")

	def test_meme_semaine_refusee(self):
		with self.assertRaises(frappe.ValidationError):
			planning_duplication.previsualiser_duplication(**{**self.args(), "semaine_cible": "2026-11-04"})

	def test_droits_classe_hors_perimetre(self):
		user = make_user_with_role("Coordonateur")
		frappe.db.set_value("Teacher", self.coord_b.name, "email", user.name)
		frappe.set_user(user.name)
		with self.assertRaises(frappe.PermissionError):
			planning_duplication.previsualiser_duplication(**self.args())
