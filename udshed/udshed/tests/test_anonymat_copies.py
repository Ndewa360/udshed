# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests du système d'anonymat des copies d'examen.

Deux documents : « Examen Anonymat » (lien confidentiel étudiant ↔ code) et
« Copie Examen » (correction sans identité). Le rôle « Correcteur » corrige
sans jamais voir la correspondance ; la levée d'anonymat (rôle responsable)
injecte les notes dans le flux existant de validation/publication.

Cas couverts :
  - génération : code unique par (étudiant, session, matière), codes
    différents entre matières et entre sessions, idempotence ;
  - le correcteur ne voit aucune identité (API et permissions) ;
  - correction, validation puis levée : les notes arrivent en « Saisi »
    et les liens passent en « Levé » ; seconde levée sans effet ;
  - l'absent / copie manquante n'injecte aucune note ;
  - la validation est bloquée s'il reste des copies non corrigées ;
  - les notes hors bornes sont refusées ;
  - la levée d'anonymat est refusée hors rôle responsable.
"""

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api.examen_anonymat import (
    charger_copies,
    enregistrer_correction,
    generer_codes,
    lever_anonymat,
    valider_corrections,
    _verifier_correcteur,
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


class TestAnonymatCopies(IntegrationTestCase):

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

    def generer(self):
        return generer_codes(self.session.name)

    # ------------------------------------------------------------------ #
    #  Génération
    # ------------------------------------------------------------------ #
    def test_generation_codes_uniques_par_etudiant_et_matiere(self):
        result = self.generer()
        self.assertEqual(result["genere"], 4)  # 2 étudiants × 2 matières

        anonymats = frappe.get_all(
            "Examen Anonymat",
            filters={"session_examen": self.session.name},
            fields=["student", "teaching_unit", "code_anonymat"],
            order_by="student, teaching_unit",
        )
        self.assertEqual(len(anonymats), 4)

        codes = [a.code_anonymat for a in anonymats]
        self.assertEqual(len(set(codes)), 4, "Les codes doivent être uniques")

        par_etudiant = {}
        for a in anonymats:
            par_etudiant.setdefault(a.student, set()).add(a.teaching_unit)
            self.assertTrue(a.student in (self.student.name, self.student2.name))

        # Même étudiant → code différent pour chaque matière.
        for etudiant in (self.student.name, self.student2.name):
            codes_etudiant = [
                a.code_anonymat for a in anonymats if a.student == etudiant
            ]
            self.assertEqual(
                len(set(codes_etudiant)), len(codes_etudiant),
                "Un étudiant doit avoir un code différent par matière",
            )

        copies = frappe.get_all(
            "Copie Examen",
            filters={"session_examen": self.session.name},
            fields=["name", "code_anonymat", "examen_anonymat", "statut_correction"],
        )
        self.assertEqual(len(copies), 4)
        self.assertTrue(all(c.statut_correction == "En attente" for c in copies))

    def test_codes_differents_entre_sessions(self):
        self.generer()
        session2 = make_session_examen(
            self.academic_year, self.calendar,
            filiere=self.fos, niveau=self.niveau, type_dexamen=TYPE_NORMALE,
        )
        generer_codes(session2.name)

        codes1 = {
            a.code_anonymat
            for a in frappe.get_all(
                "Examen Anonymat",
                filters={"session_examen": self.session.name},
                fields=["code_anonymat"],
            )
        }
        codes2 = {
            a.code_anonymat
            for a in frappe.get_all(
                "Examen Anonymat",
                filters={"session_examen": session2.name},
                fields=["code_anonymat"],
            )
        }
        self.assertFalse(codes1 & codes2, "Aucun code ne doit être réutilisé entre sessions")

    def test_generation_idempotente(self):
        self.generer()
        result = self.generer()
        self.assertEqual(result["genere"], 0)
        total = frappe.db.count("Examen Anonymat", {"session_examen": self.session.name})
        self.assertEqual(total, 4)

    # ------------------------------------------------------------------ #
    #  Confidentialité pour le correcteur
    # ------------------------------------------------------------------ #
    def test_correcteur_ne_voit_pas_identite(self):
        correcteur = make_user_with_role("Correcteur")
        self.generer()
        copie = frappe.get_all(
            "Copie Examen",
            filters={"session_examen": self.session.name},
            limit=1,
        )[0]
        anonymat = frappe.db.get_value("Copie Examen", copie.name, "examen_anonymat")

        frappe.set_user(correcteur.email)
        try:
            # Permissions réelles des doctypes.
            self.assertTrue(frappe.has_permission("Copie Examen", doc=copie.name))
            self.assertFalse(frappe.has_permission("Examen Anonymat", doc=anonymat))

            # L'API de correction ne remonte aucune identité.
            data = charger_copies(self.session.name)
            self.assertEqual(len(data["copies"]), 4)
            for c in data["copies"]:
                self.assertNotIn("student", c)
                self.assertNotIn("nom", c)
                self.assertNotIn("examen_anonymat", c)

            # Levée d'anonymat interdite pour un simple correcteur.
            with self.assertRaises(frappe.ValidationError):
                lever_anonymat(self.session.name)
        finally:
            frappe.set_user("Administrator")

    def test_correcteur_peut_corriger(self):
        correcteur = make_user_with_role("Correcteur")
        self.generer()
        copie = frappe.get_all(
            "Copie Examen",
            filters={"session_examen": self.session.name},
            limit=1,
        )[0]

        frappe.set_user(correcteur.email)
        try:
            result = enregistrer_correction(copie.name, note="14.5", observation="RAS")
            self.assertEqual(result["statut_correction"], "Corrigée")
            updated = frappe.get_doc("Copie Examen", copie.name)
            self.assertEqual(float(updated.note_examen), 14.5)
            self.assertEqual(updated.corrige_par, correcteur.email)
        finally:
            frappe.set_user("Administrator")

    def test_accuse_absent_peut_corriger_sans_note(self):
        self.generer()
        copie = frappe.get_all(
            "Copie Examen",
            filters={"session_examen": self.session.name},
            limit=1,
        )[0]
        result = enregistrer_correction(copie.name, absent="1")
        self.assertEqual(result["statut_correction"], "Copie manquante")
        doc = frappe.get_doc("Copie Examen", copie.name)
        self.assertEqual(doc.absent, 1)
        self.assertEqual(doc.statut_correction, "Copie manquante")

    # ------------------------------------------------------------------ #
    #  Validation et levée
    # ------------------------------------------------------------------ #
    def test_validation_bloquee_si_copies_en_attente(self):
        self.generer()
        copies = frappe.get_all(
            "Copie Examen",
            filters={"session_examen": self.session.name},
            order_by="code_anonymat",
        )
        enregistrer_correction(copies[0].name, note="12")
        with self.assertRaises(frappe.ValidationError):
            valider_corrections(self.session.name)

    def test_flux_complet_correction_validation_levee(self):
        self.generer()
        copies = frappe.get_all(
            "Copie Examen",
            filters={"session_examen": self.session.name},
            order_by="code_anonymat",
            fields=["name", "code_anonymat", "examen_anonymat"],
        )
        # Contre-mesure : corriger les quatre copies.
        notes = iter(["11", "13", "15", "17"])
        for copie in copies:
            enregistrer_correction(copie.name, note=next(notes))

        validees = valider_corrections(self.session.name)
        self.assertEqual(validees["validees"], 4)

        levees = lever_anonymat(self.session.name)
        self.assertEqual(levees["injectees"], 4)
        self.assertEqual(levees["levees"], 4)

        notes_frappe = frappe.get_all(
            "Session Examen Note",
            filters={"session_examen": self.session.name},
            fields=["student", "teaching_unit", "note_examen", "statut"],
        )
        self.assertEqual(len(notes_frappe), 4)
        self.assertTrue(all(n.statut == "Saisi" for n in notes_frappe))
        self.assertTrue(all(n.note_examen in (11.0, 13.0, 15.0, 17.0) for n in notes_frappe))

        restants = frappe.get_all(
            "Examen Anonymat",
            filters={"session_examen": self.session.name, "statut": "Généré"},
            pluck="name",
        )
        self.assertEqual(len(restants), 0)

        # Idempotence : une seconde levée n'injecte plus rien.
        seconde = lever_anonymat(self.session.name)
        self.assertEqual(seconde["injectees"], 0)
        self.assertEqual(seconde["levees"], 0)

    def test_copie_manquante_non_injectee(self):
        self.generer()
        copies = frappe.get_all(
            "Copie Examen",
            filters={"session_examen": self.session.name},
            order_by="code_anonymat",
            fields=["name"],
        )
        # Deux absents, deux corrigés.
        enregistrer_correction(copies[0].name, absent="1")
        enregistrer_correction(copies[1].name, absent="1")
        enregistrer_correction(copies[2].name, note="9")
        enregistrer_correction(copies[3].name, note="10")

        valider_corrections(self.session.name)
        levees = lever_anonymat(self.session.name)
        self.assertEqual(levees["injectees"], 2)

        notes = frappe.get_all(
            "Session Examen Note",
            filters={"session_examen": self.session.name},
            fields=["student", "note_examen"],
        )
        self.assertEqual(len(notes), 2)
        self.assertTrue(all(n.note_examen is not None for n in notes))

    def test_notes_hors_bornes_refusees(self):
        self.generer()
        copie = frappe.get_all(
            "Copie Examen",
            filters={"session_examen": self.session.name},
            limit=1,
        )[0]
        with self.assertRaises(frappe.ValidationError):
            enregistrer_correction(copie.name, note="25")
        with self.assertRaises(frappe.ValidationError):
            enregistrer_correction(copie.name, note="-1")
        with self.assertRaises(frappe.ValidationError):
            enregistrer_correction(copie.name, note=None)

    def test_levee_refusee_hors_role_responsable(self):
        correcteur = make_user_with_role("Correcteur")
        _verifier_correcteur()
        self.generer()
        copie = frappe.get_all(
            "Copie Examen",
            filters={"session_examen": self.session.name},
            limit=1,
        )[0]
        enregistrer_correction(copie.name, note="12")

        frappe.set_user(correcteur.email)
        try:
            with self.assertRaises(frappe.ValidationError):
                lever_anonymat(self.session.name)
            with self.assertRaises(frappe.ValidationError):
                valider_corrections(self.session.name)
        finally:
            frappe.set_user("Administrator")