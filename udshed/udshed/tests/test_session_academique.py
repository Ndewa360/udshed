# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Année académique de la session et filtres du périmètre."""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from udshed.udshed._fixture_factory import (
	make_academic_year,
	make_calendar_planing,
	make_faculty,
	make_field_of_study,
	make_level,
	make_teacher,
	make_user_with_role,
	suppress_commits,
)
from udshed.utils import session_academique as sa


class TestSessionAcademique(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._sans_limite = patch("frappe.core.doctype.user.user.throttle_user_creation")
		cls._sans_limite.start()

	@classmethod
	def tearDownClass(cls):
		cls._sans_limite.stop()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		self._commits = suppress_commits()
		self._commits.__enter__()
		self.a1 = make_academic_year("2031", "2032")
		self.a2 = make_academic_year("2032", "2033")
		faculte = make_faculty()
		self.coord = make_teacher()
		self.fil_a = make_field_of_study(faculte, make_calendar_planing(), self.coord)
		self.niv_a = make_level(self.fil_a)
		self.fil_b = make_field_of_study(faculte, make_calendar_planing(), make_teacher())
		self.niv_b = make_level(self.fil_b)
		frappe.db.set_value("Field of study Level", self.niv_a.name, "coordonateur", self.coord.name)
		self.sid = "test-sid-" + frappe.generate_hash(length=8)

	def tearDown(self):
		frappe.cache.hdel(sa.CLE, self.sid)
		frappe.set_user("Administrator")
		self._commits.__exit__(None, None, None)
		frappe.db.rollback()

	def en_session(self, user):
		frappe.set_user(user)
		return patch.object(frappe, "session", SimpleNamespace(user=user, sid=self.sid, data=frappe._dict()))

	def test_annee_fixee_pour_la_session(self):
		user = make_user_with_role("Agent de scolarité").name
		with self.en_session(user):
			self.assertEqual(sa.annee_choisie(), "")
			sa.choisir_annee(self.a1.name)
			self.assertEqual(sa.annee_session(), self.a1.name)
			sa.choisir_annee(self.a1.name)  # même année : sans effet
			with self.assertRaises(frappe.ValidationError):
				sa.choisir_annee(self.a2.name)  # changer d'année : se reconnecter
			sa.effacer_session()
			self.assertEqual(sa.annee_choisie(), "")

	def test_etudiant_ne_choisit_pas(self):
		user = make_user_with_role("Student").name
		with self.en_session(user), self.assertRaises(frappe.PermissionError):
			sa.choisir_annee(self.a1.name)

	def test_boot_donne_l_annee_et_la_valeur_par_defaut(self):
		user = make_user_with_role("Agent de scolarité").name
		with self.en_session(user):
			sa.choisir_annee(self.a2.name)
			boot = frappe._dict(user={"defaults": {}})
			sa.boot(boot)
		self.assertEqual(boot.udshed_session["annee"], self.a2.name)
		self.assertTrue(boot.udshed_session["choisie"])
		self.assertEqual(boot.user["defaults"]["academic_year"], self.a2.name)

	def test_coordinateur_ne_voit_que_sa_classe(self):
		user = make_user_with_role("Coordonateur").name
		frappe.db.set_value("Teacher", self.coord.name, "email", user)
		with self.en_session(user):
			ctx = sa.contexte_filtres()
		self.assertFalse(ctx["global"])
		self.assertEqual([n["value"] for n in ctx["niveaux"]], [self.niv_a.name])
		self.assertEqual([f["value"] for f in ctx["filieres"]], [self.fil_a.name])

	def test_scolarite_voit_tout(self):
		# Scolarité centrale (Registration Manager) : tout l'établissement.
		user = make_user_with_role("Registration Manager").name
		with self.en_session(user):
			ctx = sa.contexte_filtres()
		self.assertTrue(ctx["global"])
		niveaux = {n["value"] for n in ctx["niveaux"]}
		self.assertTrue({self.niv_a.name, self.niv_b.name} <= niveaux)
