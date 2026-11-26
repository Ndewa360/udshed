# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Actes académiques, diplomation, requêtes, babillard, saisie par la scolarité."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api import actes, babillard, requetes
from udshed.udshed._fixture_factory import (
	make_academic_year,
	make_calendar_planing,
	make_course,
	make_faculty,
	make_field_of_study,
	make_level,
	make_session_examen,
	make_session_examen_note,
	make_student,
	make_teacher,
	make_teaching_unit,
	make_user_with_role,
	suppress_commits,
)
from udshed.utils import actes as moteur
from udshed.utils import diplomation


class TestActesDiplomation(IntegrationTestCase):
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
		moteur.creer_modeles_defaut()
		self.annee = make_academic_year("2026", "2027")
		frappe.db.set_single_value("Udshed Setting", "current_year", self.annee.name)
		self.cal = make_calendar_planing()
		self.fos = make_field_of_study(make_faculty(), self.cal, make_teacher())
		self.l3 = make_level(self.fos, "Licence 3", 3)
		self.student = make_student(self.fos, self.l3, niveau_actuel="Licence 3")
		self.user = frappe.db.get_value("Student", self.student.name, "utilisateur")
		self.responsable = make_user_with_role("Responsable Diplomation")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		self._commits.__exit__(None, None, None)

	def inscrire(self):
		reg = frappe.get_doc({"doctype": "Academic Reregistration", "student": self.student.name,
							  "academic_year": self.annee.name, "filiere": self.fos.name, "niveau": "Licence 3",
							  "semestre": "Les deux", "statut": "Validée"})
		reg.flags.ignore_validate = True
		reg.flags.ignore_mandatory = True
		reg.insert(ignore_permissions=True)

	def en_tant_que(self, user, fn, *a, **k):
		frappe.set_user(user)
		try:
			return fn(*a, **k)
		finally:
			frappe.set_user("Administrator")

	# ------------------------------------------------------------------ actes
	def test_modeles_par_defaut(self):
		for titre in ("Certificat de scolarité", "Carte d'étudiant", "Relevé de notes", "Attestation de réussite", "Diplôme"):
			self.assertTrue(frappe.db.exists("Modele Acte", titre))

	def test_certificat_libre_service_et_verification(self):
		with self.assertRaises(frappe.ValidationError):  # pas encore inscrit
			self.en_tant_que(self.user, actes.obtenir, "Certificat de scolarité")
		self.inscrire()
		res = self.en_tant_que(self.user, actes.obtenir, "Certificat de scolarité")
		self.assertEqual(res["statut"], "Disponible")
		self.en_tant_que(self.user, actes.telecharger, res["name"])
		self.assertTrue(frappe.response["filecontent"].startswith(b"%PDF"))
		code = frappe.db.get_value("Acte Academique", res["name"], "code_verification")
		v = actes.verifier(code)
		self.assertTrue(v["valide"])
		self.assertEqual(v["matricule"], self.student.matricule)
		self.assertFalse(actes.verifier("FAUXCODE")["valide"])

	def test_carte_etudiant_format_carte(self):
		self.inscrire()
		modele = frappe.get_doc("Modele Acte", "Carte d'étudiant")
		html = moteur.html(modele, self.student.name, signer=True)
		self.assertIn("85.6mm 54mm", html)
		self.assertIn(self.student.matricule, html)

	def test_un_etudiant_ne_telecharge_pas_l_acte_d_un_autre(self):
		self.inscrire()
		res = self.en_tant_que(self.user, actes.obtenir, "Certificat de scolarité")
		autre = make_student(self.fos, self.l3)
		with self.assertRaises(frappe.PermissionError):
			self.en_tant_que(frappe.db.get_value("Student", autre.name, "utilisateur"), actes.telecharger, res["name"])

	# ------------------------------------------------------------------ diplomation + actes signés
	def _diplomer(self):
		self.inscrire()
		jury = frappe.get_doc({"doctype": "Jury Diplomation", "academic_year": self.annee.name, "filiere": self.fos.name,
							   "cycle": "Licence", "date_jury": "2027-07-10"}).insert(ignore_permissions=True)
		with patch.object(diplomation, "bilan_cycle",
						  return_value={"total": 180, "valides": 180, "eligible": True, "moyenne": 14.2, "details": []}):
			self.assertEqual(diplomation.rechercher_candidats(jury), 1)
		jury.save(ignore_permissions=True)
		self.assertEqual(jury.candidats[0].mention, "Bien")
		diplomation.proclamer(jury)
		return jury

	def test_diplomation_puis_attestation_signee(self):
		with self.assertRaises(frappe.ValidationError):  # pas encore diplômé
			self.en_tant_que(self.user, actes.obtenir, "Attestation de réussite")
		jury = self._diplomer()
		self.assertTrue(frappe.db.exists("Diplome Etudiant", {"student": self.student.name, "statut": "Délivré"}))

		demande = self.en_tant_que(self.user, actes.obtenir, "Attestation de réussite", "Concours d'entrée")
		self.assertEqual(demande["statut"], "Demandé")
		with self.assertRaises(frappe.ValidationError):  # pas avant délivrance
			self.en_tant_que(self.user, actes.telecharger, demande["name"])
		self.en_tant_que(self.responsable.name, actes.delivrer, demande["name"])
		self.assertEqual(frappe.db.get_value("Acte Academique", demande["name"], "statut"), "Disponible")
		ctx = moteur.contexte(self.student.name, frappe.get_doc("Modele Acte", "Attestation de réussite"))
		self.assertEqual(ctx["diplome"].mention, "Bien")

		diplomation.annuler(frappe.get_doc("Jury Diplomation", jury.name))
		self.assertFalse(frappe.db.exists("Diplome Etudiant", {"student": self.student.name, "statut": "Délivré"}))

	def test_diplome_signature_manuscrite_a_retirer(self):
		self._diplomer()
		demande = self.en_tant_que(self.user, actes.obtenir, "Diplôme")
		self.en_tant_que(self.responsable.name, actes.delivrer, demande["name"])
		self.assertEqual(frappe.db.get_value("Acte Academique", demande["name"], "statut"), "Prêt à retirer")
		self.en_tant_que(self.responsable.name, actes.marquer_retire, demande["name"])
		self.assertEqual(frappe.db.get_value("Acte Academique", demande["name"], "statut"), "Retiré")

	def test_jury_refuse_un_diplome_non_motive(self):
		self.inscrire()
		jury = frappe.get_doc({"doctype": "Jury Diplomation", "academic_year": self.annee.name, "filiere": self.fos.name,
							   "cycle": "Licence", "date_jury": "2027-07-10"}).insert(ignore_permissions=True)
		with patch.object(diplomation, "bilan_cycle",
						  return_value={"total": 180, "valides": 150, "eligible": False, "moyenne": 9, "details": ["L2"]}):
			diplomation.rechercher_candidats(jury)
		jury.candidats[0].decision = "Diplômé"
		jury.candidats[0].motif = ""
		with self.assertRaises(frappe.ValidationError):
			diplomation.proclamer(jury)

	# ------------------------------------------------------------------ requêtes
	def test_requete_soumise_puis_repondue(self):
		agent = make_user_with_role("Agent de scolarité")
		res = self.en_tant_que(self.user, requetes.soumettre, "Correction d'état civil", "Erreur de prénom",
							   "Mon prénom est mal orthographié.")
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": agent.name, "document_name": res["name"]}))
		with self.assertRaises(frappe.PermissionError):
			self.en_tant_que(self.user, requetes.repondre, res["name"], "ok")
		self.en_tant_que(agent.name, requetes.repondre, res["name"], "Corrigé dans votre dossier.")
		self.assertEqual(frappe.db.get_value("Requete Etudiant", res["name"], "statut"), "Répondue")
		# L'étudiant est notifié vers son espace (il n'ouvre pas le formulaire du personnel).
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": self.user, "link": "/app/mon-espace-etudiant"}))

	def test_reclamation_exige_une_matiere(self):
		with self.assertRaises(frappe.ValidationError):
			self.en_tant_que(self.user, requetes.soumettre, "Réclamation de note", "Note", "Erreur")

	# ------------------------------------------------------------------ babillard + saisie scolarité
	def test_babillard_classe_notes_publiees_seulement(self):
		self.inscrire()
		tu = make_teaching_unit(make_course(), self.annee, self.fos, self.l3)
		tu2 = make_teaching_unit(make_course(), self.annee, self.fos, self.l3)
		sess = make_session_examen(self.annee, self.cal, filiere=self.fos, niveau=self.l3)
		frappe.db.set_value("Session Examen", sess.name, "statut", "Publiée")
		make_session_examen_note(sess, self.student, tu, note_cc=12, note_examen=14, statut="Publié")
		make_session_examen_note(sess, self.student, tu2, note_cc=5, note_examen=5, statut="Saisi")
		options = babillard.options_babillard(self.annee.name)
		self.assertIn({"filiere": self.fos.name, "filiere_label": babillard._get_filiere_name(self.fos.name),
					   "niveau": "Licence 3"}, options["classes"])
		res = babillard.resultats_classe(self.annee.name, self.fos.name, "Licence 3")
		self.assertEqual([c["teaching_unit"] for c in res["colonnes"]], [tu.name])
		self.assertEqual(res["lignes"][0]["matricule"], self.student.matricule)

	def test_scolarite_saisit_les_notes(self):
		from udshed.api.saisie_notes import _verifier_acces_enseignant

		tu = make_teaching_unit(make_course(), self.annee, self.fos, self.l3)
		agent = make_user_with_role("Agent de scolarité")
		self.en_tant_que(agent.name, _verifier_acces_enseignant, tu.name)  # ne lève pas
