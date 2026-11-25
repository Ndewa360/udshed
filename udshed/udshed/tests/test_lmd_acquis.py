# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Règles LMD : compensation par unité, dettes, équivalences, redoublant, jury.

Unité U1 (L1, 2025-2026) = matières M1 (3 cr) + M2 (3 cr) ; matière M3 (4 cr)
hors unité. Les notes sont injectées (remplacement de `_meilleure_note`) pour
tester les règles de validation, pas la saisie.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api import reregistration, resultat_ue, saisie_notes
from udshed.udshed._fixture_factory import (
	make_academic_year,
	make_course,
	make_faculty,
	make_field_of_study,
	make_level,
	make_student,
	make_teacher,
	make_teaching_unit,
	make_teaching_unit_value,
	suppress_commits,
)
from udshed.utils import acquis, deliberation


class TestLMDAcquis(IntegrationTestCase):
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
		self._commits = suppress_commits()
		self._commits.__enter__()
		self.y1 = make_academic_year("2025", "2026")
		self.y2 = make_academic_year("2026", "2027")
		self.fos = make_field_of_study(make_faculty(), None, make_teacher())
		self.l1 = make_level(self.fos, "Licence 1", 1)
		self.l2 = make_level(self.fos, "Licence 2", 2)
		self.c1, self.c2, self.c3 = make_course(), make_course(), make_course()
		self.u1 = make_teaching_unit_value(self.y1)
		self.m1 = make_teaching_unit(self.c1, self.y1, self.fos, self.l1, credits=3, unite_de_valeur=self.u1)
		self.m2 = make_teaching_unit(self.c2, self.y1, self.fos, self.l1, credits=3, unite_de_valeur=self.u1)
		self.m3 = make_teaching_unit(self.c3, self.y1, self.fos, self.l1, credits=4)
		self.etudiant = make_student(self.fos, self.l1).name
		self.notes = {}
		self._notes = patch.object(resultat_ue, "_meilleure_note",
								   side_effect=lambda student, tu, *a, **k: self.notes.get(tu))
		self._notes.start()

	def tearDown(self):
		self._notes.stop()
		deliberation.vider_cache()
		frappe.db.rollback()
		self._commits.__exit__(None, None, None)

	# ------------------------------------------------------------------ outils
	def noter(self, **notes_20):
		for nom, note in notes_20.items():
			tu = getattr(self, nom).name
			self.notes[tu] = {"note_pct": note * 5, "note_finale": note, "est_rattrapage": False}

	def resultat_m3(self, note):
		frappe.get_doc({
			"doctype": "Resultat Academique", "student": self.etudiant, "teaching_unit": self.m3.name,
			"academic_year": self.y1.name, "semestre": "Semestre 1", "note_finale": note, "note_pct": note * 5,
			"statut": "Validé" if note >= 10 else "Non Validé",
		}).insert(ignore_permissions=True, ignore_mandatory=True)

	def bilan(self):
		return acquis.bilan_niveau(self.etudiant, self.fos.name, self.l1.name, self.y1.name)

	def delib(self, **regles):
		doc = frappe.get_doc({"doctype": "Deliberation Jury", "academic_year": self.y1.name,
							  "filiere": self.fos.name, "niveau": self.l1.name, **regles})
		doc.insert(ignore_permissions=True)
		doc.db_set("statut", "Appliquée")
		deliberation.vider_cache()
		return doc

	# ------------------------------------------------------------------ compensation
	def test_compensation_dans_l_unite(self):
		self.noter(m1=8, m2=13)  # moyenne 10,5 : M1 compensée
		self.resultat_m3(7)
		b = self.bilan()
		self.assertEqual((b["valides"], b["total"]), (6, 10))
		self.assertEqual([d["teaching_unit"] for d in b["dettes"]], [self.m3.name])

	def test_unite_non_validee_reprise_entierement(self):
		self.noter(m1=6, m2=11)  # moyenne 8,5 : M2 (11) n'est PAS capitalisée
		self.resultat_m3(12)
		b = self.bilan()
		self.assertEqual(b["valides"], 4)
		self.assertEqual({d["teaching_unit"] for d in b["dettes"]}, {self.m1.name, self.m2.name})

	# ------------------------------------------------------------------ jury
	def test_points_de_jury(self):
		self.noter(m1=8, m2=11)  # 9,5/20
		self.resultat_m3(12)
		self.assertEqual(self.bilan()["valides"], 4)
		self.delib(points_jury_max=0.5)
		r = resultat_ue.calculer_ue_etudiant(self.etudiant, self.u1.name, self.y1.name, "Semestre 1",
											 self.fos.name, self.l1.name)
		self.assertTrue(r["valide_par_jury"])
		self.assertEqual(r["points_jury"], 0.5)
		self.assertEqual(r["note_ue_20"], 9.5)  # la note n'est jamais modifiée
		self.assertEqual(self.bilan()["valides"], 10)

	def test_points_de_jury_insuffisants(self):
		self.noter(m1=6, m2=11)  # 8,5/20 : 1,5 point manquant
		self.delib(points_jury_max=1)
		self.assertNotIn(self.m1.name, self.bilan()["tu_valides"])

	def test_seuil_abaisse(self):
		self.noter(m1=8, m2=10)  # 9/20
		self.delib(seuil_abaisse=9)
		self.assertIn(self.m1.name, self.bilan()["tu_valides"])

	def test_decision_individuelle(self):
		self.noter(m1=4, m2=5)
		self.delib(decisions=[{"student": self.etudiant, "type_decision": "Validation d'unité",
							   "unite": self.u1.name, "motif": "Raisons médicales justifiées"}])
		self.assertIn(self.m2.name, self.bilan()["tu_valides"])

	def test_passage_conditionnel_et_admission_individuelle(self):
		self.delib(pourcentage_credits_min=40, dette_max_credits=36)
		pct, dette, admission = deliberation.regle_de_passage(self.etudiant, self.fos.name, self.l1.name, self.y1.name)
		self.assertEqual((pct, dette, admission), (40, 36, None))

		self.noter(m1=2, m2=3)
		self.resultat_m3(4)
		frappe.db.set_value("Deliberation Jury", {"filiere": self.fos.name}, "statut", "Brouillon")
		self.delib(decisions=[{"student": self.etudiant, "type_decision": "Admission au niveau supérieur",
							   "motif": "Décision souveraine du jury"}])
		decision = reregistration._admission_decision(self.etudiant, self.fos.name, "Licence 1", "Licence 2", self.y1.name)
		self.assertTrue(decision["admissible"])
		self.assertIn("jury", decision["motif"])

	def test_simulation_sans_effet(self):
		self.noter(m1=8, m2=11)
		doc = frappe.get_doc({"doctype": "Deliberation Jury", "academic_year": self.y1.name,
							  "filiere": self.fos.name, "niveau": self.l1.name, "points_jury_max": 0.5})
		doc.insert(ignore_permissions=True)
		self.assertEqual(self.bilan()["valides"], 0)  # brouillon : aucun effet
		self.assertEqual(deliberation.deliberation_appliquee(self.y1.name, self.fos.name, self.l1.name), None)

	# ------------------------------------------------------------------ équivalences et dettes
	def test_equivalence_automatique_et_declaree(self):
		m3_y2 = make_teaching_unit(self.c3, self.y2, self.fos, self.l1, credits=4)
		self.assertEqual(acquis.equivalent_annee(self.m3.name, self.y2.name, self.fos.name, "Licence 1"), m3_y2.name)
		# Grille modifiée : M1 remplacée par une nouvelle matière (autre cours).
		nouvelle = make_teaching_unit(make_course(), self.y2, self.fos, self.l1, credits=3)
		self.assertIsNone(acquis.equivalent_annee(self.m1.name, self.y2.name, self.fos.name, "Licence 1"))
		frappe.get_doc({"doctype": "Equivalence UE", "filiere": self.fos.name, "ancienne_matiere": self.m1.name,
						"nouvelle_matiere": nouvelle.name}).insert(ignore_permissions=True)
		self.assertEqual(acquis.equivalent_annee(self.m1.name, self.y2.name, self.fos.name, "Licence 1"), nouvelle.name)

	def test_dette_reportee_et_notee_dans_la_classe_d_origine(self):
		self.noter(m1=14, m2=14)
		self.resultat_m3(6)
		m3_y2 = make_teaching_unit(self.c3, self.y2, self.fos, self.l1, credits=4)
		sans = []
		reportees = reregistration._dettes_reportees(self.etudiant, self.fos.name, "Licence 1", self.l1.name,
													 self.y1.name, self.y2.name, sans)
		self.assertEqual([d["teaching_unit"] for d in reportees], [m3_y2.name])
		self.assertEqual(sans, [])

		# L'étudiant (désormais en L2) porte M3 en dette : il est noté en L1.
		reg = frappe.get_doc({"doctype": "Academic Reregistration", "student": self.etudiant,
							  "academic_year": self.y2.name, "filiere": self.fos.name, "niveau": "Licence 2",
							  "semestre": "Les deux", "statut": "Validée",
							  "cours_inscrits": [{"teaching_unit": m3_y2.name, "inscrire": 1, "source": "dette",
												  "statut": "Inscrit", "credits": 4}]})
		reg.flags.ignore_validate = True
		reg.flags.ignore_mandatory = True
		reg.insert(ignore_permissions=True)
		etudiants = [e["student"] for e in saisie_notes._get_etudiants(self.y2.name, self.fos.name, "Licence 1", m3_y2.name)]
		self.assertIn(self.etudiant, etudiants)

	def test_cours_decoche_absent_de_la_saisie(self):
		m3_y2 = make_teaching_unit(self.c3, self.y2, self.fos, self.l1, credits=4)
		autre = make_teaching_unit(make_course(), self.y2, self.fos, self.l1, credits=3)
		reg = frappe.get_doc({"doctype": "Academic Reregistration", "student": self.etudiant,
							  "academic_year": self.y2.name, "filiere": self.fos.name, "niveau": "Licence 1",
							  "semestre": "Les deux", "statut": "Validée",
							  "cours_inscrits": [{"teaching_unit": m3_y2.name, "inscrire": 1, "statut": "Inscrit"},
												 {"teaching_unit": autre.name, "inscrire": 0, "statut": "Inscrit"}]})
		reg.flags.ignore_validate = True
		reg.flags.ignore_mandatory = True
		reg.insert(ignore_permissions=True)
		self.assertIn(self.etudiant, [e["student"] for e in saisie_notes._get_etudiants(
			self.y2.name, self.fos.name, "Licence 1", m3_y2.name)])
		self.assertNotIn(self.etudiant, [e["student"] for e in saisie_notes._get_etudiants(
			self.y2.name, self.fos.name, "Licence 1", autre.name)])

	def test_redoublant_garde_ses_unites_validees(self):
		self.noter(m1=12, m2=12)
		resultat_ue.calculer_resultat_ue(self.etudiant, self.u1.name, self.y1.name, "Semestre 1",
										 self.fos.name, self.l1.name)
		m1_y2 = make_teaching_unit(self.c1, self.y2, self.fos, self.l1, credits=3)
		m3_y2 = make_teaching_unit(self.c3, self.y2, self.fos, self.l1, credits=4)
		acquises = acquis.matieres_acquises(self.etudiant)
		self.assertTrue(acquis.est_acquise(m1_y2.name, acquises))   # unité validée : pas reprise
		self.assertFalse(acquis.est_acquise(m3_y2.name, acquises))  # non validée : reprise
