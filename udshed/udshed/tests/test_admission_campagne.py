# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Parcours d'admission piloté par la campagne (Session Inscription).

  - dépôt refusé hors période de dépôt ; accepté pendant, campagne rattachée ;
  - centre d'examen limité aux centres de la campagne ;
  - un admis finalise APRÈS la clôture des dépôts, jusqu'à la date limite
	d'inscription de la campagne ;
  - l'inscription (année, matricule, UE) suit l'année de RENTRÉE de la campagne,
	pas l'année en cours des réglages ;
  - classe sans grille : inscription enregistrée et scolarité alertée ;
  - compte étudiant : identifiant Frappe = matricule, lien d'activation ;
  - droits : coordonnateur en lecture sur ses filières, désistement réservé
	au responsable des admissions ;
  - espace étudiant : grille et planning de SES cours uniquement ;
  - emails et pages publiques aux couleurs de l'établissement configuré.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from udshed.api import etudiant, inscription
from udshed.udshed._fixture_factory import (
	make_agent_scolarite,
	make_academic_year,
	make_course,
	make_faculty,
	make_field_of_study,
	make_level,
	make_teacher,
	make_teaching_unit,
	make_user_with_role,
	suppress_commits,
)
from udshed.udshed.doctype.session_inscription_candidate.session_inscription_candidate import (
	droits_candidature,
)
from udshed.utils import campagne


