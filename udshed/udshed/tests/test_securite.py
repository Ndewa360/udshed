# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests des contrôles d'accès et des protections des endpoints publics.

Cas couverts :
  - un compte étudiant ne peut ni valider ni publier une session, ni
    exporter les notes d'une classe, ni modifier les niveaux, ni lire les
    rapports nominatifs ;
  - cloisonnement : un étudiant ne lit que SA fiche Student et SES résultats ;
  - un relevé (transcript) d'un autre étudiant est refusé ;
  - jetons signés : normalisation (casse, accents), expiration, falsification ;
  - l'enregistrement d'une inscription exige le jeton ;
  - les fiches PDF publiques exigent le jeton (ou le droit du personnel) ;
  - limitation des tentatives échouées.
"""

import frappe
from frappe.tests import IntegrationTestCase

from udshed import permissions
from udshed.api import candidature, inscription
from udshed.api.reregistration import delete_level, get_reregistration_report, reorder_levels
from udshed.api.saisie_notes import export_evaluations, publier_session, valider_notes
from udshed.api.transcript import get_transcript_data
from udshed.udshed._fixture_factory import (
	make_academic_year,
	make_calendar_planing,
	make_faculty,
	make_field_of_study,
	make_level,
	make_session_examen,
	make_student,
	make_teacher,
	make_user_with_role,
)
from udshed.utils import securite


class TestSecurite(IntegrationTestCase):
	def setUp(self):
		self.annee = make_academic_year("2026", "2027")
		self.calendrier = make_calendar_planing()
		self.faculte = make_faculty()
		self.filiere = make_field_of_study(self.faculte, self.calendrier, make_teacher())
		self.niveau = make_level(self.filiere)
		self.etudiant = make_student(self.filiere, self.niveau)
		self.autre_etudiant = make_student(self.filiere, self.niveau)
		self.session = make_session_examen(self.annee, self.calendrier, self.filiere, self.niveau)
		self.compte_etudiant = frappe.db.get_value("Student", self.etudiant.name, "utilisateur")
		self.assertTrue(self.compte_etudiant, "Student.after_insert doit créer le compte utilisateur")

	def tearDown(self):
		frappe.set_user("Administrator")

	def en_tant_que(self, user):
		frappe.set_user(user)
		self.addCleanup(frappe.set_user, "Administrator")

	# ------------------------------------------------------------------ #
	#  Endpoints réservés au personnel
	# ------------------------------------------------------------------ #
	def test_etudiant_ne_peut_pas_valider_ni_publier(self):
		self.en_tant_que(self.compte_etudiant)
		with self.assertRaises(frappe.PermissionError):
			valider_notes(self.session.name)
		with self.assertRaises(frappe.PermissionError):
			publier_session(self.session.name)

	def test_enseignant_sans_droit_session_ne_peut_pas_publier(self):
		enseignant = make_user_with_role("Teacher")
		self.en_tant_que(enseignant.name)
		with self.assertRaises(frappe.PermissionError):
			publier_session(self.session.name)

	def test_etudiant_ne_peut_pas_exporter_les_notes(self):
		self.en_tant_que(self.compte_etudiant)
		with self.assertRaises(frappe.PermissionError):
			export_evaluations(
				self.annee.name, self.filiere.name, self.niveau.level, "Semestre 1", "UE-INEXISTANTE"
			)

	def test_etudiant_ne_peut_pas_modifier_les_niveaux(self):
		self.en_tant_que(self.compte_etudiant)
		with self.assertRaises(frappe.PermissionError):
			delete_level(self.filiere.name, self.niveau.level)
		with self.assertRaises(frappe.PermissionError):
			reorder_levels(self.filiere.name, [self.niveau.name])
		self.assertTrue(frappe.db.exists("Field of study Level", self.niveau.name))

	def test_etudiant_ne_peut_pas_lire_le_rapport_de_reinscription(self):
		self.en_tant_que(self.compte_etudiant)
		with self.assertRaises(frappe.PermissionError):
			get_reregistration_report()

	# ------------------------------------------------------------------ #
	#  Cloisonnement des données étudiantes
	# ------------------------------------------------------------------ #
	def test_etudiant_ne_lit_que_sa_fiche(self):
		self.en_tant_que(self.compte_etudiant)
		self.assertTrue(frappe.has_permission("Student", "read", doc=self.etudiant.name))
		self.assertFalse(frappe.has_permission("Student", "read", doc=self.autre_etudiant.name))
		visibles = frappe.get_list("Student", pluck="name")
		self.assertEqual(visibles, [self.etudiant.name])

	def test_conditions_vides_pour_le_personnel(self):
		self.assertEqual(permissions.student_query("Administrator"), "")
		self.assertEqual(permissions.inscription_query("Administrator"), "")
		self.assertEqual(permissions.resultat_query("Administrator"), "")

	def test_releve_d_un_autre_etudiant_refuse(self):
		self.en_tant_que(self.compte_etudiant)
		with self.assertRaises(frappe.PermissionError):
			get_transcript_data({"name": self.autre_etudiant.name})

	# ------------------------------------------------------------------ #
	#  Jetons signés
	# ------------------------------------------------------------------ #
	def test_jeton_inscription_normalise(self):
		jeton = inscription._creer_jeton("CAND-2026-00001", "Ébé Ndongo")
		self.assertTrue(inscription._verifier_jeton(jeton, " cand-2026-00001 ", "EBE NDONGO"))
		self.assertFalse(inscription._verifier_jeton(jeton, "CAND-2026-00002", "Ébé Ndongo"))
		self.assertFalse(inscription._verifier_jeton(jeton, "CAND-2026-00001", "Autre"))

	def test_jeton_inscription_falsifie_ou_expire(self):
		jeton = inscription._creer_jeton("CAND-2026-00001", "Nom")
		expiration, signature = jeton.split(".", 1)
		# Repousser l'expiration invalide la signature.
		falsifie = f"{int(expiration) + 3600}.{signature}"
		self.assertFalse(inscription._verifier_jeton(falsifie, "CAND-2026-00001", "Nom"))
		expire = f"1.{securite.signer('inscription', 'CAND-2026-00001', 'nom', 1)}"
		self.assertFalse(inscription._verifier_jeton(expire, "CAND-2026-00001", "Nom"))
		self.assertFalse(inscription._verifier_jeton("n'importe quoi", "CAND-2026-00001", "Nom"))
		self.assertFalse(inscription._verifier_jeton(None, "CAND-2026-00001", "Nom"))

	def test_enregistrer_inscription_exige_le_jeton(self):
		self.en_tant_que("Guest")
		with self.assertRaises(frappe.ValidationError):
			inscription.enregistrer_inscription("CAND-2026-00001", "Nom", donnees="{}")
		with self.assertRaises(frappe.ValidationError):
			inscription.enregistrer_inscription("CAND-2026-00001", "Nom", donnees="{}", token="1.abc")

	def test_fiche_inscription_exige_jeton_pour_invite(self):
		doc = frappe._dict(matricule="25UDS001", name="25C.001", doctype="Inscription Academique")
		self.en_tant_que("Guest")
		with self.assertRaises(frappe.PermissionError):
			inscription._verifier_acces_fiche_inscription(doc, None)
		with self.assertRaises(frappe.PermissionError):
			inscription._verifier_acces_fiche_inscription(doc, inscription.jeton_fiche_inscription("AUTRE"))
		# Jeton valide : aucune exception.
		inscription._verifier_acces_fiche_inscription(doc, inscription.jeton_fiche_inscription("25UDS001"))
		self.assertIn("jeton=", inscription._pdf_url("25UDS001"))

	def test_fiche_candidature_exige_jeton_pour_invite(self):
		doc = frappe._dict(name="CAND-2026-00001", doctype="Session Inscription Candidate")
		self.en_tant_que("Guest")
		with self.assertRaises(frappe.PermissionError):
			candidature._verifier_acces_fiche_candidature(doc, None)
		with self.assertRaises(frappe.PermissionError):
			candidature._verifier_acces_fiche_candidature(
				doc, candidature.jeton_fiche_candidature("CAND-2026-00002")
			)
		candidature._verifier_acces_fiche_candidature(
			doc, candidature.jeton_fiche_candidature("CAND-2026-00001")
		)

	# ------------------------------------------------------------------ #
	#  Limitation des tentatives
	# ------------------------------------------------------------------ #
	def test_limitation_des_tentatives(self):
		portee, ident = "test-securite", frappe.generate_hash(length=8)
		self.addCleanup(securite.reinitialiser_tentatives, portee, ident)
		for _i in range(3):
			securite.verifier_tentatives(portee, ident, 3, 60)
			securite.enregistrer_echec(portee, ident, 60)
		with self.assertRaises(frappe.RateLimitExceededError):
			securite.verifier_tentatives(portee, ident, 3, 60)
		securite.reinitialiser_tentatives(portee, ident)
		securite.verifier_tentatives(portee, ident, 3, 60)
