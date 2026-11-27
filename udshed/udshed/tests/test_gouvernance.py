# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Gouvernance : périmètre par filière (agents, doyens), périodes de saisie, dérogations, tableaux de bord."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, now_datetime

from udshed.api import direction, saisie_periode
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
	suppress_commits,
)
from udshed.utils import perimetre
from udshed.utils import periode_saisie as ps


class TestGouvernance(IntegrationTestCase):
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
		self.annee = make_academic_year("2033", "2034")
		cal = make_calendar_planing()
		self.fac_a, self.fac_b = make_faculty(), make_faculty()
		self.fil_a = make_field_of_study(self.fac_a, cal, make_teacher())
		self.niv_a = make_level(self.fil_a)
		self.fil_b = make_field_of_study(self.fac_b, cal, make_teacher())
		self.niv_b = make_level(self.fil_b)
		self.prof = make_teacher()
		self.user_prof = make_user_with_role("Teacher").name
		frappe.db.set_value("Teacher", self.prof.name, "email", self.user_prof)
		self.cours = make_teaching_unit(make_course(), self.annee, self.fil_a, self.niv_a)
		self.cours.append("table_enseignant", {"enseignant": self.prof.name, "type_de_cours": "Cours Magistral (CM)"})
		self.cours.save(ignore_permissions=True)
		self.semestre = self.cours.semestre
		self.doyen_a = make_user_with_role("Doyen").name
		frappe.db.set_value("Faculty", self.fac_a.name, "doyen", self.doyen_a)
		self.doyen_b = make_user_with_role("Doyen").name
		frappe.db.set_value("Faculty", self.fac_b.name, "doyen", self.doyen_b)

	def tearDown(self):
		frappe.set_user("Administrator")
		self._commits.__exit__(None, None, None)
		frappe.db.rollback()

	def agent(self, filiere):
		user = make_user_with_role("Agent de scolarité").name
		fos = frappe.get_doc("Field of study", filiere)
		fos.append("agents_scolarite", {"utilisateur": user})
		fos.save(ignore_permissions=True)
		return user

	def periode(self, ouverture, fermeture, faculte=None, type_eval="Examen de session normale"):
		return frappe.get_doc({"doctype": "Periode Saisie Notes", "academic_year": self.annee.name, "semestre": self.semestre,
							   "type_evaluation": type_eval, "faculte": faculte, "ouverture": ouverture,
							   "fermeture": fermeture}).insert(ignore_permissions=True)

	# ------------------------------------------------------------------ périmètre
	def test_agent_ne_voit_que_sa_filiere(self):
		user = self.agent(self.fil_a.name)
		self.assertEqual(perimetre.filieres(user), [self.fil_a.name])
		for fil in (self.fil_a, self.fil_b):
			doc = frappe.get_doc({"doctype": "Inscription Academique", "nom_prenom": "Test " + fil.name,
								  "annee_academique": self.annee.name, "filiere": fil.name, "classe": "Licence 1"})
			doc.flags.ignore_validate = True
			doc.insert(ignore_permissions=True, ignore_mandatory=True)
		frappe.set_user(user)
		filieres = set(frappe.get_list("Inscription Academique", filters={"annee_academique": self.annee.name}, pluck="filiere"))
		self.assertEqual(filieres, {self.fil_a.name})
		with self.assertRaises(frappe.PermissionError):
			perimetre.exiger_filiere(self.fil_b.name)

	def test_agent_sans_filiere_ne_voit_rien(self):
		user = make_user_with_role("Agent de scolarité").name
		self.assertEqual(perimetre.filieres(user), [])
		frappe.set_user(user)
		self.assertEqual(frappe.get_list("Inscription Academique", limit=5), [])

	def test_doyen_dirige_les_filieres_de_sa_faculte(self):
		self.assertEqual(perimetre.facultes_dirigees(self.doyen_a), [self.fac_a.name])
		self.assertIn(self.fil_a.name, perimetre.filieres(self.doyen_a))
		self.assertNotIn(self.fil_b.name, perimetre.filieres(self.doyen_a))

	def test_responsable_inscriptions_reste_global(self):
		self.assertIsNone(perimetre.filieres(make_user_with_role("Registration Manager").name))

	# ------------------------------------------------------------------ période de saisie
	def test_sans_periode_saisie_libre(self):
		frappe.set_user(self.user_prof)
		e = ps.etat(self.annee.name, self.semestre, self.cours.name, self.fil_a.name, "examen")
		self.assertTrue(e.ouverte)

	def test_apres_date_limite_enseignant_bloque_coordination_exemptee(self):
		self.periode(add_days(now_datetime(), -10), add_days(now_datetime(), -1))
		frappe.set_user(self.user_prof)
		with self.assertRaises(frappe.ValidationError):
			ps.exiger_saisie_ouverte(self.annee.name, self.semestre, self.cours.name, self.fil_a.name, "examen")
		frappe.set_user(make_user_with_role("Coordonateur").name)
		self.assertTrue(ps.etat(self.annee.name, self.semestre, self.cours.name, self.fil_a.name, "examen").ouverte)

	def test_periode_de_faculte_prioritaire(self):
		self.periode(add_days(now_datetime(), -10), add_days(now_datetime(), -1))
		self.periode(add_days(now_datetime(), -10), add_days(now_datetime(), 5), faculte=self.fac_a.name)
		frappe.set_user(self.user_prof)
		e = ps.etat(self.annee.name, self.semestre, self.cours.name, self.fil_a.name, "examen")
		self.assertTrue(e.ouverte)

	def test_doyen_ne_fixe_que_les_periodes_de_sa_faculte(self):
		frappe.set_user(self.doyen_a)
		with self.assertRaises(frappe.PermissionError):
			self.periode(now_datetime(), add_days(now_datetime(), 5), faculte=self.fac_b.name)
		with self.assertRaises(frappe.PermissionError):
			self.periode(now_datetime(), add_days(now_datetime(), 5))  # période d'établissement : DAA
		self.periode(now_datetime(), add_days(now_datetime(), 5), faculte=self.fac_a.name)

	def test_confirmation_pendant_la_periode(self):
		self.periode(add_days(now_datetime(), -1), add_days(now_datetime(), 5))
		frappe.set_user(self.user_prof)
		saisie_periode.confirmer_saisie(self.annee.name, self.fil_a.name, self.niv_a.name, self.semestre, self.cours.name, "Examen")
		e = ps.etat(self.annee.name, self.semestre, self.cours.name, self.fil_a.name, "examen", niveau=self.niv_a.name)
		self.assertTrue(e.confirmation)

	# ------------------------------------------------------------------ dérogations
	def test_derogation_demandee_puis_accordee_par_le_doyen(self):
		self.periode(add_days(now_datetime(), -10), add_days(now_datetime(), -1))
		frappe.set_user(self.user_prof)
		res = saisie_periode.demander_derogation(self.annee.name, self.fil_a.name, self.niv_a.name, self.semestre,
												 self.cours.name, "Copies remises en retard", "Examen")
		doc = frappe.get_doc("Derogation Saisie", res["name"])
		self.assertEqual((doc.statut, doc.faculte), ("Demandée", self.fac_a.name))
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": self.doyen_a, "document_name": doc.name}))
		frappe.set_user(self.doyen_b)
		with self.assertRaises(frappe.PermissionError):  # doyen d'une autre faculté
			saisie_periode.decider_derogation(doc.name, 1, add_days(now_datetime(), 2))
		frappe.set_user(self.doyen_a)
		saisie_periode.decider_derogation(doc.name, 1, add_days(now_datetime(), 2), "Accordé")
		frappe.set_user(self.user_prof)
		e = ps.exiger_saisie_ouverte(self.annee.name, self.semestre, self.cours.name, self.fil_a.name, "examen")
		self.assertTrue(e.derogation)

	def test_pas_de_derogation_si_la_saisie_est_ouverte(self):
		frappe.set_user(self.user_prof)
		with self.assertRaises(frappe.ValidationError):
			saisie_periode.demander_derogation(self.annee.name, self.fil_a.name, self.niv_a.name, self.semestre,
											   self.cours.name, "motif", "Examen")

	# ------------------------------------------------------------------ tableaux de bord
	def test_tableau_de_bord_du_doyen(self):
		frappe.set_user(self.doyen_a)
		d = direction.tableau_faculte(self.annee.name)
		self.assertEqual(d["faculte"], self.fac_a.name)
		self.assertIn(self.fil_a.name, [l["filiere"] for l in d["lignes"]])
		with self.assertRaises(frappe.PermissionError):
			direction.tableau_faculte(self.annee.name, self.fac_b.name)
		with self.assertRaises(frappe.PermissionError):
			direction.tableau_etablissement(self.annee.name)

	def test_tableau_de_bord_du_daa(self):
		frappe.set_user(make_user_with_role("Directeur des Affaires Académiques").name)
		d = direction.tableau_etablissement(self.annee.name)
		self.assertTrue({self.fac_a.name, self.fac_b.name} <= {l["faculte"] for l in d["lignes"]})
