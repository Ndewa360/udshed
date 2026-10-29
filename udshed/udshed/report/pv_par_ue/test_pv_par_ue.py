# Copyright (c) 2026, Udshed and contributors
# For license information, please see license.txt

"""Tests du Script Report « PV par UE ».

Le rapport ne fait qu'adapter `udshed.api.proces_verbal.get_pv_ue_data` (déjà
couvert par `test_resultat_ue`) au format (columns, data) d'un Script Report :
une colonne par matière, une ligne par étudiant, plus la synthèse de l'UE.
"""

import frappe
from frappe.tests import IntegrationTestCase

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
    make_teaching_unit_value,
    seed_formule,
    seed_grille_grades,
    unique_code,
)
from udshed.api.proces_verbal import get_pv_ue_data
from udshed.udshed.report.pv_par_ue.pv_par_ue import execute


class TestPvParUE(IntegrationTestCase):
    """Rapport « PV par UE » : colonnes, lignes et garde-fous de filtres."""

    def setUp(self):
        seed_grille_grades()
        seed_formule("BTS", ["Examen"], [100], seuil=50)

        self.academic_year = make_academic_year()
        self.calendar = make_calendar_planing()
        self.faculty = make_faculty()
        self.teacher = make_teacher()
        self.fos = make_field_of_study(self.faculty, self.calendar, self.teacher)
        self.niveau = make_level(self.fos, level="BTS 1")

        self.ue = make_teaching_unit_value(
            self.academic_year, code=unique_code("UTI308")
        )
        self.tu1 = self._matiere(unique_code("ANG302"))
        self.tu2 = self._matiere(unique_code("ECO304"))

        self.student = make_student(self.fos, self.niveau, cycle="BTS")
        make_academic_reregistration(
            self.fos, "BTS 1", self.academic_year, [self.tu1, self.tu2],
            student=self.student,
        )
        self.session = make_session_examen(
            self.academic_year, self.calendar, filiere=self.fos, niveau=self.niveau,
        )

    def _matiere(self, code, credits=3):
        return make_teaching_unit(
            make_course(code=code), self.academic_year, self.fos, self.niveau,
            credits=credits, unite_de_valeur=self.ue,
        )

    def _filtres(self, ue=None):
        return {
            "academic_year": self.academic_year.name,
            "semestre": "Semestre 1",
            "filiere": self.fos.name,
            "niveau": "BTS 1",
            "teaching_unit_value": (ue or self.ue).name,
        }

    def _saisir_ue_complete(self):
        # 10.2/20 -> 51 %, 13.5/20 -> 67.5 % : (51 + 67.5) / 2 = 59.25 %
        make_session_examen_note(
            self.session, self.student, self.tu1, note_examen=10.2, statut="Saisi"
        )
        make_session_examen_note(
            self.session, self.student, self.tu2, note_examen=13.5, statut="Saisi"
        )

    def test_filtres_obligatoires(self):
        with self.assertRaises(frappe.ValidationError):
            execute({"academic_year": self.academic_year.name, "semestre": "Semestre 1"})

    def test_ue_sans_matiere_dans_la_classe(self):
        """Une UE sans matière dans la classe est refusée, pas affichée vide."""
        ue_vide = make_teaching_unit_value(
            self.academic_year, code=unique_code("VIDE01")
        )
        with self.assertRaises(frappe.ValidationError):
            execute(self._filtres(ue=ue_vide))

    def test_colonnes_et_lignes(self):
        self._saisir_ue_complete()

        columns, data = execute(self._filtres())

        noms = [c["fieldname"] for c in columns]
        for attendu in (
            "num", "matricule", "student_name", "note_ue_pct", "grade", "point",
            "credits_obtenus", "statut",
        ):
            self.assertIn(attendu, noms)
        # Une colonne par matière, nommée mat_<teaching_unit>.
        for tu in (self.tu1, self.tu2):
            self.assertIn(f"mat_{tu.name}", noms)

        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(row["num"], 1)
        self.assertEqual(row["matricule"], self.student.matricule)
        self.assertEqual(row["student_name"], f"{self.student.nom} {self.student.prenom}")
        self.assertEqual(row[f"mat_{self.tu1.name}"], 51.0)
        self.assertEqual(row[f"mat_{self.tu2.name}"], 67.5)
        self.assertEqual(row["note_ue_pct"], 59.25)
        # 59.25 % -> bande [55.00 ; 59.99] de la grille officielle.
        self.assertEqual(row["grade"], "C+")
        self.assertEqual(row["point"], 2.3)
        self.assertEqual(row["credits_obtenus"], 6)
        self.assertEqual(row["statut"], "Validé")
        # Lu par le formatter JS pour colorier la note UE.
        self.assertEqual(row["seuil_validation"], 50.0)

    def test_etudiant_sans_note_donne_une_ligne_vide(self):
        columns, data = execute(self._filtres())

        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertIsNone(row["note_ue_pct"])
        self.assertIsNone(row[f"mat_{self.tu1.name}"])
        self.assertIsNone(row[f"mat_{self.tu2.name}"])
        self.assertEqual(row["statut"], "En attente")
        # Les colonnes matière restent présentes malgré l'absence de note.
        noms = [c["fieldname"] for c in columns]
        self.assertIn(f"mat_{self.tu1.name}", noms)

    def test_gabarit_pdf_accepte_une_ue_incomplete(self):
        """Le gabarit ne doit pas échouer sur une valeur vide.

        Le format « %.2f » du gabarit levait une TypeError sur `point = ""`
        (aucun grade pour un étudiant sans note) et faisait échouer tout
        le PDF, y compris pour les étudiants bien notés.
        """
        self._saisir_ue_complete()

        data = get_pv_ue_data(
            self.academic_year.name, self.fos.name, "BTS 1", "Semestre 1", self.ue.name,
        )
        # Second étudiant sans note : ni note matière, ni note UE, ni point.
        data["etudiants"].append(
            dict(
                data["etudiants"][0],
                student="MAT-VIDE",
                matricule="MAT-VIDE",
                notes={},
                note_ue_pct=None,
                grade="",
                point=None,
                mention="",
                statut="En attente",
            )
        )

        with open(
            frappe.get_app_path("udshed", "public", "print_templates", "pv_ue.html"),
            encoding="utf-8",
        ) as f:
            html = frappe.render_template(f.read(), {"data": data})

        # La note de l'étudiant noté est bien rendue, celle de l'autre non.
        self.assertIn("MAT-VIDE", html)
        self.assertEqual(html.count("59.25"), 1)
