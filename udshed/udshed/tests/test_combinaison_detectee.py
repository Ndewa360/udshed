# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests de la détection automatique de la combinaison d'évaluations.

La formule de calcul n'est PLUS déterminée par avance (type d'UE) : elle est
détectée à partir des colonnes effectivement renseignées par l'enseignant
(CC, CCTP, EXAMTP, EXAM) puis cherchée dans la Grade Formula. Les poids
proviennent uniquement de la configuration.

Cas couverts :
  - CC + EXAM ;
  - CC + CCTP + EXAM ;
  - CC + EXAMTP + EXAM ;
  - CC + CCTP + EXAMTP + EXAM ;
  - la détection prime sur le type d'UE ;
  - une combinaison saisie sans formule configurée reste indéterminée ;
  - le parcours API complet (enregistrer_evaluations -> note calculée).
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api.saisie_notes import (
    calculer_apercu,
    enregistrer_evaluations,
)
from udshed.grade_calculation import combinaison_detectee
from udshed.udshed._fixture_factory import (
    make_academic_reregistration,
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
    seed_formule,
    seed_grille_grades,
)

CC = "Controle Continu(CC)"
CCTP = "Controle Continu Travaux Pratiques(CCTP)"
EXAMTP = "Examen Travaux Pratiques(EXAMTP)"
EXAM = "Examen"

TYPE_NORMALE = "Examen de session normal"


