# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Parcours complet d'un étudiant, de la candidature au diplôme et aux actes.

  candidature (campagne ouverte) → admission sur dossier → inscription
  (matricule, UE de L1) → notes L1 publiées → progression → réinscription L2
  → notes L2 → réinscription L3 → notes L3 → jury de diplomation → diplôme →
  certificat de scolarité (libre-service), attestation de réussite (demandée,
  délivrée, vérifiable par QR).
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate, today

from udshed.api import actes, inscription
from udshed.api import reregistration as rr
from udshed.api.progression import STATUT_ADMIS
from udshed.api.saisie_notes import publier_session
from udshed.udshed._fixture_factory import (
	make_agent_scolarite,
	make_academic_year,
	make_calendar_planing,
	make_course,
	make_faculty,
	make_field_of_study,
	make_level,
	make_planning_item,
	make_session_examen,
	make_session_examen_note,
	make_teacher,
	make_teaching_unit,
	make_user_with_role,
	seed_formule,
	seed_grille_grades,
)
from udshed.utils import actes as moteur
from udshed.utils import diplomation

TYPE_NORMALE = "Examen de session normal"
NIVEAUX = ("Licence 1", "Licence 2", "Licence 3")


class TestParcoursComplet(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._commit = frappe.db.commit
		frappe.db.commit = lambda *a, **k: None
		cls._sans_limite = patch("frappe.core.doctype.user.user.throttle_user_creation")
		cls._sans_limite.start()
		cls._mails = patch("frappe.sendmail")
		cls._mails.start()
		cls._jobs = patch("frappe.enqueue")
		cls._jobs.start()
		seed_grille_grades()
		seed_formule("Licence", ["Controle Continu(CC)", "Examen"], [40, 60])

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls._jobs.stop()
		cls._mails.stop()
		cls._sans_limite.stop()
		frappe.db.commit = cls._commit
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	# ------------------------------------------------------------------ outils
	def _grilles(self):
		"""Deux UE (une par semestre) par niveau et par année."""
		self.tus = {}
		jour = 1
		for i, annee in enumerate(self.annees):
			niveau = self.levels[NIVEAUX[i]]
			for semestre in ("Semestre 1", "Semestre 2"):
				tu = make_teaching_unit(make_course(semestre=semestre), annee, self.fos, niveau, credits=6)
				frappe.db.set_value("Teaching Unit", tu.name, "semestre", semestre)
				make_planning_item(tu, annee, self.cal, type_dexamen=TYPE_NORMALE,
								   date=f"{annee.name[:4]}-12-{jour:02d}")
				jour += 1
				self.tus[(annee.name, semestre)] = tu

	def _session_reinscription(self, annee):
		frappe.db.set_value("Session Reinscription", {"statut": "Ouverte"}, "statut", "Fermée")
		return frappe.get_doc({"doctype": "Session Reinscription", "academic_year": annee.name, "statut": "Ouverte",
							   "date_ouverture": add_days(nowdate(), -5), "date_cloture": add_days(nowdate(), 30)}
							  ).insert(ignore_permissions=True)

	def _noter_et_publier(self, student, annee, note=15):
		niveau = self.levels[NIVEAUX[self.annees.index(annee)]]
		for semestre in ("Semestre 1", "Semestre 2"):
			sess = make_session_examen(annee, self.cal, filiere=self.fos, niveau=niveau, semestre=semestre)
			make_session_examen_note(sess, frappe.get_doc("Student", student), self.tus[(annee.name, semestre)],
									 note_cc=note, note_examen=note, statut="Validé")
			publier_session(sess.name)

	def _progression(self, student, annee):
		return frappe.get_doc("Progression Academique", {"student": student, "annee_source": annee.name})

	def _reinscrire(self, student, annee):
		session = self._session_reinscription(annee)
		cours = [{"teaching_unit": self.tus[(annee.name, s)].name, "inscrire": 1} for s in ("Semestre 1", "Semestre 2")]
		frappe.set_user(frappe.db.get_value("Student", student, "utilisateur"))
		try:
			res = rr.submit_reinscription(student, session.name, "Les deux", cours=cours)
		finally:
			frappe.set_user("Administrator")
		return frappe.get_doc("Academic Reregistration", res["name"])

	# ------------------------------------------------------------------ parcours
	def test_parcours_de_la_candidature_au_diplome(self):
		self.annees = [make_academic_year("2030", "2031"), make_academic_year("2031", "2032"),
					   make_academic_year("2032", "2033")]
		self.cal = make_calendar_planing()
		self.fos = make_field_of_study(make_faculty(), self.cal, make_teacher())
		self.levels = {lab: make_level(self.fos, lab, i + 1) for i, lab in enumerate(NIVEAUX)}
		self._grilles()
		frappe.db.set_single_value("Udshed Setting", "current_year", self.annees[0].name)

		# 1. Candidature pendant la campagne de la rentrée 2030-2031.
		for nom in frappe.get_all("Session Inscription", filters={"status": "Open"}, pluck="name"):
			frappe.db.set_value("Session Inscription", nom, "status", "Closed")
		campagne = frappe.get_doc({"doctype": "Session Inscription", "academic_year": self.annees[0].name,
								   "status": "Open", "opening_date": add_days(today(), -5),
								   "closing_date": add_days(today(), 20), "centres_examen": "Centre A"}
								  ).insert(ignore_permissions=True)
		cand = frappe.get_doc({
			"doctype": "Session Inscription Candidate", "first_name": "MBARGA", "last_name": "ALICE",
			"email": frappe.generate_hash(length=8) + "@example.com", "phone": "+237699111222",
			"birth_place": "Yaoundé", "birthdate": "2008-01-15", "sexe": "Femme", "examination_centre": "Centre A",
			"birth_certificate": "/files/a.pdf", "access_diploma_copy": "/files/b.pdf", "id_photo": "/files/c.png",
			"remittance_receipt": "/files/d.pdf",
			"choix_de_formation": [{"choix": "1er choix", "filiere": self.fos.name, "niveau": self.levels["Licence 1"].name}],
		})
		frappe.set_user("Guest")
		try:
			cand.insert(ignore_permissions=True)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(cand.session_inscription, campagne.name)
		self.assertEqual(cand.mode_admission, "Dossier")

		# 2. Admission sur dossier (agent de scolarité).
		frappe.set_user(make_agent_scolarite(cand.filiere).name)
		try:
			from udshed.udshed.doctype.session_inscription_candidate.session_inscription_candidate import (
				update_candidate_status,
			)

			update_candidate_status(cand.name, "Accepté")
		finally:
			frappe.set_user("Administrator")
		self.assertTrue(frappe.db.get_value("Session Inscription Candidate", cand.name, "finaliser_avant"))

		# 3. Inscription : matricule, compte, UE de L1 de la rentrée.
		dossier = frappe._dict(frappe.get_doc("Session Inscription Candidate", cand.name).as_dict())
		res = inscription._finaliser_inscription_complete(dossier, {})
		student = res["student_name"]
		self.assertEqual(res["annee_academique"], self.annees[0].name)
		self.assertEqual(res["enrolled_count"], 2)
		user = frappe.db.get_value("Student", student, "utilisateur")
		self.assertEqual(frappe.db.get_value("User", user, "username"), res["matricule"])

		# 4. L1 : notes publiées → admis en L2 → réinscription.
		self._noter_et_publier(student, self.annees[0])
		prog = self._progression(student, self.annees[0])
		self.assertEqual((prog.statut, prog.niveau_cible), (STATUT_ADMIS, "Licence 2"))
		frappe.db.set_single_value("Udshed Setting", "current_year", self.annees[1].name)
		rer = self._reinscrire(student, self.annees[1])
		self.assertEqual(rer.niveau, "Licence 2")

		# 5. L2 → L3.
		self._noter_et_publier(student, self.annees[1])
		prog = self._progression(student, self.annees[1])
		self.assertEqual((prog.statut, prog.niveau_cible), (STATUT_ADMIS, "Licence 3"))
		frappe.db.set_single_value("Udshed Setting", "current_year", self.annees[2].name)
		rer = self._reinscrire(student, self.annees[2])
		self.assertEqual(rer.niveau, "Licence 3")

		# 6. Certificat de scolarité en libre-service (inscrit en L3).
		moteur.creer_modeles_defaut()
		frappe.set_user(user)
		try:
			cert = actes.obtenir("Certificat de scolarité")
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(cert["statut"], "Disponible")

		# 7. L3 : notes publiées → jury de diplomation → diplôme.
		self._noter_et_publier(student, self.annees[2], note=16)
		jury = frappe.get_doc({"doctype": "Jury Diplomation", "academic_year": self.annees[2].name,
							   "filiere": self.fos.name, "cycle": "Licence", "date_jury": today()}).insert(ignore_permissions=True)
		diplomation.rechercher_candidats(jury)
		candidat = jury.candidats[0]
		self.assertTrue(candidat.eligible, candidat.motif)
		self.assertEqual((candidat.credits_valides, candidat.credits_total), (36, 36))
		self.assertEqual(candidat.decision, "Diplômé")
		jury.save(ignore_permissions=True)
		diplomation.proclamer(jury)
		self.assertTrue(frappe.db.exists("Diplome Etudiant", {"student": student, "statut": "Délivré"}))

		# 8. Attestation de réussite : demande, délivrance, vérification.
		frappe.set_user(user)
		try:
			demande = actes.obtenir("Attestation de réussite")
		finally:
			frappe.set_user("Administrator")
		frappe.set_user(make_user_with_role("Responsable Diplomation").name)
		try:
			actes.delivrer(demande["name"])
		finally:
			frappe.set_user("Administrator")
		code = frappe.db.get_value("Acte Academique", demande["name"], "code_verification")
		verification = actes.verifier(code)
		self.assertTrue(verification["valide"])
		self.assertEqual(verification["type"], "Attestation de réussite")
		self.assertEqual(verification["matricule"], res["matricule"])
