# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests de la résolution automatique des poids dans la Saisie des notes.

Les poids des évaluations ne sont JAMAIS saisis manuellement : ils sont
déduits de la Grade Formula active (cycle + combinaison du type d'UE).
La Saisie des notes les affiche en lecture seule et le PDF de résultats
est généré depuis les données réellement enregistrées.

Cas couverts :
  - résolution de la formule selon le type d'UE (Sans TP, Avec TP, Stage SMSB) ;
  - cycle déduit du libellé du niveau ;
  - charger_data expose la formule à la page de saisie ;
  - la sauvegarde du CC force le poids à 1 (moyenne arithmétique), quel que
    soit le poids envoyé par le client ;
  - le PDF est généré depuis les données réelles (en-tête complet + tableau).
"""

import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch

from udshed.api.saisie_notes import (
    _cycle_pour_niveau,
    _formule_pour_ue,
    _sauvegarder_cc,
    _sauvegarder_examen,
    charger_data,
    generer_pdf,
)
from udshed.udshed._fixture_factory import (
    make_academic_reregistration,
    make_academic_year,
    make_calendar_planing,
    make_course,
    make_faculty,
    make_field_of_study,
    make_level,
    make_student,
    make_teacher,
    make_teaching_unit,
    seed_formule,
    seed_grade_formula,
    seed_grille_grades,
)

TYPE_CC = "Controlle Continue (CC)"
TYPE_NORMALE = "Examen de session normal"


class TestFormuleDansSaisie(IntegrationTestCase):

    def setUp(self):
        seed_grille_grades()
        setting = frappe.get_single("Udshed Setting")
        setting.exiger_programmation = 0
        setting.save(ignore_permissions=True)

        self.academic_year = make_academic_year()
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
        make_academic_reregistration(
            self.fos, "BTS 1", self.academic_year, [self.tu], student=self.student
        )

        self.args = {
            "academic_year": self.academic_year.name,
            "semestre": "Semestre 1",
            "filiere": self.fos.name,
            "niveau": "BTS 1",
            "teaching_unit": self.tu.name,
        }

    def _composantes(self, formula):
        return [(c["composante"], c["pourcentage"]) for c in formula["composantes"]]

    # ------------------------------------------------------------------ #
    #  Résolution de la formule
    # ------------------------------------------------------------------ #
    def test_cycle_deduit_du_libelle_du_niveau(self):
        self.assertEqual(_cycle_pour_niveau("BTS 1"), "BTS")
        self.assertEqual(_cycle_pour_niveau("BTS 2"), "BTS")
        self.assertEqual(_cycle_pour_niveau("Licence 1"), "Licence")
        self.assertEqual(_cycle_pour_niveau("Master 2"), "Master")
        self.assertEqual(_cycle_pour_niveau(""), "Licence")

    def test_formule_sans_tp(self):
        seed_formule("BTS", ["Controle Continu(CC)", "Examen"], [40, 60])
        f = _formule_pour_ue(self.tu.name, self.fos.name, "BTS 1")
        self.assertIsNotNone(f)
        self.assertEqual(f["cycle"], "BTS")
        self.assertEqual(f["combinaison"], "Controle Continu(CC) + Examen")
        self.assertEqual(
            self._composantes(f),
            [("Controle Continu(CC)", 40.0), ("Examen", 60.0)],
        )

    def test_formule_avec_tp(self):
        seed_grade_formula("BTS", 30, 50, 20)
        tu_tp = make_teaching_unit(
            self.course, self.academic_year, self.fos, self.niveau,
            credits=4, type_ue="Avec TP",
        )
        f = _formule_pour_ue(tu_tp.name, self.fos.name, "BTS 1")
        self.assertIsNotNone(f)
        self.assertEqual(
            self._composantes(f),
            [
                ("Controle Continu(CC)", 30.0),
                ("Examen", 50.0),
                ("Travaux Pratique (TP)", 20.0),
            ],
        )

    def test_formule_stage_smsb(self):
        seed_formule("BTS", ["Examen", "Rapport"], [70, 30])
        tu_stage = make_teaching_unit(
            self.course, self.academic_year, self.fos, self.niveau,
            credits=6, type_ue="Stage SMSB",
        )
        f = _formule_pour_ue(tu_stage.name, self.fos.name, "BTS 1")
        self.assertIsNotNone(f)
        self.assertEqual(
            self._composantes(f),
            [("Examen", 70.0), ("Rapport", 30.0)],
        )

    def test_formule_sans_formule_active(self):
        frappe.db.set_value("Grade Formula", {"active": 1}, "active", 0)
        self.assertIsNone(_formule_pour_ue(self.tu.name, self.fos.name, "BTS 1"))

    # ------------------------------------------------------------------ #
    #  charger_data expose la formule
    # ------------------------------------------------------------------ #
    def test_charger_data_inclut_formule(self):
        seed_formule("BTS", ["Controle Continu(CC)", "Examen"], [40, 60])
        data = charger_data(
            self.academic_year.name, self.fos.name, "BTS 1", "Semestre 1", self.tu.name
        )
        self.assertIn("formule", data)
        self.assertEqual(data["formule"]["cycle"], "BTS")
        self.assertEqual(len(data["formule"]["composantes"]), 2)
        self.assertTrue(
            any(s["student"] == self.student.name for s in data["students"])
        )

    # ------------------------------------------------------------------ #
    #  Poids forcé à 1 côté serveur
    # ------------------------------------------------------------------ #
    def test_sauvegarder_cc_force_poids_un(self):
        seed_formule("BTS", ["Controle Continu(CC)", "Examen"], [40, 60])
        rows = [
            {
                "student": self.student.name,
                "notes_cc": [
                    {"cc_label": "CC 1", "cc_weight": 7, "note_cc": 14},
                    {"cc_label": "CC 2", "cc_weight": 7, "note_cc": 16},
                ],
            }
        ]
        _sauvegarder_cc(self.args, rows)

        session_cc = frappe.db.get_value(
            "Session Examen",
            {
                "type_dexamen": TYPE_CC,
                "academic_year": self.academic_year.name,
                "semestre": "Semestre 1",
            },
            "name",
        )
        note_name = frappe.db.get_value(
            "Session Examen Note",
            {
                "student": self.student.name,
                "teaching_unit": self.tu.name,
                "session_examen": session_cc,
            },
            "name",
        )
        self.assertTrue(note_name)

        items = frappe.get_all(
            "Note CC Item",
            filters={"parent": note_name},
            fields=["cc_label", "cc_weight", "note_cc"],
            order_by="idx asc",
        )
        self.assertEqual(len(items), 2)
        for item in items:
            self.assertEqual(item.cc_weight, 1, "le poids du CC doit être forcé à 1")
        self.assertEqual([i.note_cc for i in items], [14, 16])

        doc = frappe.get_doc("Session Examen Note", note_name)
        self.assertEqual(doc.note_cc_moyenne, 15)

    # ------------------------------------------------------------------ #
    #  PDF depuis les données réelles
    # ------------------------------------------------------------------ #
    def test_generer_pdf_donnees_reelles(self):
        seed_formule("BTS", ["Controle Continu(CC)", "Examen"], [40, 60])
        _sauvegarder_cc(
            self.args,
            [
                {
                    "student": self.student.name,
                    "notes_cc": [{"cc_label": "CC 1", "cc_weight": 1, "note_cc": 15}],
                }
            ],
        )
        _sauvegarder_examen(
            self.args,
            [{"student": self.student.name, "note_examen": 14}],
        )

        with patch("udshed.api.saisie_notes._html_en_pdf", return_value=b"%PDF-TEST-OK") as mock_pdf:
            generer_pdf(
                self.academic_year.name,
                self.fos.name,
                "BTS 1",
                "Semestre 1",
                self.tu.name,
            )

        self.assertEqual(frappe.response["filecontent"], b"%PDF-TEST-OK")
        self.assertTrue(frappe.response["filename"].endswith(".pdf"))
        self.assertEqual(frappe.response["content_type"], "application/pdf")

        html = mock_pdf.call_args[0][0]
        for fragment in [
            "Faculté",
            self.fos.name_of_field,
            "BTS 1",
            "Semestre 1",
            "Crédits",
            "Formule appliquée",
            "CC (40%)",
            "Examen (60%)",
            self.student.matricule,
            "CCTP",
            "EXAMTP",
            "MOY",
            "GRD",
            "PTS",
            "15.0",
            "14.0",
        ]:
            self.assertIn(fragment, html, "fragment manquant dans le PDF : " + fragment)