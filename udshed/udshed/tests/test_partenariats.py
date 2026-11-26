# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Partenariats enseignants : vacations, progression, documents (PDF / Word), conventions."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from udshed.api import actes as api_actes
from udshed.api import documents_enseignant as api
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
from udshed.utils import actes as moteur
from udshed.utils import vacations


class TestPartenariats(IntegrationTestCase):
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
		jour = getdate(today())
		debut = jour.year - 1 if jour.month < 9 else jour.year
		self.annee = make_academic_year(str(debut), str(debut + 1))
		cal = make_calendar_planing()
		cal.append("heure_planification", {"libelle": "Matin", "heure_de_debut": "08:00:00", "heure_de_fin": "12:00:00"})
		cal.save(ignore_permissions=True)
		self.periode = cal.heure_planification[-1].name
		self.fos = make_field_of_study(make_faculty(), cal, make_teacher())
		self.niveau = make_level(self.fos)

		titre = frappe.get_meta("Financial Payment Grade Config").get_field("grade").options.split("\n")[0]
		reglages = frappe.get_single("Udshed Setting")
		reglages.set("configuration_des_paiements_par_grade", [{"grade": titre, "prix_heure": 5000}])
		reglages.base_paiement_vacations = vacations.BASE_FAIT
		reglages.taux_retenue_vacations = 10
		reglages.coef_vacation_cm = reglages.coef_vacation_td = reglages.coef_vacation_tp = 1
		reglages.save(ignore_permissions=True)
		frappe.clear_document_cache("Udshed Setting", "Udshed Setting")

		self.vacataire = make_teacher()
		frappe.db.set_value("Teacher", self.vacataire.name, {"status": "Vacataire", "titre": titre})
		self.permanent = make_teacher()
		frappe.db.set_value("Teacher", self.permanent.name, {"status": "Permanent", "titre": titre})
		self.cours = make_teaching_unit(make_course(), self.annee, self.fos, self.niveau)
		frappe.db.set_value("Teaching Unit", self.cours.name, {"nombre_dheure_cm": 20, "nombre_dheure_td": 10})
		self.cours.reload()
		self.cours.append("table_enseignant", {"enseignant": self.vacataire.name, "type_de_cours": "Cours Magistral (CM)"})
		self.cours.append("table_enseignant", {"enseignant": self.permanent.name, "type_de_cours": "Travaux Dirigés (TD)"})
		self.cours.save(ignore_permissions=True)
		# Deux CM faits (2 × 4 h), un CM non pointé, un TD fait.
		passe = add_days(today(), -3)
		for i, (type_, statut) in enumerate((("Cours Magistral (CM)", "Fait"), ("Cours Magistral (CM)", "Fait"),
											  ("Cours Magistral (CM)", "Non fait"), ("Traveaux Dirigés (TD)", "Fait"))):
			frappe.get_doc({"doctype": "Planning Item", "cours": self.cours.name, "type": type_, "status": statut,
							"date": f"{add_days(passe, -7 * i)} 08:00:00", "period": self.periode,
							"academic_year": self.annee.name, "mode": "En présentiel"}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		self._commits.__exit__(None, None, None)
		frappe.db.rollback()
		frappe.clear_document_cache("Udshed Setting", "Udshed Setting")

	def compte(self, teacher):
		user = make_user_with_role("Teacher")
		frappe.db.set_value("Teacher", teacher.name, "email", user.name)
		return user.name

	# ------------------------------------------------------------------ calculs
	def test_vacations_heures_faites_fois_tarif(self):
		f = vacations.fiche(self.vacataire.name, self.annee.name)
		self.assertTrue(f.vacataire)
		self.assertEqual(f.heures_prevues, 20)
		self.assertEqual(f.heures_faites, 8)  # le CM non pointé n'est pas payé
		self.assertEqual(f.brut, 8 * 5000)
		self.assertEqual(f.retenue, 4000)
		self.assertEqual(f.net, 36000)

	def test_permanent_a_des_heures_mais_pas_de_montant(self):
		f = vacations.fiche(self.permanent.name, self.annee.name)
		self.assertFalse(f.vacataire)
		self.assertEqual(f.heures_faites, 4)
		self.assertEqual(f.net, 0)

	def test_coefficient_et_seances_passees(self):
		frappe.db.set_single_value("Udshed Setting", {"coef_vacation_cm": 1.5,
													  "base_paiement_vacations": vacations.BASE_PASSEES})
		frappe.clear_document_cache("Udshed Setting", "Udshed Setting")
		f = vacations.fiche(self.vacataire.name, self.annee.name)
		self.assertEqual(f.heures_faites, 12)  # séances passées, pointées ou non
		self.assertEqual(f.brut, 12 * 5000 * 1.5)

	# ------------------------------------------------------------------ enseignant
	def test_enseignant_telecharge_ses_documents(self):
		frappe.set_user(self.compte(self.vacataire))
		res = api.mes_documents(self.annee.name)
		possibles = {d["type_acte"] for d in res["documents"] if d["possible"]}
		self.assertIn("Fiche de règlement des vacations", possibles)
		self.assertIn("Fiche de progression des cours", possibles)
		api.telecharger("Fiche de règlement des vacations", "pdf", academic_year=self.annee.name)
		self.assertTrue(frappe.response["filecontent"].startswith(b"%PDF"))
		api.telecharger("Fiche de progression des cours", "docx", academic_year=self.annee.name)
		self.assertTrue(frappe.response["filecontent"].startswith(b"PK"))
		doc = frappe.get_last_doc("Document Enseignant", filters={"teacher": self.vacataire.name})
		self.assertTrue(doc.code_verification)
		frappe.set_user("Administrator")
		res = api_actes.verifier(doc.code_verification)
		self.assertTrue(res["valide"])
		self.assertEqual(res["titulaire"], "enseignant")

	def test_enseignant_ne_voit_pas_les_documents_des_autres(self):
		frappe.set_user(self.compte(self.permanent))
		with self.assertRaises(frappe.PermissionError):
			api.telecharger("Fiche de progression des cours", teacher=self.vacataire.name, academic_year=self.annee.name)
		with self.assertRaises(frappe.PermissionError):  # permanent : pas de règlement des vacations
			api.telecharger("Fiche de règlement des vacations", academic_year=self.annee.name)
		with self.assertRaises(frappe.PermissionError):  # attestation : délivrée par le service
			api.telecharger("Attestation d'enseignement", academic_year=self.annee.name)

	# ------------------------------------------------------------------ service des partenariats
	def test_service_tableau_conventions_et_documents(self):
		frappe.set_user(make_user_with_role("Responsable des partenariats").name)
		lignes = {l["enseignant"]: l for l in api.tableau(self.annee.name)["lignes"]}
		self.assertEqual(lignes[self.vacataire.name]["net"], 36000)
		crees = api.creer_conventions(self.annee.name)["crees"]
		conv = frappe.get_doc("Convention Vacation", {"teacher": self.vacataire.name, "academic_year": self.annee.name})
		self.assertIn(conv.name, crees)
		self.assertEqual(conv.volume_horaire, 20)
		self.assertEqual(conv.montant_previsionnel, 20 * 5000)
		self.assertNotIn(self.permanent.name, {frappe.db.get_value("Convention Vacation", c, "teacher") for c in crees})
		api.telecharger("Convention de vacation", "pdf", teacher=self.vacataire.name, academic_year=self.annee.name)
		self.assertTrue(frappe.response["filecontent"].startswith(b"%PDF"))
		api.telecharger("Attestation d'enseignement", "docx", teacher=self.permanent.name, academic_year=self.annee.name)
		self.assertTrue(frappe.response["filecontent"].startswith(b"PK"))
		with self.assertRaises(frappe.ValidationError):  # une seule convention par enseignant et par année
			frappe.get_doc({"doctype": "Convention Vacation", "teacher": self.vacataire.name,
							"academic_year": self.annee.name}).insert()

	def test_modele_word_vierge_garde_les_variables(self):
		api.modele_vierge(moteur.modele_par_defaut("Fiche de règlement des vacations"))
		import io
		import zipfile

		xml = zipfile.ZipFile(io.BytesIO(frappe.response["filecontent"])).read("word/document.xml").decode()
		self.assertIn("vacations.net", xml)
		self.assertIn("for l in vacations.lignes", xml)

	def test_un_seul_modele_par_defaut_par_type(self):
		type_acte = "Attestation d'enseignement"
		premier = moteur.modele_par_defaut(type_acte)
		autre = frappe.copy_doc(frappe.get_doc("Modele Acte", premier))
		autre.titre = "Attestation d'enseignement (variante)"
		autre.par_defaut = 1
		autre.insert(ignore_permissions=True)
		self.assertEqual(moteur.modele_par_defaut(type_acte), autre.name)
		self.assertFalse(frappe.db.get_value("Modele Acte", premier, "par_defaut"))
		self.assertEqual(autre.sujet, moteur.SUJET_ENSEIGNANT)

	def test_espace_etudiant_sans_documents_enseignants(self):
		from udshed.udshed._fixture_factory import make_student

		student = make_student(self.fos, self.niveau)
		user = make_user_with_role("Student")
		frappe.db.set_value("Student", student.name, "utilisateur", user.name)
		frappe.set_user(user.name)
		types = {m["type_acte"] for m in api_actes.mes_documents()}
		self.assertFalse(types & set(moteur.TYPES_ENSEIGNANT))
