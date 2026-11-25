# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Correction d'une note d'une année close.

  1. verrou : modification directe refusée sur une année close, permise sur
	 l'année en cours ;
  2. l'enseignant DEMANDE (note inchangée), la coordination APPROUVE (note
	 corrigée, historique, commentaire) ; une demande de la coordination
	 s'applique aussitôt ; un refus exige un motif ;
  3. réinscription déjà faite : dettes mises à jour si la décision ne change
	 pas, alerte à la scolarité sinon ;
  4. l'étudiant est prévenu.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from udshed.udshed._fixture_factory import (
	make_academic_year,
	make_calendar_planing,
	make_course,
	make_faculty,
	make_field_of_study,
	make_level,
	make_progression,
	make_session_examen,
	make_session_examen_note,
	make_student,
	make_teacher,
	make_teaching_unit,
	make_user_with_role,
	seed_grade_formula,
	suppress_commits,
)
from udshed.utils import correction_note


class TestCorrectionNote(IntegrationTestCase):
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
		self._mails = patch("frappe.sendmail")
		self.sendmail = self._mails.start()
		seed_grade_formula("Licence")
		self.y1 = make_academic_year("2025", "2026")
		self.y2 = make_academic_year("2026", "2027")
		frappe.db.set_single_value("Udshed Setting", "current_year", self.y2.name)  # 2025-2026 est close
		self.cal = make_calendar_planing()
		self.fos = make_field_of_study(make_faculty(), self.cal, make_teacher())
		self.l1 = make_level(self.fos, "Licence 1", 1)
		self.tu = make_teaching_unit(make_course(), self.y1, self.fos, self.l1)
		self.prof = make_teacher()
		self.prof_user = make_user_with_role("Teacher")
		frappe.db.set_value("Teacher", self.prof.name, "email", self.prof_user.name)
		self.tu.append("table_enseignant", {"enseignant": self.prof.name, "type_de_cours": "Cours Magistral (CM)"})
		self.tu.save(ignore_permissions=True)
		self.student = make_student(self.fos, self.l1)
		sess = make_session_examen(self.y1, self.cal, filiere=self.fos, niveau=self.l1)
		self.note = make_session_examen_note(sess, self.student, self.tu, note_cc=8, note_examen=8)

	def tearDown(self):
		self._mails.stop()
		frappe.set_user("Administrator")
		frappe.db.rollback()
		self._commits.__exit__(None, None, None)

	def demander(self, user, nouvelle=15, motif_type="Réclamation de l'étudiant"):
		frappe.set_user(user)
		try:
			return correction_note.demander_correction(
				self.note.name, [{"champ": "note_examen", "nouvelle_valeur": nouvelle}], motif_type, "Copie mal additionnée")
		finally:
			frappe.set_user("Administrator")

	# ------------------------------------------------------------------ verrou
	def test_modification_directe_refusee_sur_annee_close(self):
		note = frappe.get_doc("Session Examen Note", self.note.name)
		note.note_examen = 15
		with self.assertRaisesRegex(frappe.ValidationError, "close"):
			note.save(ignore_permissions=True)

	def test_annee_en_cours_reste_modifiable(self):
		frappe.db.set_single_value("Udshed Setting", "current_year", self.y1.name)
		note = frappe.get_doc("Session Examen Note", self.note.name)
		note.note_examen = 15
		note.save(ignore_permissions=True)

	# ------------------------------------------------------------------ circuit
	def test_demande_enseignant_puis_approbation(self):
		avant = self.note.note_finale
		res = self.demander(self.prof_user.name)
		self.assertEqual(res["statut"], "En attente")
		self.assertEqual(frappe.db.get_value("Session Examen Note", self.note.name, "note_examen"), 8)

		cor = frappe.get_doc("Correction Note", res["name"])
		self.assertEqual(cor.demandee_par, self.prof_user.name)
		self.assertEqual(cor.lignes[0].ancienne_valeur, 8)
		self.assertEqual(cor.note_finale_avant, frappe.utils.flt(avant))

		with patch.object(correction_note, "recalculer_apres_correction", return_value=["ok"]):
			cor.approuver()
		cor.reload()
		self.assertEqual(cor.statut, "Appliquée")
		self.assertEqual(frappe.db.get_value("Session Examen Note", self.note.name, "note_examen"), 15)
		self.assertEqual(cor.note_finale_apres, frappe.utils.flt(
			frappe.db.get_value("Session Examen Note", self.note.name, "note_finale")))
		# Historique : versions activées sur la note (écrites en différé par Frappe)
		# et commentaire de correction posé sur la note.
		self.assertTrue(frappe.get_meta("Session Examen Note").track_changes)
		self.assertTrue(frappe.db.exists("Comment", {"reference_doctype": "Session Examen Note",
													 "reference_name": self.note.name,
													 "content": ["like", f"%{cor.name}%"]}))
		self.assertTrue(self.sendmail.called)

	def test_enseignant_ne_peut_pas_approuver(self):
		res = self.demander(self.prof_user.name)
		cor = frappe.get_doc("Correction Note", res["name"])
		frappe.set_user(self.prof_user.name)
		with self.assertRaises(frappe.PermissionError):
			cor.approuver()

	def test_demande_de_la_coordination_appliquee_aussitot(self):
		coord = make_user_with_role("Coordonateur")
		with patch.object(correction_note, "recalculer_apres_correction", return_value=[]):
			res = self.demander(coord.name, motif_type="Erreur de saisie")
		self.assertEqual(res["statut"], "Appliquée")
		self.assertEqual(frappe.db.get_value("Session Examen Note", self.note.name, "note_examen"), 15)

	def test_refus_motive(self):
		res = self.demander(self.prof_user.name)
		cor = frappe.get_doc("Correction Note", res["name"])
		with self.assertRaises(frappe.ValidationError):
			cor.refuser("")
		cor.refuser("Copie vérifiée : note exacte")
		self.assertEqual(frappe.db.get_value("Correction Note", cor.name, "statut"), "Refusée")
		self.assertEqual(frappe.db.get_value("Session Examen Note", self.note.name, "note_examen"), 8)

	def test_motif_et_valeurs_controles(self):
		with self.assertRaises(frappe.ValidationError):
			self.demander("Administrator", nouvelle=25)
		with self.assertRaises(frappe.ValidationError):
			self.demander("Administrator", nouvelle=8)  # identique

	# ------------------------------------------------------------------ réinscription déjà faite
	def _reinscription_utilisee(self, dettes):
		prog = make_progression(self.student, self.y1.name, self.fos.name, "Licence 1", statut="Redoublement")
		reg = frappe.get_doc({"doctype": "Academic Reregistration", "student": self.student.name,
							  "academic_year": self.y2.name, "filiere": self.fos.name, "niveau": "Licence 1",
							  "semestre": "Les deux", "statut": "Validée",
							  "cours_inscrits": [{"teaching_unit": tu, "inscrire": 1, "source": "dette",
												  "statut": "Inscrit"} for tu in dettes]})
		reg.flags.ignore_validate = True
		reg.flags.ignore_mandatory = True
		reg.insert(ignore_permissions=True)
		frappe.db.set_value("Progression Academique", prog.name, {
			"reinscription": reg.name, "filiere_source": self.fos.name, "niveau_source": "Licence 1"})
		return prog, reg

	def test_dettes_mises_a_jour_si_decision_inchangee(self):
		ancienne = make_teaching_unit(make_course(), self.y2, self.fos, self.l1)
		_prog, reg = self._reinscription_utilisee([ancienne.name])
		with patch("udshed.api.progression.evaluer_progression",
				   return_value={"statut": "Redoublement", "niveau_cible": "Licence 1"}), \
			patch("udshed.api.reregistration._dettes_reportees", return_value=[]):
			bilan = correction_note.recalculer_apres_correction(self.note)
		reg.reload()
		self.assertEqual([c for c in reg.cours_inscrits if c.source == "dette"], [])
		self.assertTrue(any("mise à jour" in b for b in bilan))

	def test_alerte_si_la_decision_de_passage_change(self):
		agent = make_user_with_role("Agent de scolarité")
		_prog, reg = self._reinscription_utilisee([])
		with patch("udshed.api.progression.evaluer_progression",
				   return_value={"statut": "Admis au niveau supérieur", "niveau_cible": "Licence 2", "motif": "60 %"}):
			bilan = correction_note.recalculer_apres_correction(self.note)
		self.assertTrue(any("change la décision" in b for b in bilan))
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": agent.name,
															  "document_name": reg.name}))
		self.assertEqual(frappe.db.get_value("Academic Reregistration", reg.name, "niveau"), "Licence 1")
