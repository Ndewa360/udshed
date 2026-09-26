# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests de la saisie des notes par « Type d'évaluation ».

L'interface propose désormais trois modes : « Contrôle continu (CC) »,
« Examen normal » et « Rattrapage ». Chaque mode ne manipule que les notes
de son type (une saisie de CC ne touche jamais aux notes d'examen et
réciproquement), les notes existantes sont mises à jour — jamais dupliquées —
et les codes d'anonymat (propres à chaque matière) relient l'examen saisi
au bon étudiant.

Scénarios exigés :
  - TEST 1 : interface CC seule, saisie d'une note, enregistrement, relecture
    et export (feuille de saisie PDF + export Excel limité au CC).
  - TEST 2 : interface Examen seule, codes d'anonymat, saisie avec les codes,
    rejet des codes erronés, et génération du PV existant (CC + examen).
- TEST 3 : le rattrapage continue de fonctionner (note retenue = MAX).
    - TEST 4 : bascule CC -> Examen -> Rattrapage -> CC sans perte ni mélange
      de données.
    - TEST 5 : la fiche de report (Examen) téléchargeable avec les codes
      d'anonymat pour que l'enseignant relève les notes.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api.saisie_notes import (
    TYPE_CC,
    TYPE_NORMALE,
    TYPE_RATTRAPAGE,
    _contexte_anonyme,
    _generer_codes_anonymes,
    _get_etudiants,
    charger_data,
    download_fiche_report_pdf,
    enregistrer_evaluations,
    enregistrer_rattrapage,
    export_modele_pdf,
    export_notes,
    generer_pdf,
    generer_pdf_cc,
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
)


