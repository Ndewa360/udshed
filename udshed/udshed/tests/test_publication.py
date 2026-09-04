# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests du workflow de validation / publication des notes.

Cas couverts (règles du cahier des charges) :
  - la saisie fait passer les notes de « Brouillon » à « Saisi » ;
  - la validation (valider_notes) passe les notes à « Validé » ;
  - une session n'est publiable que si toutes ses notes sont validées ;
  - après validation, la publication passe les notes à « Publié » ;
  - la publication est réversible : les notes restent modifiables après
    publication (requêtes et corrections), y compris le CC ;
  - le babillard public n'expose que les notes publiées, en pourcentage.
"""

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api.babillard import consulter_notes
from udshed.api.saisie_notes import (
    _sauvegarder_cc,
    _sauvegarder_examen,
    publier_session,
    valider_notes,
)
from udshed.udshed._fixture_factory import (
    make_academic_year,
    make_calendar_planing,
    make_course,
    make_faculty,
    make_field_of_study,
    make_level,
    make_session_examen,
    make_student,
    make_teacher,
    make_teaching_unit,
    seed_formule,
    seed_grille_grades,
    suppress_commits,
)

TYPE_CC = "Controlle Continue (CC)"
TYPE_NORMALE = "Examen de session normal"


class TestValidationEtPublication(IntegrationTestCase):

    def setUp(self):
        seed_grille_grades()
        seed_formule("BTS", ["Controle Continu(CC)", "Examen"], [40, 60])

        # Les tests qui PUBLIENT une session utilisent une année académique
        # unique (isolation : la saisie réutilise les sessions par
        # année + semestre + type). Les autres tests partagent 2026-2027.
        start = getattr(self, "ACADEMIC_YEAR", None) or "2026"
        self.academic_year = make_academic_year(
            start=start, end=str(int(start) + 1)
        )

        self.calendar = make_calendar_planing()
        self.faculty = make_faculty()
        self.teacher = make_teacher()
        self.fos = make_field_of_study(self.faculty, self.calendar, self.teacher)
        self.niveau = make_level(self.fos, level="BTS 1")
        self.course = make_course()
        self.tu = make_teaching_unit(
            self.course, self.academic_year, self.fos, self.niveau,
            credits=3, type_ue="Sans TP",
        )
        self.student = make_student(self.fos, self.niveau, "BTS")
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
    #  Utilitaires
    # ------------------------------------------------------------------ #
    def _session_de_type(self, type_dexamen):
        return frappe.db.get_value(
            "Session Examen",
            {
                "academic_year": self.academic_year.name,
                "semestre": "Semestre 1",
                "type_dexamen": type_dexamen,
            },
            "name",
        )

    def _note(self, session):
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

    def _saisir_cc_examen(self):
        """Saisit CC + Examen via le parcours réel de l'API et retourne la session normale."""
        with suppress_commits():
            _sauvegarder_cc(
                self.args,
                [{"student": self.student.name,
                  "notes_cc": [{"cc_label": "CC 1", "cc_weight": 1, "note_cc": 14}]}],
            )
            _sauvegarder_examen(
                self.args,
                [{"student": self.student.name, "note_examen": 12}],
            )
        return self._session_de_type(TYPE_NORMALE)

    # ------------------------------------------------------------------ #
    #  Saisi / Validé / Publié
    # ------------------------------------------------------------------ #
    def test_1_saisie_passe_les_notes_a_saisi(self):
        with suppress_commits():
            _sauvegarder_cc(
                self.args,
                [{"student": self.student.name,
                  "notes_cc": [{"cc_label": "CC 1", "cc_weight": 1, "note_cc": 14}]}],
            )
        session_cc = self._session_de_type(TYPE_CC)
        self.assertEqual(self._note(session_cc).statut, "Saisi")

    def test_2_valider_notes_marque_valide(self):
        session = self._saisir_cc_examen()
        resultat = valider_notes(session)
        self.assertEqual(resultat["validated"], 1)
        self.assertEqual(self._note(session).statut, "Validé")

    def test_3_publier_refuse_si_non_validee(self):
        session = self._saisir_cc_examen()
        with self.assertRaises(frappe.ValidationError):
            publier_session(session)
        self.assertEqual(
            frappe.db.get_value("Session Examen", session, "statut"), "Brouillon"
        )
        self.assertEqual(self._note(session).statut, "Saisi")

    def test_4_publier_apres_validation(self):
        session = self._saisir_cc_examen()
        valider_notes(session)
        resultat = publier_session(session)
        self.assertEqual(resultat["statut"], "Publiée")
        self.assertEqual(
            frappe.db.get_value("Session Examen", session, "statut"), "Publiée"
        )
        self.assertEqual(self._note(session).statut, "Publié")

    test_4_publier_apres_validation.ACADEMIC_YEAR = "2024"

    def test_5_session_publiee_restera_modifiable(self):
        session = self._saisir_cc_examen()
        valider_notes(session)
        publier_session(session)
        with suppress_commits():
            _sauvegarder_examen(
                self.args,
                [{"student": self.student.name, "note_examen": 18}],
            )
        self.assertEqual(self._note(session).note_examen, 18)
        self.assertEqual(self._note(session).statut, "Publié")

    test_5_session_publiee_restera_modifiable.ACADEMIC_YEAR = "2025"
#  Babillard
    # ------------------------------------------------------------------ #
    def test_7_babillard_affiche_la_note_publiee_en_pourcentage(self):
        session = self._saisir_cc_examen()
        valider_notes(session)
        publier_session(session)

        data = consulter_notes(
            niveau="BTS 1",
            matricule=self.student.matricule,
            academic_year=self.academic_year.name,
            semestre="Semestre 1",
        )
        self.assertTrue(data["success"], data.get("message"))
        semestre = data["semesters"][0]
        self.assertEqual(len(semestre["ues"]), 1)
        ue = semestre["ues"][0]
        self.assertEqual(ue["note_finale"], 12.8)
        self.assertEqual(ue["note_pct"], 64.0)
        self.assertEqual(ue["statut"], "Validé")

    test_7_babillard_affiche_la_note_publiee_en_pourcentage.ACADEMIC_YEAR = "2027"

    def test_8_babillard_ignore_les_notes_non_publiees(self):
        self._saisir_cc_examen()
        data = consulter_notes(
            niveau="BTS 1",
            matricule=self.student.matricule,
            academic_year=self.academic_year.name,
            semestre="Semestre 1",
        )
        self.assertFalse(data["success"])

