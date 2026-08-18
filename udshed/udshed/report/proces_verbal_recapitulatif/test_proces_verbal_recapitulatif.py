# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from udshed.udshed._fixture_factory import (
    make_academic_year,
    make_academic_reregistration,
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
)
from udshed.udshed.report.proces_verbal_recapitulatif.proces_verbal_recapitulatif import (
    execute,
)


class TestProcesVerbalRecapitulatif(IntegrationTestCase):
    """Tests du Script Report « Proces Verbal Recapitulatif » (PV de Classe).

    Le rapport s'appuie sur les données du procès-verbal (session normale),
    produites par ``udshed.api.proces_verbal.get_proces_verbal_data`` :
    réinscriptions validées, notes publiées, bilan MPS / MPC / Statut.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.formula = seed_grade_formula("BTS", 30, 50, 20, seuil=50)
        seed_grille_grades()

    def setUp(self):
        self.academic_year = make_academic_year()
        self.calendar = make_calendar_planing()
        self.faculty = make_faculty()
        self.teacher = make_teacher()
        self.fos = make_field_of_study(self.faculty, self.calendar, self.teacher)
        self.niveau = make_level(self.fos, level="BTS 1")

        self.course1 = make_course()
        self.tu1 = make_teaching_unit(
            self.course1, self.academic_year, self.fos, self.niveau,
            credits=3, type_ue="Avec TP",
        )
        self.course2 = make_course()
        self.tu2 = make_teaching_unit(
            self.course2, self.academic_year, self.fos, self.niveau,
            credits=3, type_ue="Avec TP",
        )

        # Étudiant réinscrit (Validée) et inscrit aux deux UE du semestre
        self.student = make_student(self.fos, self.niveau, cycle="BTS")
        make_academic_reregistration(
            self.fos, "BTS 1", self.academic_year, [self.tu1, self.tu2],
            student=self.student,
        )

        self.session1 = make_session_examen(
            self.academic_year, self.calendar,
            filiere=self.fos, niveau=self.niveau,
        )
        self.session2 = make_session_examen(
            self.academic_year, self.calendar,
            filiere=self.fos, niveau=self.niveau,
        )

    def _filtres(self):
        return {
            "academic_year": self.academic_year.name,
            "semestre": "Semestre 1",
            "filiere": self.fos.name,
            "niveau": "BTS 1",
        }

    def _produire_notes(self):
        """Note publiée (session normale) par UE : tu1 validée, tu2 non validée."""
        make_session_examen_note(
            self.session1, self.student, self.tu1, note_cc=16, note_examen=18,
        )
        make_session_examen_note(
            self.session2, self.student, self.tu2, note_cc=6, note_examen=6,
        )

    def test_filtres_obligatoires(self):
        with self.assertRaises(frappe.ValidationError):
            execute({"academic_year": self.academic_year.name, "semestre": "Semestre 1"})

    def test_rapport_retourne_colonnes_ue_et_lignes(self):
        self._produire_notes()

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
        self.assertIn("statut", noms)
        self.assertNotIn("mention", noms)

        # Trois colonnes par UE du semestre
        for ue in (self.tu1, self.tu2):
            prefix = f"ue_{ue.name}"
            for suffix in ("_note", "_grade", "_point"):
                self.assertIn(prefix + suffix, noms)

        # Une ligne par étudiant réinscrit
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(row["num"], 1)
        self.assertEqual(row["matricule"], self.student.matricule)
        self.assertEqual(row["student_name"], f"{self.student.nom} {self.student.prenom}")

        # Notes / grades / points (CC 30 %, Examen 50 %, TP 0 % si absent)
        self.assertEqual(row[f"ue_{self.tu1.name}_note"], 69.0)
        self.assertEqual(row[f"ue_{self.tu1.name}_grade"], "C")
        self.assertEqual(row[f"ue_{self.tu1.name}_point"], 2.0)
        self.assertEqual(row[f"ue_{self.tu1.name}_non_valide"], 0)
        self.assertEqual(row[f"ue_{self.tu2.name}_note"], 24.0)
        self.assertEqual(row[f"ue_{self.tu2.name}_grade"], "F")
        self.assertEqual(row[f"ue_{self.tu2.name}_point"], 0.0)
        self.assertEqual(row[f"ue_{self.tu2.name}_non_valide"], 1)

        # Synthèse : TCI = 6 crédits, TCC = 3 (une seule UE validée),
        # MPS = (3×2 + 3×0) / 6 = 1.0 ; pas de Resultat Semestre -> MPC None
        self.assertEqual(row["tci"], 6)
        self.assertEqual(row["tcc"], 3)
        self.assertEqual(row["pct_validation"], 50.0)
        self.assertEqual(row["mps"], 1.0)
        self.assertIsNone(row["mpc"])
        self.assertEqual(row["statut"], "Ajourné")

    def test_rapport_sans_resultats(self):
        # Le PV liste tous les étudiants de la classe, même sans notes publiées
        columns, data = execute(self._filtres())
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(row["student_name"], f"{self.student.nom} {self.student.prenom}")
        self.assertEqual(row["tci"], 6)
        self.assertEqual(row["tcc"], 0)
        self.assertEqual(row["pct_validation"], 0.0)
        self.assertEqual(row["mps"], 0)
        self.assertEqual(row["statut"], "En attente")

        # Les colonnes UE restent présentes, avec des valeurs vides
        noms = [c["fieldname"] for c in columns]
        self.assertIn(f"ue_{self.tu1.name}_note", noms)
        self.assertIn(f"ue_{self.tu2.name}_note", noms)
        self.assertIsNone(row[f"ue_{self.tu1.name}_note"])
        self.assertEqual(row[f"ue_{self.tu1.name}_grade"], "")
        self.assertIsNone(row[f"ue_{self.tu1.name}_point"])