class TestSaisieParType(IntegrationTestCase):

    def setUp(self):
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

        self.args = {
            "academic_year": self.academic_year.name,
            "semestre": "Semestre 1",
            "filiere": self.fos.name,
            "niveau": "BTS 1",
            "teaching_unit": self.tu.name,
        }

    # ------------------------------------------------------------------ #
    #  helpers
    # ------------------------------------------------------------------ #
    def _session(self, type_dexamen):
        sessions = frappe.db.get_all(
            "Session Examen",
            filters={
                "academic_year": self.academic_year.name,
                "semestre": "Semestre 1",
                "type_dexamen": type_dexamen,
            },
            pluck="name",
        )
        niveau = frappe.db.get_value(
            "Field of study Level", {"parent": self.fos.name, "level": "BTS 1"}, "name"
        )
        for name in sessions:
            if frappe.db.exists(
                "Session Examen Field of study Level",
                {"parent": name, "filiere": self.fos.name, "niveau": niveau},
            ):
                return name
        return None

    def _note(self, type_dexamen):
        session = self._session(type_dexamen)
        self.assertIsNotNone(session)
        name = frappe.db.get_value(
            "Session Examen Note",
            {
                "session_examen": session,
                "student": self.student.name,
                "teaching_unit": self.tu.name,
            },
            "name",
        )
        return frappe.get_doc("Session Examen Note", name) if name else None

    def _nb_notes(self, type_dexamen):
        session = self._session(type_dexamen)
        if not session:
            return 0
        return frappe.db.count(
            "Session Examen Note",
            {
                "session_examen": session,
                "student": self.student.name,
                "teaching_unit": self.tu.name,
            },
        )

    def _codes(self):
        students = charger_data(
            self.args["academic_year"],
            self.args["filiere"],
            self.args["niveau"],
            self.args["semestre"],
            self.args["teaching_unit"],
        )["students"]
        return _generer_codes_anonymes(
            students, _contexte_anonyme(self.args["teaching_unit"], TYPE_NORMALE)
        )

    def _sauver_cc(self, cc=None, cctp=None):
        return enregistrer_evaluations(
            self.args["academic_year"],
            self.args["filiere"],
            self.args["niveau"],
            self.args["semestre"],
            self.args["teaching_unit"],
            [{"student": self.student.name, "cc": cc, "note_cctp": cctp}],
            type_dexamen="CC",
        )

    def _sauver_examen(self, code, examen=None, examtp=None):
        return enregistrer_evaluations(
            self.args["academic_year"],
            self.args["filiere"],
            self.args["niveau"],
            self.args["semestre"],
            self.args["teaching_unit"],
            [{
                "student": self.student.name,
                "code_anonyme": code,
                "note_examen": examen,
                "note_examtp": examtp,
            }],
            type_dexamen="Examen",
        )

    # ------------------------------------------------------------------ #
    #  TEST 1 : Contrôle continu (CC), saisie / relecture / export
    # ------------------------------------------------------------------ #
    def test_cc_saisie_relecture_et_export(self):
        resultat = self._sauver_cc(cc=12, cctp=13)
        self.assertEqual(resultat["saved"], 1)
        self.assertEqual(resultat["type_dexamen"], "cc")

        note = self._note(TYPE_NORMALE)
        self.assertIsNotNone(note)
        self.assertEqual(float(note.note_cc_moyenne), 12.0)
        self.assertEqual(len(note.notes_cc), 1)
        self.assertEqual(float(note.notes_cc[0].note_cc), 12.0)
        self.assertEqual(note.cc_saisi, 1)
        self.assertEqual(note.cctp_saisi, 1)
        self.assertEqual(note.examen_saisi, 0, "aucun examen saisi en mode CC")
        self.assertEqual(note.examtp_saisi, 0)
        self.assertEqual(self._nb_notes(TYPE_NORMALE), 1)

        data = charger_data(
            self.args["academic_year"],
            self.args["filiere"],
            self.args["niveau"],
            self.args["semestre"],
            self.args["teaching_unit"],
        )
        ligne = next(l for l in data["lignes"] if l["student"] == self.student.name)
        self.assertEqual(ligne["cc"], 12.0)
        self.assertEqual(ligne["cctp"], 13.0)
        self.assertIsNone(ligne["examen"])

        # Feuille de saisie PDF du CC.
        with patch("udshed.api.saisie_notes._html_en_pdf", return_value=b"%PDF") as mock_pdf:
            export_modele_pdf(
                "CC",
                cc_columns=None,
                academic_year=self.args["academic_year"],
                filiere=self.args["filiere"],
                niveau=self.args["niveau"],
                semestre=self.args["semestre"],
                teaching_unit=self.args["teaching_unit"],
            )
        self.assertEqual(frappe.response["filecontent"], b"%PDF")
        self.assertTrue(frappe.response["filename"].endswith(".pdf"))
        self.assertIn("Modèle de saisie des notes — CC", mock_pdf.call_args[0][0])

        # Export Excel limité au CC : la valeur saisie est exportée.
        with patch("udshed.api.saisie_notes._repondre_xlsx") as mock_xlsx:
            export_notes(
                self.args["academic_year"],
                self.args["filiere"],
                self.args["niveau"],
                self.args["semestre"],
                self.args["teaching_unit"],
                "CC",
                cc_columns=None,
                anonyme=0,
            )
        rows = mock_xlsx.call_args[0][0]
        self.assertEqual(rows[0][-1], "Moyenne CC")
        self.assertEqual(rows[1][0], self.student.matricule)
        self.assertEqual(rows[1][-1], 12.0)

    # ------------------------------------------------------------------ #
    #  TEST 2 : Examen normal, codes d'anonymat + PV existant
    # ------------------------------------------------------------------ #
    def test_examen_codes_anonymat_et_pv(self):
        self._sauver_cc(cc=12, cctp=13)
        code = self._codes()[self.student.name]
        self.assertTrue(code.startswith("AN"))

        # Code d'anonymat erroné -> refus sans rien enregistrer.
        with self.assertRaises(frappe.ValidationError):
            self._sauver_examen("AN999", examen=15)
        self.assertEqual(self._nb_notes(TYPE_NORMALE), 1)

        # Code manquant -> refus.
        with self.assertRaises(frappe.ValidationError):
            self._sauver_examen(None, examen=15)

        # Code correct -> enregistrement, CC intact.
        resultat = self._sauver_examen(code, examen=15, examtp=14)
        self.assertEqual(resultat["saved"], 1)
        note = self._note(TYPE_NORMALE)
        self.assertEqual(float(note.note_examen), 15.0)
        self.assertEqual(float(note.note_examtp), 14.0)
        self.assertEqual(float(note.note_cc_moyenne), 12.0)
        self.assertEqual(self._nb_notes(TYPE_NORMALE), 1)

        data = charger_data(
            self.args["academic_year"],
            self.args["filiere"],
            self.args["niveau"],
            self.args["semestre"],
            self.args["teaching_unit"],
        )
        ligne = next(l for l in data["lignes"] if l["student"] == self.student.name)
        self.assertEqual(ligne["cc"], 12.0)
        self.assertEqual(ligne["examen"], 15.0)
        self.assertEqual(ligne["code_anonyme"], code)

        # PV existant (CC + examen) généré à partir des données enregistrées.
        with patch("udshed.api.saisie_notes._html_en_pdf", return_value=b"%PDF") as mock_pdf:
            generer_pdf(
                self.args["academic_year"],
                self.args["filiere"],
                self.args["niveau"],
                self.args["semestre"],
                self.args["teaching_unit"],
            )
        self.assertEqual(frappe.response["filecontent"], b"%PDF")
        html = mock_pdf.call_args[0][0]
        self.assertIn("PROCES VERBAL DE LA MATIERE", html)
        self.assertIn("12.0", html, "le CC saisi doit apparaître dans le PV")
        self.assertIn("15.0", html, "l'examen saisi doit apparaître dans le PV")

    # ------------------------------------------------------------------ #
    #  TEST 3 : le rattrapage continue de fonctionner
    # ------------------------------------------------------------------ #
    def test_rattrapage_utilise_cc_et_examen_normaux(self):
        self._sauver_cc(cc=12, cctp=13)
        self._sauver_examen(self._codes()[self.student.name], examen=10, examtp=9)

        resultat = enregistrer_rattrapage(
            self.args["academic_year"],
            self.args["filiere"],
            self.args["niveau"],
            self.args["semestre"],
            self.args["teaching_unit"],
            [{"student": self.student.name, "note_examen_rattrapage": 14}],
        )
        self.assertEqual(resultat["saved"], 1)

        rattrapage = self._note(TYPE_RATTRAPAGE)
        self.assertIsNotNone(rattrapage)
        self.assertEqual(float(rattrapage.note_examen_rattrapage), 14.0)
        self.assertEqual(float(rattrapage.note_examen), 10.0)  # initiale conservée
        self.assertEqual(float(rattrapage.note_examen_active), 14.0)  # MAX
        self.assertEqual(float(rattrapage.note_cc_moyenne), 12.0)  # CC copié
        self.assertEqual(self._nb_notes(TYPE_RATTRAPAGE), 1)

    # ------------------------------------------------------------------ #
    #  TEST 4 : bascule CC -> Examen -> Rattrapage -> CC sans perte/mélange
    # ------------------------------------------------------------------ #
    def test_bascule_entre_modes_sans_perte(self):
        code = self._codes()[self.student.name]

        # 1) CC
        self._sauver_cc(cc=12, cctp=13)
        # 2) Examen (via code) : ne touche pas au CC déjà saisi.
        self._sauver_examen(code, examen=15, examtp=14)
        note = self._note(TYPE_NORMALE)
        self.assertEqual(float(note.note_cc_moyenne), 12.0)
        self.assertEqual(float(note.note_examen), 15.0)
        # 3) Rattrapage : conserve l'examen initial, stocke le rattrapage.
        enregistrer_rattrapage(
            self.args["academic_year"],
            self.args["filiere"],
            self.args["niveau"],
            self.args["semestre"],
            self.args["teaching_unit"],
            [{"student": self.student.name, "note_examen_rattrapage": 17}],
        )
        # 4) Retour au CC : mise à jour du CC uniquement, examen et rattrapage intacts.
        self._sauver_cc(cc=11, cctp=10)

        self.assertEqual(self._nb_notes(TYPE_NORMALE), 1, "aucune duplication de note")
        self.assertEqual(self._nb_notes(TYPE_RATTRAPAGE), 1)

        note = self._note(TYPE_NORMALE)
        self.assertEqual(float(note.note_cc_moyenne), 11.0)
        self.assertEqual(float(note.note_cctp), 10.0)
        self.assertEqual(float(note.note_examen), 15.0)
        self.assertEqual(float(note.note_examtp), 14.0)

        rattrapage = self._note(TYPE_RATTRAPAGE)
        self.assertEqual(float(rattrapage.note_examen_rattrapage), 17.0)
        self.assertEqual(float(rattrapage.note_examen_active), 17.0)

        data = charger_data(
            self.args["academic_year"],
            self.args["filiere"],
            self.args["niveau"],
            self.args["semestre"],
            self.args["teaching_unit"],
        )
        ligne = next(l for l in data["lignes"] if l["student"] == self.student.name)
        self.assertEqual(ligne["cc"], 11.0)
        self.assertEqual(ligne["cctp"], 10.0)
        self.assertEqual(ligne["examen"], 15.0)
        self.assertEqual(ligne["examtp"], 14.0)

    def test_effacer_cc_en_mode_cc_ne_touche_pas_a_l_examen(self):
        code = self._codes()[self.student.name]
        self._sauver_cc(cc=12)
        self._sauver_examen(code, examen=15)

        # Effacement du CC dans le mode CC (cc vide) : l'examen reste intact.
        self._sauver_cc(cc=None, cctp=10)
        note = self._note(TYPE_NORMALE)
        self.assertEqual(len(note.notes_cc), 0)
        self.assertEqual(note.cc_saisi, 0)
        self.assertEqual(float(note.note_examen), 15.0)

    # ------------------------------------------------------------------ #
    #  TEST 5 : fiche de report vierge avec codes d'anonymat (Examen)
    # ------------------------------------------------------------------ #
    def test_fiche_report_vierge_avec_codes(self):
        with patch("udshed.api.saisie_notes._html_en_pdf", return_value=b"%PDF") as mock_pdf:
            download_fiche_report_pdf(
                self.args["academic_year"],
                self.args["filiere"],
                self.args["niveau"],
                self.args["semestre"],
                self.args["teaching_unit"],
            )
        self.assertEqual(frappe.response["filecontent"], b"%PDF")
        self.assertTrue(frappe.response["filename"].startswith("Fiche_report_examen_"))
        self.assertEqual(frappe.response["content_type"], "application/pdf")

        html = mock_pdf.call_args[0][0]
        self.assertIn("Fiche de report — Examen normal", html)
        for fragment in ["N°", "Code anonymat", "Matricule", "Nom", "Prénom", "Note /20"]:
            self.assertIn(fragment, html, "colonne manquante : " + fragment)
        code = self._codes()[self.student.name]
        self.assertIn(code, html, "le code d'anonymat de l'étudiant doit figurer")
        self.assertIn(self.student.matricule, html)
        self.assertIn(self.student.nom, html)

    def test_fiche_report_rattrapage_utilise_le_meme_template(self):
        # Le rattrapage reprend le même template (fiche d'anonymat) avec les
        # codes propres au type « Examen de rattrapage ».
        self._sauver_cc(cc=12, cctp=13)
        self._sauver_examen(self._codes()[self.student.name], examen=10, examtp=9)
        enregistrer_rattrapage(
            self.args["academic_year"],
            self.args["filiere"],
            self.args["niveau"],
            self.args["semestre"],
            self.args["teaching_unit"],
            [{"student": self.student.name, "note_examen_rattrapage": 14}],
        )

        with patch("udshed.api.saisie_notes._html_en_pdf", return_value=b"%PDF") as mock_pdf:
            download_fiche_report_pdf(
                self.args["academic_year"],
                self.args["filiere"],
                self.args["niveau"],
                self.args["semestre"],
                self.args["teaching_unit"],
                type_dexamen="Rattrapage",
            )
        self.assertEqual(frappe.response["filecontent"], b"%PDF")
        self.assertTrue(frappe.response["filename"].startswith("Fiche_report_rattrapage_"))
        self.assertEqual(frappe.response["content_type"], "application/pdf")

        html = mock_pdf.call_args[0][0]
        self.assertIn("Fiche de report — Rattrapage", html)
        self.assertIn("Examen de rattrapage", html)  # bandeau session
        for fragment in ["N°", "Code anonymat", "Matricule", "Nom", "Prénom", "Note /20"]:
            self.assertIn(fragment, html, "colonne manquante : " + fragment)
        codes_rt = _generer_codes_anonymes(
            _get_etudiants(
                self.args["academic_year"],
                self.args["filiere"],
                self.args["niveau"],
                self.args["teaching_unit"],
            ),
            _contexte_anonyme(self.args["teaching_unit"], TYPE_RATTRAPAGE),
        )
        self.assertIn(codes_rt[self.student.name], html)
        self.assertIn(self.student.matricule, html)

    # ------------------------------------------------------------------ #
    #  TEST 6 : en mode CC, « Télécharger PDF » ne contient que la note CC
    # ------------------------------------------------------------------ #
    def test_pdf_cc_contient_uniquement_la_note_de_cc(self):
        # Le mode CC ne doit télécharger que la note de contrôle continu :
        # les notes d'examen (même saisies) ne doivent jamais y apparaître.
        self._sauver_cc(cc=12, cctp=13)
        self._sauver_examen(self._codes()[self.student.name], examen=15, examtp=14)

        with patch("udshed.api.saisie_notes._html_en_pdf", return_value=b"%PDF") as mock_pdf:
            generer_pdf_cc(
                self.args["academic_year"],
                self.args["filiere"],
                self.args["niveau"],
                self.args["semestre"],
                self.args["teaching_unit"],
            )
        self.assertEqual(frappe.response["filecontent"], b"%PDF")
        self.assertTrue(frappe.response["filename"].startswith("Notes_CC_"))
        self.assertEqual(frappe.response["content_type"], "application/pdf")

        html = mock_pdf.call_args[0][0]
        self.assertIn("Notes de contrôle continu", html)
        self.assertIn("12.0", html, "la note de CC doit figurer")
        self.assertIn("13.0", html, "le CCTP doit figurer (composante CC)")
        self.assertNotIn("15.0", html, "la note d'examen ne doit jamais apparaître")
        self.assertNotIn("PROCES VERBAL DE LA MATIERE", html)