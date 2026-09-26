# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests de l'anonymisation de la Saisie des notes (examen / rattrapage).

Pendant les évaluations (examen, rattrapage), l'identité des étudiants ne
doit pas être visible : la page, les exports et la feuille de saisie PDF
utilisent des codes stables (AN001, AN002, …). Il n'existe pas un code pour
toutes les matières : chaque UE et chaque type d'examen (examen normal et
rattrapage) porte son propre jeu de codes. Le CC reste nominatif et le PV
officiel (generer_pdf) reste nominatif.

Cas couverts :
  - charger_data expose un code anonyme stable par étudiant ;
  - le code anonyme diffère d'une matière à l'autre et de l'examen au
    rattrapage (per contextes) ;
  - la feuille de saisie PDF est anonymisée quand ``anonyme`` est actif ;
  - sans le drapeau, le modèle PDF reste nominatif ;
  - les exports Excel (évaluations unifiées et notes de session)
    sont anonymisés ; les cellules Nom / Prénom sont vidées ;
  - le PV officiel (generer_pdf) reste nominatif.
"""

import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch

from udshed.api.saisie_notes import (
    _contexte_anonyme,
    _generer_codes_anonymes,
    charger_data,
    export_evaluations,
    export_modele_pdf,
    export_notes,
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
    seed_grille_grades,
)

TYPE_RATTRAPAGE = "Rattrapage"


class TestAnonymisationSaisie(IntegrationTestCase):

    def setUp(self):
        seed_grille_grades()
        setting = frappe.get_single("Udshed Setting")
        setting.exiger_programmation = 0
        setting.save(ignore_permissions=True)
        seed_formule("BTS", ["Controle Continu(CC)", "Examen"], [40, 60])

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
        self.student2 = make_student(self.fos, self.niveau, "BTS")
        make_academic_reregistration(
            self.fos, "BTS 1", self.academic_year, [self.tu], student=self.student
        )
        make_academic_reregistration(
            self.fos, "BTS 1", self.academic_year, [self.tu], student=self.student2
        )

        self.args = {
            "academic_year": self.academic_year.name,
            "semestre": "Semestre 1",
            "filiere": self.fos.name,
            "niveau": "BTS 1",
            "teaching_unit": self.tu.name,
        }

    # ------------------------------------------------------------------ #
    #  Codes anonymes
    # ------------------------------------------------------------------ #
    def test_charger_data_expose_un_code_anonyme_stable(self):
        data = charger_data(**self.args)
        lignes = data["lignes"]
        self.assertEqual(len(lignes), 2)

        codes = [l["code_anonyme"] for l in lignes]
        self.assertEqual(
            sorted(codes), ["AN001", "AN002"], "codes séquentiels et stables"
        )

        # Un code anonyme ne doit jamais coïncider avec l'identité réelle.
        for ligne in lignes:
            self.assertNotEqual(ligne["code_anonyme"], ligne["matricule"])
            self.assertTrue(ligne["code_anonyme"].startswith("AN"))

    def test_generer_codes_anonymes_a_cle_student(self):
        students = [
            {"student": "E1", "matricule": "MAT-2"},
            {"student": "E2", "matricule": "MAT-1"},
        ]
        codes = _generer_codes_anonymes(students)
        self.assertEqual(codes["E1"], "AN001")
        self.assertEqual(codes["E2"], "AN002")

    def test_codes_anonymes_propres_a_chaque_matiere(self):
        """Un code anonyme par (UE, type d'examen) — pas un code pour tous."""
        students = [
            {"student": "E1", "matricule": "MAT-2"},
            {"student": "E2", "matricule": "MAT-1"},
            {"student": "E3", "matricule": "MAT-3"},
        ]
        examen_tu1 = _generer_codes_anonymes(
            students, _contexte_anonyme("TU-1", "Examen")
        )
        examen_tu2 = _generer_codes_anonymes(
            students, _contexte_anonyme("TU-2", "Examen")
        )
        rattrapage_tu1 = _generer_codes_anonymes(
            students, _contexte_anonyme("TU-1", "Rattrapage")
        )

        for codes in (examen_tu1, examen_tu2, rattrapage_tu1):
            self.assertEqual(
                sorted(codes.values()), ["AN001", "AN002", "AN003"],
                "chaque jeu de codes couvre bien tous les étudiants",
            )

        self.assertNotEqual(
            examen_tu1, examen_tu2, "le code anonyme doit différer entre deux matières"
        )
        self.assertNotEqual(
            examen_tu1, rattrapage_tu1, "examen normal et rattrapage : jeux de codes distincts"
        )
        self.assertTrue(
            any(examen_tu1[s["student"]] != examen_tu2[s["student"]] for s in students),
            "au moins un étudiant change de code d'une matière à l'autre",
        )

    def test_lignes_exposent_les_codes_examen_et_rattrapage(self):
        """Chaque ligne porte un code examen et un code rattrapage stables."""
        data = charger_data(**self.args)
        ligne = data["lignes"][0]
        self.assertTrue(ligne["code_anonyme"].startswith("AN"))
        self.assertTrue(ligne["code_anonyme_rattrapage"].startswith("AN"))

        set_examen = {l["code_anonyme"] for l in data["lignes"]}
        set_rattrapage = {l["code_anonyme_rattrapage"] for l in data["lignes"]}
        self.assertEqual(set_examen, {"AN001", "AN002"})
        self.assertEqual(set_rattrapage, {"AN001", "AN002"})

        # Reproductibles entre deux chargements (stabilité par contexte).
        data2 = charger_data(**self.args)
        codes1 = [(l["code_anonyme"], l["code_anonyme_rattrapage"]) for l in data["lignes"]]
        codes2 = [(l["code_anonyme"], l["code_anonyme_rattrapage"]) for l in data2["lignes"]]
        self.assertEqual(codes1, codes2)

    # ------------------------------------------------------------------ #
    #  Feuille de saisie PDF
    # ------------------------------------------------------------------ #
    def test_export_modele_pdf_anonyme(self):
        with patch("udshed.api.saisie_notes._html_en_pdf", return_value=b"%PDF") as mock_pdf:
            export_modele_pdf(
                "Examen",
                academic_year=self.args["academic_year"],
                filiere=self.args["filiere"],
                niveau=self.args["niveau"],
                semestre=self.args["semestre"],
                teaching_unit=self.args["teaching_unit"],
                anonyme=1,
            )
        html = mock_pdf.call_args[0][0]
        self.assertIn("AN001", html)
        self.assertIn("AN002", html)
        self.assertNotIn(self.student.matricule, html)
        self.assertNotIn(self.student2.matricule, html)
        self.assertNotIn(self.student.nom, html)
        self.assertNotIn(self.student.prenom, html)
        self.assertNotIn(self.student2.nom, html)
        self.assertNotIn(self.student2.prenom, html)

    def test_export_modele_pdf_toujours_anonyme(self):
        # La feuille de saisie utilise toujours le code d'anonymat : plus de
        # colonnes Matricule / Nom / Prénom, seuls restent le code, le crédit
        # et les colonnes de notes.
        with patch("udshed.api.saisie_notes._html_en_pdf", return_value=b"%PDF") as mock_pdf:
            export_modele_pdf(
                "Examen",
                academic_year=self.args["academic_year"],
                filiere=self.args["filiere"],
                niveau=self.args["niveau"],
                semestre=self.args["semestre"],
                teaching_unit=self.args["teaching_unit"],
            )
        html = mock_pdf.call_args[0][0]
        self.assertIn("AN001", html)
        self.assertIn("AN002", html)
        for fragment in ["Code d&apos;anonymat", "Crédit", "Note d&apos;examen"]:
            self.assertIn(fragment, html, "colonne attendue : " + fragment)
        for absent in ["Matricule", "Nom", "Prénom", self.student.matricule,
                       self.student.nom, self.student.prenom,
                       self.student2.matricule, self.student2.nom]:
            self.assertNotIn(absent, html, "élément à ne pas afficher : " + str(absent))

        # Filigrane du logo présent comme sur les autres documents (PV, fiches).
        self.assertIn("watermark", html)

    # ------------------------------------------------------------------ #
    #  Exports Excel
    # ------------------------------------------------------------------ #
    def test_export_evaluations_anonyme(self):
        with patch("udshed.api.saisie_notes._repondre_xlsx") as mock_xlsx:
            export_evaluations(
                self.args["academic_year"],
                self.args["filiere"],
                self.args["niveau"],
                self.args["semestre"],
                self.args["teaching_unit"],
                anonyme=1,
            )
        rows = mock_xlsx.call_args[0][0]
        self.assertEqual(rows[0][0], "Matricule")
        self.assertEqual(
            sorted([rows[1][0], rows[2][0]]),
            ["AN001", "AN002"],
            "identité remplacée par le code",
        )
        for ligne in rows[1:3]:
            self.assertEqual(ligne[1:3], ["", ""], "Nom / Prénom vidés pour tous")

    def test_export_evaluations_nominatif_par_defaut(self):
        with patch("udshed.api.saisie_notes._repondre_xlsx") as mock_xlsx:
            export_evaluations(
                self.args["academic_year"],
                self.args["filiere"],
                self.args["niveau"],
                self.args["semestre"],
                self.args["teaching_unit"],
            )
        rows = mock_xlsx.call_args[0][0]
        self.assertEqual(rows[1][0], self.student.matricule)
        self.assertEqual(rows[1][1], self.student.nom)

    def test_export_notes_rattrapage_anonyme(self):
        with patch("udshed.api.saisie_notes._repondre_xlsx") as mock_xlsx:
            export_notes(
                self.args["academic_year"],
                self.args["filiere"],
                self.args["niveau"],
                self.args["semestre"],
                self.args["teaching_unit"],
                TYPE_RATTRAPAGE,
                anonyme=1,
            )
        rows = mock_xlsx.call_args[0][0]
        self.assertEqual(rows[0][0], "Matricule")
        self.assertEqual(
            sorted([rows[1][0], rows[2][0]]),
            ["AN001", "AN002"],
            "identité remplacée par le code",
        )
        for ligne in rows[1:3]:
            self.assertEqual(ligne[1:3], ["", ""], "Nom / Prénom vidés pour tous")

    # ------------------------------------------------------------------ #
    #  PV officiel : toujours nominatif
    # ------------------------------------------------------------------ #
    def test_generer_pdf_du_pv_reste_nominatif(self):
        from udshed.api.saisie_notes import _sauvegarder_examen

        _sauvegarder_examen(
            self.args,
            [{"student": self.student.name, "note_examen": 14}],
        )
        with patch("udshed.api.saisie_notes._html_en_pdf", return_value=b"%PDF") as mock_pdf:
            generer_pdf(
                self.args["academic_year"],
                self.args["filiere"],
                self.args["niveau"],
                self.args["semestre"],
                self.args["teaching_unit"],
            )
        html = mock_pdf.call_args[0][0]
        self.assertIn(self.student.matricule, html)
        self.assertNotIn("AN001", html)