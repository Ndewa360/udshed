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

	# ------------------------------------------------------------------ #
	#  Vue « deux grilles »
	# ------------------------------------------------------------------ #
	def comparer(self):
		return cours_commun.comparer_grilles(
			self.annee.name, self.fil_a.name, self.niv_a.name, self.fil_b.name, self.niv_b.name, "Semestre 1"
		)

	def test_comparer_grilles_liens_et_suggestions(self):
		tronc = make_teaching_unit(make_course(), self.annee, self.fil_a, self.niv_a)
		tronc.append("course_levels", {"filiere": self.fil_b.name, "niveau": self.niv_b.name, "course_poid": 3})
		tronc.save(ignore_permissions=True)
		frappe.db.set_value("Teaching Unit", self.autre_b.name, "intitule_cours", "Algebre")
		frappe.db.set_value("Teaching Unit", self.algebre_a.name, "intitule_cours", "ALGÈBRE")
		cours_commun.lier_cours([self.algebre_a.name, self.maths_b.name])

		data = self.comparer()
		liens = {(l["gauche"], l["droite"], l["type"]) for l in data["liens"]}
		self.assertIn((tronc.name, tronc.name, "tronc_commun"), liens)
		self.assertIn((self.algebre_a.name, self.maths_b.name, "lie"), liens)
		# Le tronc commun apparaît dans les deux grilles.
		for cote in ("gauche", "droite"):
			self.assertIn(tronc.name, [c["teaching_unit"] for ue in data[cote]["ues"] for c in ue["cours"]])
		# Algèbre est déjà lié : pas de suggestion le concernant.
		self.assertEqual(data["suggestions"], [])
		self.assertTrue(data["peut_lier"])

	def test_grille_detaille_les_cours_lies_et_leurs_classes(self):
		"""Info-bulle « Lié » de la colonne Remarques : cours liés ET classes qui les suivent."""
		from udshed.api import teaching_grid

		cours_commun.lier_cours([self.algebre_a.name, self.maths_b.name])
		grille = teaching_grid.get_academic_teaching_unit(
			self.annee.name, self.fil_a.faculte, self.fil_a.name, self.niv_a.name, "Semestre 1"
		)
		cours = next(c for ue in grille["grid"] for c in ue["courses"] if c["teaching_unit"] == self.algebre_a.name)
		self.assertEqual(cours["cours_lies"], 1)
		detail = cours["cours_lies_details"][0]
		self.assertEqual(detail["code"], frappe.db.get_value("Teaching Unit", self.maths_b.name, "course"))
		nom_b = frappe.db.get_value("Field of study", self.fil_b.name, "name_of_field")
		self.assertEqual(detail["classes"], [f"{nom_b} — {self.niv_b.level}"])
		self.assertEqual(cours["classes_partagees_libelles"], [])

	def test_comparer_meme_classe_refuse(self):
		with self.assertRaises(frappe.ValidationError):
			cours_commun.comparer_grilles(self.annee.name, self.fil_a.name, self.niv_a.name, self.fil_a.name, self.niv_a.name)

	def test_une_classe_ne_suit_pas_deux_cours_d_un_meme_groupe(self):
		autre_a = make_teaching_unit(make_course(), self.annee, self.fil_a, self.niv_a)
		cours_commun.lier_cours([self.algebre_a.name, self.maths_b.name])
		with self.assertRaises(frappe.ValidationError):
			cours_commun.lier_cours([autre_a.name, self.maths_b.name])

	def test_liaison_n_ajoute_aucune_classe(self):
		cours_commun.lier_cours([self.algebre_a.name, self.maths_b.name])
		niveaux = lambda tu: [str(r.niveau) for r in frappe.get_doc("Teaching Unit", tu.name).course_levels]  # noqa: E731
		self.assertEqual(niveaux(self.algebre_a), [str(self.niv_a.name)])
		self.assertEqual(niveaux(self.maths_b), [str(self.niv_b.name)])

	# ------------------------------------------------------------------ #
	#  Planning : chaque classe voit le cours de SA grille
	# ------------------------------------------------------------------ #
	def test_planning_affiche_le_cours_de_la_grille(self):
		frappe.db.set_value("Teaching Unit", self.algebre_a.name, {"intitule_cours": "Algèbre", "nombre_dheure_cm": 8})
		frappe.db.set_value("Teaching Unit", self.maths_b.name, {"intitule_cours": "Mathématiques I", "nombre_dheure_cm": 12})
		cours_commun.lier_cours([self.algebre_a.name, self.maths_b.name])
		item = self.planifier(self.algebre_a)
		self.planifier(self.maths_b, jour="2026-11-03")

		vue_b = {r["name"]: r for r in planning_calendar.get_week_planning(
			self.annee.name, "2026-11-02", filiere=self.fil_b.name, niveau=self.niv_b.name)}
		seance = vue_b[item.name]
		self.assertEqual(seance["cours"], self.algebre_a.name)           # cours réellement planifié
		self.assertEqual(seance["cours_affiche"], self.maths_b.name)     # cours de la grille de B
		self.assertEqual(seance["intitule_label"], "Mathématiques I")
		self.assertTrue(seance["cours_lie"])
		# Heures cumulées sur le groupe (4 h + 4 h), rapportées au volume du cours affiché (12 h).
		derniere = max(vue_b.values(), key=lambda r: str(r["date"]))
		self.assertEqual(derniere["progress_label"], "8/12 h")

		vue_a = {r["name"]: r for r in planning_calendar.get_week_planning(
			self.annee.name, "2026-11-02", filiere=self.fil_a.name, niveau=self.niv_a.name)}
		self.assertEqual(vue_a[item.name]["intitule_label"], "Algèbre")
		self.assertFalse(vue_a[item.name].get("cours_lie"))

	# ------------------------------------------------------------------ #
	#  Saisie des notes
	# ------------------------------------------------------------------ #
	def test_notes_prennent_en_compte_la_liaison(self):
		from udshed.api import saisie_notes

		prof = make_teacher()
		self.algebre_a.append("table_enseignant", {"enseignant": prof.name, "type_de_cours": "Cours Magistral (CM)"})
		self.algebre_a.save(ignore_permissions=True)
		cours_commun.lier_cours([self.algebre_a.name, self.maths_b.name])

		# Examen commun programmé via le cours de A : B peut saisir ses notes.
		frappe.get_doc({
			"doctype": "Planning Item", "cours": self.algebre_a.name, "type": saisie_notes.TYPE_NORMALE,
			"date": "2026-11-06", "period": self.matin, "academic_year": self.annee.name, "mode": "En ligne",
		}).insert(ignore_permissions=True)
		self.assertTrue(saisie_notes._verifier_programmation(self.annee.name, self.maths_b.name, saisie_notes.TYPE_NORMALE))

		# L'enseignant du cours de A voit et gère le cours lié de B.
		ues_b = saisie_notes.get_ues(self.annee.name, self.fil_b.name, self.niv_b.level, teacher=prof.name)
		self.assertEqual([u["name"] for u in ues_b], [self.maths_b.name])
		user = make_user_with_role("Teacher")
		frappe.db.set_value("Teacher", prof.name, "email", user.name)
		frappe.set_user(user.name)
		saisie_notes._verifier_acces_enseignant(self.maths_b.name)
		with self.assertRaises(frappe.PermissionError):
			saisie_notes._verifier_acces_enseignant(self.autre_b.name)

	def test_suggestions_intitules_normalises(self):
		frappe.db.set_value("Teaching Unit", self.maths_b.name, "intitule_cours", "ALGEBRE")
		frappe.db.set_value("Teaching Unit", self.algebre_a.name, "intitule_cours", "Algèbre")
		noms = [{c["teaching_unit"] for c in s["cours"]} for s in cours_commun.suggestions(self.annee.name, "Semestre 1")]
		# Inclusion : d'autres « Algèbre » créés par les tests précédents de la classe
		# (annulés seulement en fin de classe) peuvent figurer dans le même groupe.
		self.assertTrue(any({self.algebre_a.name, self.maths_b.name} <= groupe for groupe in noms))
