# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests de la création d'année académique et de la reprise des grilles.

Cas couverts :
  - année précédente détectée automatiquement ;
  - aperçu : classes de l'année source avec leurs volumes ;
  - reprise des seules classes cochées (un tronc commun n'emporte pas la
    classe non cochée) ; UE et enseignants recopiés ;
  - relance idempotente puis ajout d'une classe supplémentaire = rattachement ;
  - liaisons de cours communs recopiées entre cours recopiés ;
  - une seule année « en cours », synchronisée avec Udshed Setting.
"""

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api import annee_academique, cours_commun
from udshed.udshed._fixture_factory import (
	make_academic_year,
	make_calendar_planing,
	make_course,
	make_faculty,
	make_field_of_study,
	make_level,
	make_teacher,
	make_teaching_unit,
	make_teaching_unit_value,
)


class TestAnneeAcademique(IntegrationTestCase):
	def setUp(self):
		self.source = make_academic_year("2026", "2027")
		self.cible = make_academic_year("2027", "2028")
		calendrier = make_calendar_planing()
		faculte = make_faculty()
		self.fil_a = make_field_of_study(faculte, calendrier, make_teacher())
		self.niv_a = make_level(self.fil_a)
		self.fil_b = make_field_of_study(faculte, calendrier, make_teacher())
		self.niv_b = make_level(self.fil_b)
		self.prof = make_teacher()
		ue = make_teaching_unit_value(self.source)

		self.propre_a = make_teaching_unit(make_course(), self.source, self.fil_a, self.niv_a, unite_de_valeur=ue)
		self.propre_a.append("table_enseignant", {"enseignant": self.prof.name, "type_de_cours": "Cours Magistral (CM)"})
		self.propre_a.save(ignore_permissions=True)
		self.tronc = make_teaching_unit(make_course(), self.source, self.fil_a, self.niv_a, credits=4)
		self.tronc.append("course_levels", {"filiere": self.fil_b.name, "niveau": self.niv_b.name, "course_poid": 2})
		self.tronc.save(ignore_permissions=True)
		self.propre_b = make_teaching_unit(make_course(), self.source, self.fil_b, self.niv_b)
		self.ue_code = ue.code

	def classes(self, *paires):
		return [{"filiere": f.name, "niveau": n.name} for f, n in paires]

	def cible_de(self, tu):
		return frappe.db.get_value("Teaching Unit", {"course": tu.course, "academic_year": self.cible.name}, "name")

	def test_annee_precedente(self):
		self.assertEqual(annee_academique.annee_precedente(self.cible.name), self.source.name)

	def test_apercu(self):
		data = annee_academique.apercu_grilles(self.cible.name, self.source.name)
		par_niveau = {str(c["niveau"]): c for c in data["classes"]}
		self.assertEqual(par_niveau[str(self.niv_a.name)]["cours"], 2)
		self.assertEqual(par_niveau[str(self.niv_b.name)]["cours"], 2)

	def test_reprise_des_seules_classes_cochees(self):
		stats = annee_academique.dupliquer_grilles(
			self.cible.name, self.source.name, self.classes((self.fil_a, self.niv_a))
		)
		self.assertEqual(stats["cours_crees"], 2)
		self.assertEqual(stats["ue_creees"], 1)
		self.assertFalse(self.cible_de(self.propre_b))

		tronc = frappe.get_doc("Teaching Unit", self.cible_de(self.tronc))
		self.assertEqual([(str(r.niveau), r.course_poid) for r in tronc.course_levels], [(str(self.niv_a.name), 4)])
		propre = frappe.get_doc("Teaching Unit", self.cible_de(self.propre_a))
		self.assertEqual([t.enseignant for t in propre.table_enseignant], [self.prof.name])
		self.assertEqual(frappe.db.get_value("Teaching Unit Value", propre.unite_de_valeur, ["code", "academic_year"]),
		                 (self.ue_code, self.cible.name))

	def test_relance_idempotente_puis_ajout_de_classe(self):
		a = self.classes((self.fil_a, self.niv_a))
		annee_academique.dupliquer_grilles(self.cible.name, self.source.name, a)
		stats = annee_academique.dupliquer_grilles(self.cible.name, self.source.name, a)
		self.assertEqual((stats["cours_crees"], stats["cours_rattaches"], stats["classes_deja_presentes"]), (0, 0, 2))

		stats = annee_academique.dupliquer_grilles(self.cible.name, self.source.name, self.classes((self.fil_b, self.niv_b)))
		self.assertEqual((stats["cours_crees"], stats["cours_rattaches"]), (1, 1))
		tronc = frappe.get_doc("Teaching Unit", self.cible_de(self.tronc))
		self.assertEqual(len(tronc.course_levels), 2)

	def test_sans_enseignants_sur_demande(self):
		annee_academique.dupliquer_grilles(self.cible.name, self.source.name, self.classes((self.fil_a, self.niv_a)),
		                                   copier_enseignants=0)
		self.assertFalse(frappe.get_doc("Teaching Unit", self.cible_de(self.propre_a)).table_enseignant)

	def test_liaisons_recopiees(self):
		cours_commun.lier_cours([self.propre_a.name, self.propre_b.name])
		stats = annee_academique.dupliquer_grilles(
			self.cible.name, self.source.name, self.classes((self.fil_a, self.niv_a), (self.fil_b, self.niv_b))
		)
		self.assertEqual(stats["liaisons"], 1)
		groupes = {frappe.db.get_value("Teaching Unit", self.cible_de(t), "groupe_cours_commun") for t in (self.propre_a, self.propre_b)}
		self.assertEqual(len(groupes), 1)
		self.assertNotIn(None, groupes)
		self.assertNotEqual(groupes, {frappe.db.get_value("Teaching Unit", self.propre_a.name, "groupe_cours_commun")})

	def test_une_seule_annee_en_cours(self):
		self.source.is_current_year = 1
		self.source.save(ignore_permissions=True)
		self.cible.reload()
		self.cible.is_current_year = 1
		self.cible.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Academic Year", self.source.name, "is_current_year"), 0)
		self.assertEqual(frappe.db.get_single_value("Udshed Setting", "current_year"), self.cible.name)

	def test_annee_fin_avant_debut_refusee(self):
		doc = frappe.get_doc("Academic Year", self.cible.name)
		doc.end_year = "2026"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)
