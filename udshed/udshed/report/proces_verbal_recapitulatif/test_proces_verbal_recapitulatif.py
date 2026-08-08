# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api.resultat_academique import calculer_resultat_session
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
    seed_grade_formula,
    seed_grille_grades,
    suppress_commits,
)
from udshed.udshed.report.proces_verbal_recapitulatif.proces_verbal_recapitulatif import (
    execute,
)


class TestProcesVerbalRecapitulatif(IntegrationTestCase):
    """Tests du Script Report « Proces Verbal Recapitulatif » (PV de Classe)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.formula = seed_grade_formula("BTS", 30, 50, 20)
        seed_grille_grades()

    def setUp(self):
        self.academic_year = make_academic_year()
        self.calendar = make_calendar_planing()
        self.faculty = make_faculty()
        self.teacher = make_teacher()
        self.fos = make_field_of_study(self.faculty, self.calendar, self.teacher)
        self.niveau = make_level(self.fos)

        self.course1 = make_course()
        self.tu1 = make_teaching_unit(self.course1, self.academic_year, self.fos, self.niveau, credits=3)
        self.course2 = make_course()
        self.tu2 = make_teaching_unit(self.course2, self.academic_year, self.fos, self.niveau, credits=3)

        self.student = make_student(self.fos, self.niveau, "BTS")
        frappe.db.set_value("Student", self.student.name, "niveau_actuel", "BTS 1")
        self.student.reload()

        self.session1 = make_session_examen(
            self.academic_year, self.calendar,
            filiere=self.fos, niveau=self.niveau,
        )
        self.session2 = make_session_examen(
            self.academic_year, self.calendar,
            filiere=self.fos, niveau=self.niveau,
        )

    def _produire_resultats(self):
        """Crée des notes publiées puis les Resultat Academique / Semestre."""
        make_session_examen_note(
            self.session1, self.student, self.tu1, note_cc=16, note_examen=18,
        )
        make_session_examen_note(
            self.session2, self.student, self.tu2, note_cc=6, note_examen=6,
        )
        with suppress_commits():
            calculer_resultat_session(self.student.name, self.session1.name)
            calculer_resultat_session(self.student.name, self.session2.name)

    def _filtres(self):
        return {
            "academic_year": self.academic_year.name,
            "semestre": "Semestre 1",
            "filiere": self.fos.name,
            "niveau": "BTS 1",
        }

    def test_filtres_obligatoires(self):
        with self.assertRaises(frappe.ValidationError):
            execute({"academic_year": self.academic_year.name, "semestre": "Semestre 1"})

    def test_rapport_retourne_colonnes_ue_et_lignes(self):
        self._produire_resultats()

        columns, data = execute(self._filtres())

        # Colonnes statiques
        noms = [c["fieldname"] for c in columns]
        self.assertIn("num", noms)
        self.assertIn("matricule", noms)
        self.assertIn("student_name", noms)
        self.assertIn("tci", noms)
        self.assertIn("tcc", noms)
        self.assertIn("pct_validation", noms)
        self.assertIn("mps", noms)
        self.assertIn("mpc", noms)
        self.assertIn("mention", noms)

        # Colonnes dynamiques : une par UE du semestre
        self.assertIn(f"ue_{self.tu1.name}", noms)
        self.assertIn(f"ue_{self.tu2.name}", noms)

        # Une ligne par étudiant
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(row["num"], 1)
        self.assertEqual(row["matricule"], self.student.matricule)
        self.assertEqual(row["student_name"], f"{self.student.nom} {self.student.prenom}")
        self.assertEqual(row[f"ue_{self.tu1.name}"], "C")
        self.assertEqual(row[f"ue_{self.tu2.name}"], "F")
        self.assertEqual(row[f"ue_{self.tu1.name}_non_valide"], 0)
        self.assertEqual(row[f"ue_{self.tu2.name}_non_valide"], 1)

        # Synthèse : TCI = 6 crédits, TCC = 3 (une seule UE validée), MPS = 1.0
        self.assertEqual(row["tci"], 6)
        self.assertEqual(row["tcc"], 3)
        self.assertEqual(row["pct_validation"], 50.0)
        self.assertEqual(row["mps"], 1.0)
        self.assertEqual(row["mpc"], 1.0)

    def test_rapport_sans_resultats(self):
        # Le PV liste tous les étudiants de la classe, même sans notes publiées
        columns, data = execute(self._filtres())
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(row["student_name"], f"{self.student.nom} {self.student.prenom}")
        self.assertEqual(row["tci"], 0)
        self.assertEqual(row["tcc"], 0)
        self.assertEqual(row["mps"], 0)
        # Sans résultats, seules les colonnes statiques sont présentes
        noms = [c["fieldname"] for c in columns]
        self.assertIn("matricule", noms)
        self.assertIn("student_name", noms)
        self.assertIn("mps", noms)
        self.assertIn("mention", noms)
        self.assertNotIn(f"ue_{self.tu1.name}", noms)
