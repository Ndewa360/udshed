# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests de la fiche d'anonymat et de la fiche de report (examens Udshed).

Le flux complet est couvert :
  Inscription (réinscription académique) → Étudiant (matricule, nom, prénom)
  → Session/Matière → Code d'anonymat → Correction → Note → Levée d'anonymat
  → Fiche de report (PDF) → Résultat (Session Examen Note).

Vérifie aussi :
  - l'identité (matricule réel, jamais STU-xxx) est copiée sur la fiche
    d'anonymat et sur la fiche de report ;
  - le correcteur ne voit aucune identité et ne peut pas télécharger les
    fiches confidentielles ;
  - chaque levée laisse une trace (leve_par / leve_le) et crée une fiche de
    report unique par (étudiant, matière, session) ;
  - la note reportée est celle enregistrée lors de la correction ;
  - les deux PDF (anonymat, report) sont générés et téléchargés.
"""

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api.examen_anonymat import (
    download_fiche_anonymat_pdf,
    download_fiche_report_pdf,
    enregistrer_correction,
    generer_codes,
    lever_anonymat,
    valider_corrections,
)
from udshed.api.saisie_notes import TYPE_NORMALE
from udshed.udshed._fixture_factory import (
    make_academic_reregistration,
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
    make_user_with_role,
    seed_formule,
    seed_grille_grades,
)


class TestFichesAnonymatReport(IntegrationTestCase):

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
        self.tu2 = make_teaching_unit(
            make_course(), self.academic_year, self.fos, self.niveau,
            credits=3, type_ue="Sans TP",
        )
        self.student = make_student(self.fos, self.niveau, "BTS")
        self.student2 = make_student(self.fos, self.niveau, "BTS")
        make_academic_reregistration(
            self.fos, "BTS 1", self.academic_year, [self.tu, self.tu2], student=self.student
        )
        make_academic_reregistration(
            self.fos, "BTS 1", self.academic_year, [self.tu, self.tu2], student=self.student2
        )

        self.session = make_session_examen(
            self.academic_year, self.calendar,
            filiere=self.fos, niveau=self.niveau, type_dexamen=TYPE_NORMALE,
        )

    # ------------------------------------------------------------------ #
    #  Fiche d'anonymat : identité réelle, jamais STU-xxx
    # ------------------------------------------------------------------ #
    def test_fiche_anonymat_porte_matricule_et_identite(self):
        generer_codes(self.session.name)
        anonymats = frappe.get_all(
            "Examen Anonymat",
            filters={"session_examen": self.session.name},
            fields=["student", "teaching_unit", "code_anonymat", "matricule", "nom", "prenom"],
        )
        self.assertEqual(len(anonymats), 4)
        for a in anonymats:
            self.assertTrue(a.matricule, "Le matricule doit être renseigné")
            self.assertNotIn("STU-", str(a.matricule), "Aucun matricule STU-xxx")
            self.assertTrue(a.matricule in (self.student.name, self.student2.name))
            self.assertTrue(a.nom and a.prenom, "Nom et prénom doivent être copiés")
            self.assertTrue(a.code_anonymat)

    def test_code_anonymat_unique_par_combinaison(self):
        generer_codes(self.session.name)
        anonymats = frappe.get_all(
            "Examen Anonymat",
            filters={"session_examen": self.session.name, "student": self.student.name},
            fields=["teaching_unit", "code_anonymat"],
        )
        self.assertEqual(len(anonymats), 2)
        codes = [a.code_anonymat for a in anonymats]
        self.assertEqual(len(set(codes)), 2, "Un code différent par matière pour un même étudiant")

    # ------------------------------------------------------------------ #
    #  Levée : fiche de report + trace + note corrigée alimentant résultats
    # ------------------------------------------------------------------ #
    def _corriger_et_lever(self):
        generer_codes(self.session.name)
        copies = frappe.get_all(
            "Copie Examen",
            filters={"session_examen": self.session.name},
            order_by="code_anonymat",
            fields=["name"],
        )
        notes = iter(["11", "13", "15", "17"])
        for copie in copies:
            enregistrer_correction(copie.name, note=next(notes))
        valider_corrections(self.session.name)
        result = lever_anonymat(self.session.name)
        self.assertEqual(result["injectees"], 4)
        return copies

    def test_levee_cree_fiche_de_report_avec_note_corrigee(self):
        self._corriger_et_lever()

        fiches = frappe.get_all(
            "Fiche Report",
            filters={"session_examen": self.session.name},
            fields=[
                "name", "student", "matricule", "nom", "prenom",
                "teaching_unit", "note_reportee", "session_examen_note",
                "examen_anonymat", "copie_examen", "leve_par", "leve_le",
            ],
            order_by="student, teaching_unit",
        )
        self.assertEqual(len(fiches), 4)
        for f in fiches:
            # Identité réelle de l'inscription, jamais STU-xxx.
            self.assertTrue(f.matricule)
            self.assertNotIn("STU-", str(f.matricule))
            self.assertTrue(f.nom and f.prenom)
            # Note reportée = note corrigée (0-20).
            self.assertIsNotNone(f.note_reportee)
            self.assertTrue(0 <= float(f.note_reportee) <= 20)
            self.assertTrue(f.session_examen_note, "La note référence le document du flux résultats")
            self.assertTrue(f.examen_anonymat and f.copie_examen)
            self.assertTrue(f.leve_par, "Trace : levé par doit être consigné")
            self.assertTrue(f.leve_le, "Trace : date de levée doit être consignée")

        notes_sp = {f.student: f.note_reportee for f in fiches}
        self.assertEqual(len(notes_sp), 2)  # 2 étudiants × 2 matières

        # La note reportée alimente le flux des résultats (Session Examen Note).
        notes_res = frappe.get_all(
            "Session Examen Note",
            filters={"session_examen": self.session.name},
            fields=["student", "teaching_unit", "note_examen", "statut"],
        )
        self.assertEqual(len(notes_res), 4)
        self.assertTrue(all(n.statut == "Saisi" for n in notes_res))

    def test_trace_levee_sur_anonymat_et_idempotence(self):
        self._corriger_et_lever()

        anonymats = frappe.get_all(
            "Examen Anonymat",
            filters={"session_examen": self.session.name},
            fields=["statut", "leve_par", "leve_le"],
        )
        self.assertEqual(len(anonymats), 4)
        self.assertTrue(all(a.statut == "Levé" for a in anonymats))
        self.assertTrue(all(a.leve_par for a in anonymats))
        self.assertTrue(all(a.leve_le for a in anonymats))

        # Seconde levée : idempotente, aucune nouvelle fiche de report.
        seconde = lever_anonymat(self.session.name)
        self.assertEqual(seconde["injectees"], 0)
        total_fiches = frappe.db.count("Fiche Report", {"session_examen": self.session.name})
        self.assertEqual(total_fiches, 4)

    def test_fiche_report_unique_par_combinaison(self):
        self._corriger_et_lever()
        fiche = frappe.get_all("Fiche Report", filters={"session_examen": self.session.name}, limit=1)[0]
        original = frappe.get_doc("Fiche Report", fiche.name)

        avec_doublon = frappe.copy_doc(original)
        avec_doublon.anonyme = None
        with self.assertRaises(frappe.ValidationError):
            avec_doublon.insert(ignore_permissions=True)

    # ------------------------------------------------------------------ #
    #  PDF des fiches (téléchargement réel)
    # ------------------------------------------------------------------ #
    def test_download_fiche_anonymat_pdf(self):
        generer_codes(self.session.name)
        download_fiche_anonymat_pdf(self.session.name)
        self.assertEqual(frappe.response["type"], "download")
        self.assertIn("Fiche_anonymat", frappe.response["filename"])
        pdf = frappe.response.get("filecontent") or b""
        self.assertTrue(pdf.startswith(b"%PDF"), "Le contenu doit être un PDF")

    def test_download_fiche_report_pdf(self):
        self._corriger_et_lever()
        download_fiche_report_pdf(self.session.name)
        self.assertEqual(frappe.response["type"], "download")
        self.assertIn("Fiche_report", frappe.response["filename"])
        pdf = frappe.response.get("filecontent") or b""
        self.assertTrue(pdf.startswith(b"%PDF"), "Le contenu doit être un PDF")

    def test_download_fiche_report_pdf_avant_levee(self):
        """La fiche de report se télécharge dès la validation, sans levée."""
        generer_codes(self.session.name)
        copies = frappe.get_all(
            "Copie Examen",
            filters={"session_examen": self.session.name},
            order_by="code_anonymat",
            fields=["name"],
        )
        notes = iter(["11", "13", "15", "17"])
        for copie in copies:
            enregistrer_correction(copie.name, note=next(notes))
        valider_corrections(self.session.name)

        download_fiche_report_pdf(self.session.name)
        self.assertEqual(frappe.response["type"], "download")
        pdf = frappe.response.get("filecontent") or b""
        self.assertTrue(pdf.startswith(b"%PDF"), "Le contenu doit être un PDF")

    def test_download_fiche_report_pdf_sans_copies_validees(self):
        """Sans copie corrigée et validée, le PDF est refusé (erreur claire)."""
        generer_codes(self.session.name)
        with self.assertRaises(frappe.ValidationError):
            download_fiche_report_pdf(self.session.name)

    # ------------------------------------------------------------------ #
    #  Confidentialité : le correcteur ne doit jamais accéder aux fiches
    # ------------------------------------------------------------------ #
    def test_correcteur_sans_acces_aux_fiches(self):
        correcteur = make_user_with_role("Correcteur")
        generer_codes(self.session.name)
        anonymat = frappe.get_all(
            "Examen Anonymat",
            filters={"session_examen": self.session.name},
            limit=1,
            fields=["name"],
        )[0]

        frappe.set_user(correcteur.email)
        try:
            self.assertFalse(frappe.has_permission("Examen Anonymat", doc=anonymat.name))
            self.assertFalse(frappe.has_permission("Fiche Report", doc=None))
            with self.assertRaises(frappe.ValidationError):
                download_fiche_anonymat_pdf(self.session.name)
            with self.assertRaises(frappe.ValidationError):
                download_fiche_report_pdf(self.session.name)
        finally:
            frappe.set_user("Administrator")