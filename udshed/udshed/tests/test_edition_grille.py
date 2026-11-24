# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests de l'édition de la grille d'enseignement.

Cas couverts :
  - modification d'un cours propre à la classe (intitulé, heures, crédits) ;
  - cours partagé : l'intitulé / les heures exigent la confirmation tronc
    commun ; les crédits restent propres à chaque classe ;
  - avertissement de cohérence crédits / heures ;
  - ajout d'un nouveau cours (avec nouvelle UE) puis rattachement d'un cours
    existant à une autre classe ;
  - retrait refusé si le cours a des données pour la classe ; retrait d'un
    cours orphelin = suppression du cours et de son UE vide ;
  - renommage d'UE (le code ne change pas).
"""

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api import teaching_grid
from udshed.udshed._fixture_factory import (
	make_academic_year,
	make_calendar_planing,
	make_faculty,
	make_field_of_study,
	make_level,
	make_teacher,
	unique_code,
)


class TestEditionGrille(IntegrationTestCase):
	def setUp(self):
		self.annee = make_academic_year("2026", "2027")
		self.calendrier = make_calendar_planing()
		self.faculte = make_faculty()
		self.filiere = make_field_of_study(self.faculte, self.calendrier, make_teacher())
		self.filiere.has_uv_in_grid = 1
		self.niveau = make_level(self.filiere)
		self.autre_filiere = make_field_of_study(self.faculte, self.calendrier, make_teacher())
		self.autre_filiere.has_uv_in_grid = 1
		self.autre_niveau = make_level(self.autre_filiere)
		self.ctx = dict(academic_year=self.annee.name, faculty=self.faculte.name, filiere=self.filiere.name,
		                niveau=self.niveau.name, semestre="Semestre 1")
		self.ctx_b = {**self.ctx, "filiere": self.autre_filiere.name, "niveau": self.autre_niveau.name}
		self.ue = unique_code("UE")
		self.code = unique_code("CRS")
		res = teaching_grid.ajouter_cours(**self.ctx, code=self.code, intitule_cours="Analyse", credits=3,
		                                  ue_code=self.ue, ue_intitule="Mathématiques",
		                                  nombre_dheure_cm=30, nombre_dheure_td=10)
		self.tu = res["teaching_unit"]

	def doc(self):
		return frappe.get_doc("Teaching Unit", self.tu)

	def test_ajout_cree_cours_et_ue(self):
		doc = self.doc()
		self.assertEqual(doc.intitule_cours, "Analyse")
		self.assertEqual(frappe.db.get_value("Teaching Unit Value", doc.unite_de_valeur, "code"), self.ue)
		self.assertEqual(doc.course_levels[0].course_poid, 3)

	def test_modification_cours_propre(self):
		res = teaching_grid.modifier_cours(self.tu, **self.ctx, valeurs={
			"intitule_cours": "Analyse I", "credits": 4, "nombre_dheure_cm": 40, "nombre_dheure_td": 15})
		doc = self.doc()
		self.assertEqual((doc.intitule_cours, doc.nombre_dheure_cm, doc.course_levels[0].course_poid, doc.credits),
		                 ("Analyse I", 40, 4, 4))
		self.assertIsNone(res["avertissement"])  # 55 h pour 4 crédits : dans la norme
		res = teaching_grid.modifier_cours(self.tu, **self.ctx, valeurs={"credits": 10})
		self.assertTrue(res["avertissement"])

	def test_cours_partage_exige_confirmation(self):
		res = teaching_grid.ajouter_cours(**self.ctx_b, code=self.code, credits=5)
		self.assertTrue(res["rattache"])
		with self.assertRaises(frappe.ValidationError):
			teaching_grid.modifier_cours(self.tu, **self.ctx, valeurs={"intitule_cours": "Renommé"})
		self.assertEqual(self.doc().intitule_cours, "Analyse")
		# Les crédits sont propres à la classe : pas de confirmation requise.
		teaching_grid.modifier_cours(self.tu, **self.ctx, valeurs={"credits": 2})
		teaching_grid.modifier_cours(self.tu, **self.ctx, valeurs={"intitule_cours": "Renommé"}, appliquer_au_tronc_commun=1)
		poids = {str(r.niveau): r.course_poid for r in self.doc().course_levels}
		self.assertEqual(poids, {str(self.niveau.name): 2, str(self.autre_niveau.name): 5})
		self.assertEqual(self.doc().intitule_cours, "Renommé")

	def test_rattachement_en_double_refuse(self):
		with self.assertRaises(frappe.ValidationError):
			teaching_grid.ajouter_cours(**self.ctx, code=self.code, credits=3)

	def test_retrait_refuse_si_donnees(self):
		periode = self.calendrier.append("heure_planification", {"libelle": "M", "heure_de_debut": "08:00:00", "heure_de_fin": "10:00:00"})
		self.calendrier.save(ignore_permissions=True)
		frappe.get_doc({"doctype": "Planning Item", "cours": self.tu, "type": "Cours Magistral (CM)", "date": "2026-11-02",
		                "period": periode.name, "academic_year": self.annee.name, "mode": "En ligne"}).insert(ignore_permissions=True)
		deps = teaching_grid.dependances_suppression(self.tu, **self.ctx)
		self.assertTrue(deps["bloque"])
		with self.assertRaises(frappe.ValidationError):
			teaching_grid.supprimer_cours(self.tu, **self.ctx)
		self.assertTrue(frappe.db.exists("Teaching Unit", self.tu))

	def test_retrait_cours_orphelin_supprime_cours_et_ue(self):
		ue = self.doc().unite_de_valeur
		res = teaching_grid.supprimer_cours(self.tu, **self.ctx)
		self.assertTrue(res["supprime"])
		self.assertFalse(frappe.db.exists("Teaching Unit", self.tu))
		self.assertFalse(frappe.db.exists("Teaching Unit Value", ue))

	def test_retrait_tronc_commun_garde_le_cours_pour_l_autre_classe(self):
		teaching_grid.ajouter_cours(**self.ctx_b, code=self.code, credits=5)
		res = teaching_grid.supprimer_cours(self.tu, **self.ctx)
		self.assertFalse(res["supprime"])
		self.assertEqual([str(r.niveau) for r in self.doc().course_levels], [str(self.autre_niveau.name)])

	def test_renommage_ue(self):
		teaching_grid.modifier_ue(self.ue, "Maths appliquées", **self.ctx)
		nom = self.doc().unite_de_valeur
		self.assertEqual(frappe.db.get_value("Teaching Unit Value", nom, ["code", "intitule"]), (self.ue, "Maths appliquées"))