class TestAdmissionCampagne(IntegrationTestCase):
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
		# La finalisation de l'inscription commite sa transaction : neutralisé ici,
		# sinon les données du test resteraient en base (doublons, limite de
		# création de comptes « Throttled » pour les autres tests).
		self._commits = suppress_commits()
		self._commits.__enter__()
		self._mails = patch("frappe.sendmail")
		self._mails.start()
		self._jobs = patch("frappe.enqueue")
		self._jobs.start()
		# Année EN COURS 2025-2026 ; campagne pour la RENTRÉE 2026-2027.
		self.courante = make_academic_year("2025", "2026")
		self.cible = make_academic_year("2026", "2027")
		frappe.db.set_single_value("Udshed Setting", "current_year", self.courante.name)
		self.fos = make_field_of_study(make_faculty(), None, make_teacher())
		self.niveau = make_level(self.fos)
		for nom in frappe.get_all("Session Inscription", filters={"status": "Open"}, pluck="name"):
			frappe.db.set_value("Session Inscription", nom, "status", "Closed")
		self.campagne = frappe.get_doc({
			"doctype": "Session Inscription", "academic_year": self.cible.name, "status": "Open",
			"opening_date": add_days(today(), -10), "closing_date": add_days(today(), 10),
			"centres_examen": "Centre Nord\nCentre Sud",
		}).insert(ignore_permissions=True)

	def tearDown(self):
		self._mails.stop()
		self._jobs.stop()
		frappe.set_user("Administrator")
		frappe.db.rollback()
		self._commits.__exit__(None, None, None)

	# ------------------------------------------------------------------ outils
	def candidature(self, **valeurs):
		doc = frappe.get_doc({
			"doctype": "Session Inscription Candidate",
			"first_name": "NGONO", "last_name": "AMINA", "email": frappe.generate_hash(length=8) + "@example.com",
			"phone": "+237699000000", "birth_place": "Douala", "birthdate": "2005-03-02", "sexe": "Femme",
			"birth_certificate": "/files/a.pdf", "access_diploma_copy": "/files/b.pdf",
			"id_photo": "/files/c.png", "remittance_receipt": "/files/d.pdf",
			"examination_centre": "Centre Nord",
			"choix_de_formation": [{"choix": "1er choix", "filiere": self.fos.name, "niveau": self.niveau.name}],
			**valeurs,
		})
		frappe.set_user("Guest")
		try:
			doc.insert(ignore_permissions=True)
		finally:
			frappe.set_user("Administrator")
		return doc

	def admettre(self, doc):
		frappe.db.set_value("Session Inscription Candidate", doc.name, {
			"candidature_status": "Accepté", "finaliser_avant": add_days(today(), 15)})
		return frappe._dict(frappe.get_doc("Session Inscription Candidate", doc.name).as_dict())

	# ------------------------------------------------------------------ campagne
	def test_depot_pendant_la_periode_rattache_la_campagne(self):
		doc = self.candidature()
		self.assertEqual(doc.session_inscription, self.campagne.name)
		self.assertEqual(campagne.annee_cible(doc.name), self.cible.name)

	def test_depot_hors_periode_refuse(self):
		frappe.db.set_value("Session Inscription", self.campagne.name, "closing_date", add_days(today(), -1))
		frappe.clear_document_cache("Session Inscription", self.campagne.name)
		with self.assertRaises(frappe.ValidationError):
			self.candidature()

	def test_centre_hors_campagne_refuse(self):
		with self.assertRaises(frappe.ValidationError):
			self.candidature(examination_centre="Centre Inconnu")

	def test_infos_publiques(self):
		infos = campagne.infos_publiques()
		self.assertEqual(infos["etat"], "ouverte")
		self.assertEqual(infos["campagne"]["academic_year"], self.cible.name)
		self.assertEqual(infos["campagne"]["centres"], ["Centre Nord", "Centre Sud"])
		self.assertTrue(infos["etablissement"]["nom"])

	# ------------------------------------------------------------------ inscription
	def test_finalisation_apres_cloture_sur_l_annee_cible(self):
		tu = make_teaching_unit(make_course(), self.cible, self.fos, self.niveau)
		dossier = self.admettre(self.candidature())
		# Dépôts clos : l'admis peut quand même s'inscrire (date limite non atteinte).
		frappe.db.set_value("Session Inscription", self.campagne.name, {
			"status": "Closed", "closing_date": add_days(today(), -1)})
		frappe.clear_document_cache("Session Inscription", self.campagne.name)
		campagne.exiger_inscription_ouverte(dossier)

		res = inscription._finaliser_inscription_complete(dossier, {"annee_academique": "1999-2000"})
		ia = frappe.get_doc("Inscription Academique", {"dossier_origine": dossier.name})
		self.assertEqual(ia.annee_academique, self.cible.name)  # ni le champ envoyé, ni l'année courante
		self.assertTrue(res["matricule"].startswith("26"))
		rr = frappe.get_doc("Academic Reregistration", {"student": res["student_name"]})
		self.assertEqual(rr.academic_year, self.cible.name)
		self.assertEqual([c.teaching_unit for c in rr.cours_inscrits], [tu.name])

	def test_inscription_close_apres_la_date_limite(self):
		dossier = self.admettre(self.candidature())
		frappe.db.set_value("Session Inscription", self.campagne.name, {
			"closing_date": add_days(today(), -20), "opening_date": add_days(today(), -40),
			"date_limite_inscription": add_days(today(), -1)})
		frappe.clear_document_cache("Session Inscription", self.campagne.name)
		with self.assertRaises(frappe.ValidationError):
			campagne.exiger_inscription_ouverte(dossier)

	def test_classe_sans_grille_alerte_la_scolarite(self):
		dossier = self.admettre(self.candidature())
		agent = make_agent_scolarite(dossier.filiere)
		res = inscription._finaliser_inscription_complete(dossier, {})
		self.assertEqual(res["enrolled_count"], 0)
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": agent.name, "document_type": "Inscription Academique"}))

	def test_compte_etudiant_par_matricule(self):
		make_teaching_unit(make_course(), self.cible, self.fos, self.niveau)
		dossier = self.admettre(self.candidature())
		res = inscription._finaliser_inscription_complete(dossier, {})
		user = frappe.db.get_value("Student", res["student_name"], "utilisateur")
		self.assertEqual(frappe.db.get_value("User", user, "username"), res["matricule"])
		self.assertIn("Student", frappe.get_roles(user))
		from udshed.utils.compte_etudiant import lien_activation

		self.assertIn("/update-password?key=", lien_activation(user))

	# ------------------------------------------------------------------ droits
	def test_droits_par_role(self):
		doc = frappe.get_doc("Session Inscription Candidate", self.candidature().name)
		agent = make_agent_scolarite(doc.filiere)
		frappe.set_user(agent.name)
		d = droits_candidature(doc)
		self.assertTrue(d["accepter"] and d["rejeter"])
		self.assertFalse(d["desister"])

		coord = make_user_with_role("Coordonateur")
		frappe.set_user(coord.name)
		self.assertFalse(droits_candidature(doc)["decider"])
		# Coordonnateur sans filière coordonnée : aucun dossier visible.
		self.assertEqual(frappe.get_list("Session Inscription Candidate", filters={"name": doc.name}), [])

	# ------------------------------------------------------------------ espace étudiant
	def test_espace_etudiant_limite_a_ses_cours(self):
		tu = make_teaching_unit(make_course(), self.cible, self.fos, self.niveau)
		autre = make_teaching_unit(make_course(), self.cible, self.fos, self.niveau)
		dossier = self.admettre(self.candidature())
		res = inscription._finaliser_inscription_complete(dossier, {})
		rr = frappe.get_doc("Academic Reregistration", {"student": res["student_name"]})
		rr.cours_inscrits = [c for c in rr.cours_inscrits if c.teaching_unit == tu.name]
		rr.flags.ignore_validate = True
		rr.flags.ignore_mandatory = True
		rr.save(ignore_permissions=True)

		frappe.set_user(frappe.db.get_value("Student", res["student_name"], "utilisateur"))
		grille = etudiant.ma_grille(self.cible.name)
		self.assertEqual([c["code"] for c in grille["cours"]], [tu.course])
		self.assertNotIn(autre.course, [c["code"] for c in grille["cours"]])
		self.assertEqual(etudiant.profil()["matricule"], res["matricule"])

	def test_espace_etudiant_refuse_un_compte_sans_fiche(self):
		frappe.set_user(make_user_with_role("Student").name)
		with self.assertRaises(frappe.PermissionError):
			etudiant.profil()

	# ------------------------------------------------------------------ identité
	def test_emails_et_accueil_aux_couleurs_de_l_etablissement(self):
		frappe.db.set_single_value("Udshed Setting", "school_name", "Université de Test")
		frappe.clear_document_cache("Udshed Setting", "Udshed Setting")
		html = frappe.render_template("templates/emails/candidature_receipt.html", {
			"first_name": "A", "last_name": "B", "doc_name": "CAND-1", "jeton_fiche": "x", "base_url": ""})
		self.assertIn("Université de Test", html)
		self.assertNotIn("Udshed</h1>", html)
		self.assertIn("Ndewa360", html)
		accueil = frappe.db.get_value("Web Page", {"route": "index"}, "main_section_html")
		if accueil:
			rendu = frappe.render_template(accueil, {})
			self.assertIn("Université de Test", rendu)
			self.assertIn("/candidature/new", rendu)