class TestCombinaisonDetectee(IntegrationTestCase):

    def setUp(self):
        seed_grille_grades()
        setting = frappe.get_single("Udshed Setting")
        setting.exiger_programmation = 0
        setting.save(ignore_permissions=True)
        frappe.db.set_value("Grade Formula", {"active": 1}, "active", 0)

        self.academic_year = make_academic_year()
        self.calendar = make_calendar_planing()
        self.faculty = make_faculty()
        self.teacher = make_teacher()
        self.fos = make_field_of_study(self.faculty, self.calendar, self.teacher)
        self.niveau = make_level(self.fos, level="BTS 1")

        self.course = make_course()
        self.tu = make_teaching_unit(
            self.course, self.academic_year, self.fos, self.niveau,
            credits=3, type_ue="Avec TP",
        )
        self.student = make_student(self.fos, self.niveau, "BTS")
        make_academic_reregistration(
            self.fos, "BTS 1", self.academic_year, [self.tu], student=self.student
        )
        self.session = make_session_examen(
            self.academic_year, self.calendar, filiere=self.fos, niveau=self.niveau
        )

        self.args = {
            "academic_year": self.academic_year.name,
            "semestre": "Semestre 1",
            "filiere": self.fos.name,
            "niveau": "BTS 1",
            "teaching_unit": self.tu.name,
        }

    # ------------------------------------------------------------------ #
    #  Moteur : combinaison canonique détectée
    # ------------------------------------------------------------------ #
    def test_combinaison_detectee_ordre_canonique(self):
        self.assertEqual(
            combinaison_detectee([CC, EXAM]),
            "Controle Continu(CC) + Examen",
        )
        self.assertEqual(
            combinaison_detectee([EXAM, CC, CCTP]),
            "Controle Continu(CC) + Controle Continu Travaux Pratiques(CCTP) + Examen",
        )
        self.assertEqual(
            combinaison_detectee([CCTP, EXAMTP, CC, EXAM]),
            "Controle Continu(CC) + Controle Continu Travaux Pratiques(CCTP)"
            " + Examen + Examen Travaux Pratiques(EXAMTP)",
        )

    # ------------------------------------------------------------------ #
    #  Les 4 combinaisons retenues sont calculées avec leur formule
    # ------------------------------------------------------------------ #
    def _note(self, cc=None, cctp=None, examtp=None, examen=None):
        return make_session_examen_note(
            self.session,
            self.student,
            self.tu,
            note_cc=cc,
            note_cctp=cctp,
            note_examtp=examtp,
            note_examen=examen,
        )

    def test_cc_exam(self):
        seed_formule("BTS", [CC, EXAM], [40, 60])
        note = self._note(cc=10, examen=16)
        # 10*0.4 + 16*0.6 = 13.6
        self.assertEqual(note.note_finale, 13.6)
        self.assertEqual(note.combinaison_detectee(), "Controle Continu(CC) + Examen")

    def test_cc_cctp_exam(self):
        seed_formule("BTS", [CC, CCTP, EXAM], [30, 20, 50])
        note = self._note(cc=10, cctp=12, examen=16)
        # 10*0.3 + 12*0.2 + 16*0.5 = 13.4
        self.assertEqual(note.note_finale, 13.4)
        self.assertEqual(
            note.combinaison_detectee(),
            "Controle Continu(CC) + Controle Continu Travaux Pratiques(CCTP) + Examen",
        )

    def test_cc_examtp_exam(self):
        seed_formule("BTS", [CC, EXAMTP, EXAM], [30, 20, 50])
        note = self._note(cc=10, examtp=14, examen=16)
        # 10*0.3 + 14*0.2 + 16*0.5 = 13.8
        self.assertEqual(note.note_finale, 13.8)
        self.assertEqual(
            note.combinaison_detectee(),
            "Controle Continu(CC) + Examen + Examen Travaux Pratiques(EXAMTP)",
        )

    def test_cc_cctp_examtp_exam(self):
        seed_formule("BTS", [CC, CCTP, EXAMTP, EXAM], [25, 15, 15, 45])
        note = self._note(cc=10, cctp=12, examtp=14, examen=16)
        # 10*0.25 + 12*0.15 + 14*0.15 + 16*0.45 = 13.6
        self.assertEqual(note.note_finale, 13.6)
        self.assertEqual(
            note.combinaison_detectee(),
            "Controle Continu(CC) + Controle Continu Travaux Pratiques(CCTP)"
            " + Examen + Examen Travaux Pratiques(EXAMTP)",
        )

    # ------------------------------------------------------------------ #
    #  La détection prime sur le type d'UE
    # ------------------------------------------------------------------ #
    def test_detection_prime_sur_type_ue(self):
        # UE « Avec TP » mais l'enseignant saisit CC + CCTP + EXAM.
        seed_formule("BTS", [CC, EXAM], [40, 60])
        seed_formule("BTS", [CC, CCTP, EXAM], [30, 20, 50])
        seed_formule("BTS", [CC, EXAM, "Travaux Pratique (TP)"], [30, 50, 20])
        note = self._note(cc=10, cctp=12, examen=16)
        # La formule CC+CCTP+EXAM doit être utilisée, pas celle Avec TP.
        self.assertEqual(note.note_finale, 13.4)

    # ------------------------------------------------------------------ #
    #  Combinaison non configurée
    # ------------------------------------------------------------------ #
    def test_combinaison_non_configuree_reste_indeterminee(self):
        seed_formule("BTS", [CC, EXAM], [40, 60])
        note = self._note(cc=10, cctp=12, examen=16)
        self.assertTrue(note.formule_manquante())
        self.assertIsNone(note.note_finale)

    # ------------------------------------------------------------------ #
    #  API : enregistrer_evaluations
    # ------------------------------------------------------------------ #
    def _enregistrer(self, cc=None, cctp=None, examtp=None, examen=None):
        rows = [
            {
                "student": self.student.name,
                "cc": cc,
                "note_cctp": cctp,
                "note_examtp": examtp,
                "note_examen": examen,
            }
        ]
        return enregistrer_evaluations(
            self.args["academic_year"],
            self.args["filiere"],
            self.args["niveau"],
            self.args["semestre"],
            self.args["teaching_unit"],
            rows,
        )

    def _note_api(self):
        session = frappe.db.get_value(
            "Session Examen",
            {
                "academic_year": self.academic_year.name,
                "semestre": "Semestre 1",
                "type_dexamen": TYPE_NORMALE,
            },
            "name",
        )
        return frappe.get_doc(
            "Session Examen Note",
            frappe.db.get_value(
                "Session Examen Note",
                {
                    "session_examen": session,
                    "student": self.student.name,
                    "teaching_unit": self.tu.name,
                },
                "name",
            ),
        )

    def test_api_enregistre_et_calcule(self):
        seed_formule("BTS", [CC, CCTP, EXAMTP, EXAM], [25, 15, 15, 45])
        resultat = self._enregistrer(cc=10, cctp=12, examtp=14, examen=16)
        self.assertEqual(resultat["saved"], 1)
        note = self._note_api()
        self.assertEqual(note.note_cctp, 12)
        self.assertEqual(note.note_examtp, 14)
        self.assertEqual(note.note_cc_moyenne, 10)
        self.assertEqual(note.note_finale, 13.6)

    def test_api_apercu_detecte_combinaison(self):
        seed_formule("BTS", [CC, CCTP, EXAM], [30, 20, 50])
        resultat = calculer_apercu(
            self.student.name,
            self.tu.name,
            notes_cc=json.dumps([{"cc_label": "CC", "cc_weight": 1, "note_cc": 10}]),
            note_examen=16,
            note_cctp=12,
        )
        self.assertEqual(
            resultat["combinaison"],
            "Controle Continu(CC) + Controle Continu Travaux Pratiques(CCTP) + Examen",
        )
        self.assertFalse(resultat["formule_manquante"])
        self.assertEqual(resultat["note_finale"], 13.4)

    def test_api_apercu_combinaison_non_configuree(self):
        seed_formule("BTS", [CC, EXAM], [40, 60])
        resultat = calculer_apercu(
            self.student.name,
            self.tu.name,
            notes_cc=json.dumps([{"cc_label": "CC", "cc_weight": 1, "note_cc": 10}]),
            note_examen=16,
            note_cctp=12,
        )
        self.assertTrue(resultat["formule_manquante"])
        self.assertIsNone(resultat["note_finale"])