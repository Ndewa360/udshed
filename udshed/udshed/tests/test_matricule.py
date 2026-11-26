# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Matricules : format configurable, lettre au choix, numérotation sans doublon."""

import frappe
from frappe.tests import IntegrationTestCase

from udshed.udshed._fixture_factory import (
	make_academic_year,
	make_calendar_planing,
	make_faculty,
	make_field_of_study,
	make_teacher,
	suppress_commits,
)
from udshed.utils import matricule


class TestMatricule(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._commits = suppress_commits()
		self._commits.__enter__()
		self.annee = make_academic_year("2026", "2027")
		self.fos = make_field_of_study(make_faculty(), make_calendar_planing(), make_teacher())
		self.reglages = frappe.get_single("Udshed Setting")
		self.avant = {c: self.reglages.get(c) for c in ("format_matricule", "mode_lettre_matricule", "lettre_matricule_fixe")}

	def tearDown(self):
		self._commits.__exit__(None, None, None)
		frappe.db.rollback()
		frappe.clear_document_cache("Udshed Setting", "Udshed Setting")

	def regler(self, **valeurs):
		for champ, valeur in valeurs.items():
			frappe.db.set_single_value("Udshed Setting", champ, valeur)
		frappe.clear_document_cache("Udshed Setting", "Udshed Setting")

	def test_format_par_defaut_annee_lettre_numero(self):
		self.regler(format_matricule="{AA}{L}{###}", mode_lettre_matricule=matricule.MODE_FIXE, lettre_matricule_fixe="C")
		premier = matricule.generer(self.annee.name)
		self.assertRegex(premier, r"^26C\d{3}$")

	def test_numero_suit_les_matricules_existants(self):
		self.regler(format_matricule="{AA}{L}{###}", mode_lettre_matricule=matricule.MODE_FIXE, lettre_matricule_fixe="Q")
		prefixe = matricule.gabarit(self.annee.name)[0]
		self.assertEqual(prefixe, "26Q")
		maximum = matricule._max_numero("26Q", "")
		self.assertEqual(matricule.generer(self.annee.name), "26Q" + str(maximum + 1).zfill(3))

	def test_lettre_de_la_filiere_et_code(self):
		frappe.db.set_value("Field of study", self.fos.name, "lettre_matricule", "k")
		self.regler(format_matricule="{AAAA}-{FIL}{L}{####}", mode_lettre_matricule=matricule.MODE_FILIERE,
					lettre_matricule_fixe="")
		code = (self.fos.field_of_study_code or "").upper()
		self.assertRegex(matricule.generer(self.annee.name, filiere=self.fos.name), rf"^2026-{code}K\d{{4}}$")

	def test_suite_des_campagnes(self):
		self.regler(format_matricule="{A}{L}{##}", mode_lettre_matricule=matricule.MODE_CAMPAGNE)
		lettre = matricule.lettre_campagne(academic_year=self.annee.name)
		self.assertRegex(lettre, r"^[A-Z]+$")
		self.assertTrue(matricule.generer(self.annee.name).startswith("6" + lettre))

	def test_formats_invalides_refuses(self):
		for fmt in ("{AA}{L}", "{AA}{###}{##}", "{AA}{X}{###}", "{AA}{L}{#}", "ab cd {###}"):
			with self.subTest(fmt=fmt), self.assertRaises(frappe.ValidationError):
				matricule.valider_format(fmt)

	def test_reglages_valident_le_format(self):
		doc = frappe.get_single("Udshed Setting")
		doc.format_matricule = "{AA}{L}"
		with self.assertRaises(frappe.ValidationError):
			doc.validate()
		doc.format_matricule = "{aa}{l}{###}"
		doc.lettre_matricule_fixe = "c"
		doc.validate()
		self.assertEqual((doc.format_matricule, doc.lettre_matricule_fixe), ("{AA}{L}{###}", "C"))

	def test_apercu_pour_le_formulaire(self):
		res = matricule.apercu("{AA}{L}{###}", matricule.MODE_FIXE, "B")
		self.assertRegex(res["exemple"], r"^\d{2}B\d{3}$")
