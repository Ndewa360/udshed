# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests du parcours session normale -> rattrapage.

Cas couverts :
  - 11-12 : calcul de la note UE et validation selon le seuil du cycle ;
  - 13 : seuils par cycle ;
  - 14 : crédits LMD indépendants des coefficients ;
  - 15-20 : éligibilité, conservation et MAX(normale, rattrapage) ;
  - 24 : création de la session de rattrapage.
"""

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api.retake import (
    creer_session_rattrapage,
    etudiants_eligibles_rattrapage,
    identifier_rattrapages,
)
from udshed.api.resultat_academique import calculer_resultat_session
from udshed.api.saisie_notes import _sauvegarder_rattrapage
from udshed.grade_calculation import est_valide
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
    seed_formule,
    seed_grade_formula,
    seed_grille_grades,
    suppress_commits,
)

TYPE_NORMALE = "Examen de session normal"
TYPE_RATTRAPAGE = "Examen de rattrapage"


class TestSessionNormaleEtRattrapage(IntegrationTestCase):

    def setUp(self):
        seed_grille_grades()
        seed_grade_formula("BTS", 30, 50, 20)
        self.academic_year = make_academic_year()
        self.calendar = make_calendar_planing()
        self.faculty = make_faculty()
        self.teacher = make_teacher()
        self.fos = make_field_of_study(self.faculty, self.calendar, self.teacher)
        self.niveau = make_level(self.fos, level="BTS 1")

        self.course = make_course()
        self.tu = make_teaching_unit(
            self.course, self.academic_year, self.fos, self.niveau, credits=3,
            type_ue="Avec TP",
        )
        self.course2 = make_course()
        self.tu2 = make_teaching_unit(
            self.course2, self.academic_year, self.fos, self.niveau, credits=6,
            type_ue="Avec TP",
        )

        self.student = make_student(self.fos, self.niveau, "BTS")
        self.session = make_session_examen(
            self.academic_year, self.calendar, filiere=self.fos, niveau=self.niveau
        )

    def _note(self, note_cc, note_examen, session=None, tu=None):
        return make_session_examen_note(
            session or self.session,
            self.student,
            tu or self.tu,
            note_cc=note_cc,
            note_examen=note_examen,
        )

    # ------------------------------------------------------------------ #
    #  11-13 : session normale
    # ------------------------------------------------------------------ #
    def test_11_note_ue_session_normale(self):
        note = self._note(16, 18)
        self.assertEqual(note.note_finale, 13.8)
        self.assertEqual(note.note_pct, 69.0)
        self.assertEqual(note.grade, "C")

    def test_12_validation_selon_seuil(self):
        valide = self._note(16, 18)
        self.assertTrue(est_valide(valide.note_finale, "BTS"))
        echoue = self._note(6, 6, tu=self.tu2)
        self.assertFalse(est_valide(echoue.note_finale, "BTS"))

        with suppress_commits():
            resultat = calculer_resultat_session(self.student.name, self.session.name)
        self.assertEqual(resultat["total"], 2)
        statuts = {r["statut"] for r in resultat["resultats"]}
        self.assertEqual(statuts, {"Validé", "Non Validé"})

    def test_13_seuil_bts(self):
        # 50 % de validation : 10/20 -> 50 % validé, 9.9/20 -> non
        self.assertTrue(est_valide(10, "BTS"))
        self.assertFalse(est_valide(9.9, "BTS"))

    def test_14_credits_independants_des_coefficients(self):
        note1 = make_session_examen_note(
            self.session, self.student, self.tu, note_cc=16, note_examen=18
        )
        note2 = make_session_examen_note(
            self.session, self.student, self.tu2, note_cc=16, note_examen=18
        )
        # Mêmes notes => même note finale, peu importe les crédits (3 vs 6)
        self.assertEqual(note1.note_finale, note2.note_finale)

    def test_14b_selection_formule_selon_type_ue(self):
        """Une UE Sans TP utilise la formule CC+Examen, pas la formule Avec TP."""
        seed_formule("BTS", ["Controle Continu(CC)", "Examen"], [40, 60])
        tu_sans_tp = make_teaching_unit(
            make_course(), self.academic_year, self.fos, self.niveau,
            credits=3, type_ue="Sans TP",
        )
        note = make_session_examen_note(
            self.session, self.student, tu_sans_tp, note_cc=16, note_examen=18
        )
        # 16*0.4 + 18*0.6 = 17.2 -> 86 %
        self.assertEqual(note.note_finale, 17.2)
        self.assertEqual(note.note_pct, 86.0)

    # ------------------------------------------------------------------ #
    #  15-16 : éligibilité au rattrapage
    # ------------------------------------------------------------------ #
    def test_15_eligible_si_ue_non_validee(self):
        self._note(6, 6)
        data = identifier_rattrapages(self.session.name)
        self.assertEqual(data["total_eligibles"], 1)
        eligible = data["etudiants_eligibles"][0]
        self.assertEqual(eligible["student"], self.student.name)
        self.assertEqual(eligible["statut"], "À rattraper")
        self.assertIn(self.course.intitule, eligible["ue_concernees"])
        self.assertEqual(eligible["credits_concernee"], 3)

    def test_16_non_eligible_si_toutes_ue_validees(self):
        self._note(16, 18)
        data = identifier_rattrapages(self.session.name)
        self.assertEqual(data["total_eligibles"], 0)
        self.assertEqual(data["etudiants"], [])

    # ------------------------------------------------------------------ #
    #  17-18 : MAX(normale, rattrapage) et conservation
    # ------------------------------------------------------------------ #
    def _creer_rattrapage(self, note_rattrapage):
        rattrapage_session = make_session_examen(
            self.academic_year,
            self.calendar,
            filiere=self.fos,
            niveau=self.niveau,
            type_dexamen=TYPE_RATTRAPAGE,
        )
        make_session_examen_note(
            rattrapage_session,
            self.student,
            self.tu,
            note_cc=16,
            note_examen=note_rattrapage,
        )
        return rattrapage_session

    def test_17_max_note_normale_rattrapage(self):
        self._note(16, 18)  # 13.8 / 69 %
        self._creer_rattrapage(19)  # 14.3 / 71.5 %

        with suppress_commits():
            resultat = calculer_resultat_session(self.student.name, self.session.name)
        res = resultat["resultats"][0]
        self.assertAlmostEqual(res["note_finale"], 14.3)
        self.assertEqual(res["statut"], "Validé")
        self.assertTrue(res["est_rattrapage"])
        self.assertIsNotNone(res["session_rattrapage"])
        self.assertEqual(res["session_normale"], frappe.db.get_value(
            "Session Examen Note",
            {"session_examen": self.session.name, "student": self.student.name,
             "teaching_unit": self.tu.name},
            "name",
        ))

    def test_17b_rattrapage_inferieur_garde_normale(self):
        self._note(16, 18)  # 13.8 / 69 %
        self._creer_rattrapage(10)  # 9.8 / 49 % < 13.8

        with suppress_commits():
            resultat = calculer_resultat_session(self.student.name, self.session.name)
        res = resultat["resultats"][0]
        self.assertAlmostEqual(res["note_finale"], 13.8)
        self.assertFalse(res["est_rattrapage"])
        self.assertIsNone(res["session_rattrapage"])

    def test_18_conservation_session_normale(self):
        normale = self._note(16, 18)
        self._creer_rattrapage(19)

        with suppress_commits():
            calculer_resultat_session(self.student.name, self.session.name)

        normale.reload()
        self.assertEqual(normale.note_finale, 13.8)
        self.assertEqual(normale.note_pct, 69.0)

    # ------------------------------------------------------------------ #
    #  19 : composantes conservées au rattrapage
    # ------------------------------------------------------------------ #
    def test_19_composantes_conservees_au_rattrapage(self):
        self._note(16, 18)
        args = {
            "academic_year": self.academic_year.name,
            "teaching_unit": self.tu.name,
            "semestre": "Semestre 1",
            "filiere": self.fos.name,
            "niveau": "BTS 1",
        }
        rows = [{"student": self.student.name, "note_examen_rattrapage": 19}]
        with suppress_commits():
            _sauvegarder_rattrapage(args, rows)

        rattrapage_session = frappe.db.get_value(
            "Session Examen",
            {
                "academic_year": self.academic_year.name,
                "semestre": "Semestre 1",
                "type_dexamen": TYPE_RATTRAPAGE,
            },
            "name",
        )
        self.assertIsNotNone(rattrapage_session)
        rattrapage_note = frappe.db.get_value(
            "Session Examen Note",
            {"student": self.student.name, "teaching_unit": self.tu.name,
             "session_examen": rattrapage_session},
            ["name", "note_cc_moyenne", "note_examen", "note_examen_rattrapage",
             "note_examen_active", "note_tp", "note_finale"],
            as_dict=True,
        )
        self.assertIsNotNone(rattrapage_note)
        self.assertEqual(rattrapage_note.note_cc_moyenne, 16)
        self.assertEqual(rattrapage_note.note_examen, 18)  # conservée
        self.assertEqual(rattrapage_note.note_examen_rattrapage, 19)
        self.assertEqual(rattrapage_note.note_examen_active, 19)
        self.assertFalse(rattrapage_note.note_tp)
        self.assertEqual(rattrapage_note.note_finale, 14.3)

    # ------------------------------------------------------------------ #
    #  20 : structure de l'identification
    # ------------------------------------------------------------------ #
    def test_20_structure_identifier_rattrapages(self):
        self._note(6, 6)
        data = identifier_rattrapages(self.session.name)
        for cle in ("session", "etudiants", "total_eligibles", "etudiants_eligibles"):
            self.assertIn(cle, data)
        detail = data["etudiants"][0]
        for cle in ("student", "teaching_unit", "credits", "note_session_normale",
                    "seuil", "statut", "ue_name"):
            self.assertIn(cle, detail)
        self.assertEqual(detail["statut"], "Non validé")
        self.assertEqual(detail["credits"], 3)
        self.assertEqual(detail["seuil"], 50)

    # ------------------------------------------------------------------ #
    #  24 : création de la session de rattrapage
    # ------------------------------------------------------------------ #
    def test_24_creer_session_rattrapage(self):
        self._note(6, 6)
        resultat = creer_session_rattrapage(
            self.session.name, "2026-11-02", "2026-11-16"
        )
        self.assertEqual(resultat["nb_etudiants_concernes"], 1)

        sess_rattrapage = frappe.get_doc("Session Examen", resultat["session_rattrapage"])
        self.assertEqual(sess_rattrapage.type_dexamen, TYPE_RATTRAPAGE)
        self.assertEqual(sess_rattrapage.academic_year, self.academic_year.name)
        self.assertEqual(sess_rattrapage.semestre, "Semestre 1")
        classes = [(c.filiere, c.niveau) for c in sess_rattrapage.classes_concernees]
        self.assertIn((self.fos.name, str(self.niveau.name)), classes)

    def test_etudiants_eligibles_rattrapage_api(self):
        self._note(6, 6)
        data = etudiants_eligibles_rattrapage(
            self.academic_year.name, "Semestre 1", self.fos.name, self.niveau.name
        )
        self.assertEqual(data["total_eligibles"], 1)
        self.assertEqual(data["etudiants"][0]["student"], self.student.name)
        self.assertEqual(data["etudiants"][0]["nb_ue_concernees"], 1)
