# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests du moteur de calcul des formules (Grade Formula) et du grade_calculation.

Cas couverts :
  - 1 à 10 : calcul de la note UE selon les composantes et compositions ;
  - arrondi, moyennes CC, seuils par cycle, crédits indépendants ;
  - validations : total 100 %, composition interne 100 %, unicité par cycle.
"""

import frappe
from frappe.tests import IntegrationTestCase

from udshed.grade_calculation import (
    SEUILS_DEFAUT,
    appliquer_arrondi,
    calculer_moyenne_cc,
    calculer_note_ue,
    combinaison_formule,
    combinaison_type_ue,
    est_valide,
    get_active_formula,
    get_formula,
    get_seuil_validation,
    get_student_cycle,
    is_formule_complete,
    rendre_apercu,
)
from udshed.udshed._fixture_factory import _next, seed_formule, seed_grade_formula

CC = "Controle Continu(CC)"
EXAMEN = "Examen"
TP = "Travaux Pratique (TP)"


class TestCalculNoteUE(IntegrationTestCase):
    """Cas 1 à 10 : calcul de la note finale selon la formule."""

    def _formule(self, composantes, composition=None, cycle="Licence", seuil=50):
        doc = frappe.new_doc("Grade Formula")
        doc.name = _next("FORMULE-TEST")
        doc.cycle = cycle
        doc.active = 0
        doc.seuil_validation = seuil
        doc.methode_arrondi = "Au plus proche"
        doc.methode_calcul_cc = "Moyenne arithmétique"
        doc.nb_meilleures_notes_cc = 2
        for c, p in composantes:
            doc.append("components", {"composante": c, "pourcentage": p})
        for parent, rows in (composition or {}).items():
            for c, p in rows:
                doc.append(
                    "composition",
                    {"composante_parent": parent, "composante": c, "pourcentage": p},
                )
        doc.insert(ignore_permissions=True)
        return doc

    def _note(self, formula, ctx):
        note, pct = calculer_note_ue(ctx, formula)
        return note, pct

    def test_1_cc_seul(self):
        formula = self._formule([(CC, 100)])
        note, pct = self._note(formula, {CC: 14})
        self.assertEqual(note, 14.0)
        self.assertEqual(pct, 70.0)

    def test_2_examen_seul(self):
        formula = self._formule([(EXAMEN, 100)])
        note, pct = self._note(formula, {EXAMEN: 12})
        self.assertEqual(note, 12.0)
        self.assertEqual(pct, 60.0)

    def test_3_tp_seul(self):
        formula = self._formule([(TP, 100)])
        note, pct = self._note(formula, {TP: 15})
        self.assertEqual(note, 15.0)
        self.assertEqual(pct, 75.0)

    def test_4_cc_examen(self):
        formula = self._formule([(CC, 40), (EXAMEN, 60)])
        note, pct = self._note(formula, {CC: 10, EXAMEN: 12})
        self.assertEqual(note, 11.2)
        self.assertEqual(pct, 56.0)

    def test_5_cc_tp(self):
        formula = self._formule([(CC, 40), (TP, 60)])
        note, pct = self._note(formula, {CC: 10, TP: 15})
        self.assertEqual(note, 13.0)
        self.assertEqual(pct, 65.0)

    def test_6_examen_tp(self):
        formula = self._formule([(EXAMEN, 60), (TP, 40)])
        note, pct = self._note(formula, {EXAMEN: 12, TP: 15})
        self.assertEqual(note, 13.2)
        self.assertEqual(pct, 66.0)

    def test_7_cc_examen_tp(self):
        formula = self._formule([(CC, 30), (EXAMEN, 50), (TP, 20)])
        note, pct = self._note(formula, {CC: 16, EXAMEN: 18, TP: 14})
        self.assertEqual(note, 16.6)
        self.assertEqual(pct, 83.0)

    def test_8_composition_tp_dans_cc(self):
        formula = self._formule([(CC, 100)], composition={CC: [(CC, 70), (TP, 30)]})
        note, pct = self._note(formula, {CC: 12, TP: 8})
        self.assertEqual(note, 10.8)
        self.assertEqual(pct, 54.0)

    def test_9_composition_tp_dans_examen(self):
        formula = self._formule([(EXAMEN, 100)], composition={EXAMEN: [(EXAMEN, 70), (TP, 30)]})
        note, pct = self._note(formula, {EXAMEN: 12, TP: 8})
        self.assertEqual(note, 10.8)
        self.assertEqual(pct, 54.0)

    def test_10_composition_examen_cc_tp(self):
        formula = self._formule([(EXAMEN, 100)], composition={EXAMEN: [(CC, 50), (TP, 50)]})
        note, pct = self._note(formula, {CC: 12, TP: 8})
        self.assertEqual(note, 10.0)
        self.assertEqual(pct, 50.0)

    def test_composante_manquante_egale_zero(self):
        """Une composante absente vaut 0 (le calcul ne plante pas)."""
        formula = self._formule([(CC, 50), (EXAMEN, 50)])
        note, pct = self._note(formula, {CC: 10})
        self.assertEqual(note, 5.0)
        self.assertEqual(pct, 25.0)


class TestArrondiEtMoyennes(IntegrationTestCase):
    """Arrondis et méthodes de calcul des moyennes CC."""

    def test_arrondi_au_plus_proche(self):
        self.assertEqual(appliquer_arrondi(12.345), round(12.345, 2))

    def test_arrondi_au_superieur(self):
        self.assertEqual(appliquer_arrondi(12.341, "Au supérieur"), 12.35)

    def test_arrondi_a_l_inferieur(self):
        self.assertEqual(appliquer_arrondi(12.349, "À l'inférieur"), 12.34)

    def test_moyenne_arithmetique(self):
        self.assertEqual(calculer_moyenne_cc([10, 12, 14], "Moyenne arithmétique"), 12.0)

    def test_moyenne_n_meilleures(self):
        self.assertEqual(
            calculer_moyenne_cc([10, 12, 14], "Moyenne des N meilleures notes", nombre_min=2),
            13.0,
        )

    def test_notes_insuffisantes(self):
        with self.assertRaises(frappe.ValidationError):
            calculer_moyenne_cc([10], "Moyenne arithmétique", nombre_min=2)


class TestSeuilsEtValidation(IntegrationTestCase):
    """Seuils de validation par cycle (cas 13) et validations de formule (21-23)."""

    def test_seuils_par_cycle(self):
        for cycle, seuil in SEUILS_DEFAUT.items():
            with self.subTest(cycle=cycle):
                seed_grade_formula(cycle, 30, 50, 20)
                self.assertEqual(get_seuil_validation(cycle), seuil)

    def test_est_valide_licence(self):
        self.assertTrue(est_valide(10, "Licence"))
        self.assertFalse(est_valide(9.9, "Licence"))

    def test_est_valide_master(self):
        self.assertTrue(est_valide(12, "Master"))
        self.assertFalse(est_valide(11.9, "Master"))

    def test_student_sans_cycle_repli_licence(self):
        self.assertEqual(get_student_cycle(None), "Licence")
        self.assertEqual(get_student_cycle("STUDENT-INTROUVABLE"), "Licence")

    def test_21_plusieurs_formules_actives_par_cycle(self):
        seed_grade_formula("Licence", 30, 50, 20)
        doc = frappe.new_doc("Grade Formula")
        doc.name = _next("FORMULE-TEST")
        doc.cycle = "Licence"
        doc.active = 1
        doc.seuil_validation = 50
        doc.methode_arrondi = "Au plus proche"
        doc.append("components", {"composante": CC, "pourcentage": 100})
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.combinaison, CC)

    def test_21b_meme_combinaison_active_rejetee(self):
        seed_grade_formula("Licence", 30, 50, 20)
        doc = frappe.new_doc("Grade Formula")
        doc.name = _next("FORMULE-TEST")
        doc.cycle = "Licence"
        doc.active = 1
        doc.seuil_validation = 50
        doc.methode_arrondi = "Au plus proche"
        doc.append("components", {"composante": CC, "pourcentage": 30})
        doc.append("components", {"composante": EXAMEN, "pourcentage": 50})
        doc.append("components", {"composante": TP, "pourcentage": 20})
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_22_total_formule_doit_faire_100(self):
        doc = frappe.new_doc("Grade Formula")
        doc.name = _next("FORMULE-TEST")
        doc.cycle = "Licence"
        doc.active = 1
        doc.seuil_validation = 50
        doc.append("components", {"composante": CC, "pourcentage": 30})
        doc.append("components", {"composante": EXAMEN, "pourcentage": 50})
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_23_composition_interne_doit_faire_100(self):
        doc = frappe.new_doc("Grade Formula")
        doc.name = _next("FORMULE-TEST")
        doc.cycle = "Licence"
        doc.active = 1
        doc.seuil_validation = 50
        doc.append("components", {"composante": CC, "pourcentage": 100})
        doc.append("composition", {"composante_parent": CC, "composante": CC, "pourcentage": 70})
        doc.append("composition", {"composante_parent": CC, "composante": TP, "pourcentage": 20})
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_composante_inconnue_rejetee(self):
        doc = frappe.new_doc("Grade Formula")
        doc.name = _next("FORMULE-TEST")
        doc.cycle = "Licence"
        doc.active = 1
        doc.seuil_validation = 50
        doc.append("components", {"composante": CC, "pourcentage": 50})
        doc.append("components", {"composante": "Inconnue", "pourcentage": 50})
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_double_comptabilisation_rejetee(self):
        doc = frappe.new_doc("Grade Formula")
        doc.name = _next("FORMULE-TEST")
        doc.cycle = "Licence"
        doc.active = 1
        doc.seuil_validation = 50
        doc.append("components", {"composante": CC, "pourcentage": 50})
        doc.append("components", {"composante": EXAMEN, "pourcentage": 50})
        doc.append("composition", {"composante_parent": EXAMEN, "composante": CC, "pourcentage": 40})
        doc.append("composition", {"composante_parent": EXAMEN, "composante": TP, "pourcentage": 60})
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_formule_sans_composante_rejetee(self):
        doc = frappe.new_doc("Grade Formula")
        doc.name = _next("FORMULE-TEST")
        doc.cycle = "Licence"
        doc.active = 1
        doc.seuil_validation = 50
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)


class TestApercuEtCompletude(IntegrationTestCase):
    """Aperçu lisible de la formule et complétude."""

    def test_rendre_apercu(self):
        formula = seed_grade_formula("BTS", 30, 50, 20)
        apercu = rendre_apercu(formula)
        self.assertIn(
            "Note du cours = Controle Continu(CC) (30%) + Examen (50%) + Travaux Pratique (TP) (20%)",
            apercu,
        )

    def test_rendre_apercu_composition(self):
        doc = frappe.new_doc("Grade Formula")
        doc.name = _next("FORMULE-TEST")
        doc.cycle = "Licence"
        doc.active = 0
        doc.seuil_validation = 50
        doc.methode_arrondi = "Au plus proche"
        doc.append("components", {"composante": CC, "pourcentage": 100})
        doc.append("composition", {"composante_parent": CC, "composante": CC, "pourcentage": 70})
        doc.append("composition", {"composante_parent": CC, "composante": TP, "pourcentage": 30})
        doc.insert(ignore_permissions=True)
        apercu = rendre_apercu(doc)
        self.assertIn(
            "Controle Continu(CC) = Controle Continu(CC) (70%) + Travaux Pratique (TP) (30%)",
            apercu,
        )

    def test_is_formule_complete(self):
        formula = seed_grade_formula("BTS", 30, 50, 20)
        self.assertFalse(is_formule_complete(formula, {CC: 16, EXAMEN: 18}))
        self.assertTrue(
            is_formule_complete(formula, {CC: 16, EXAMEN: 18, TP: 14})
        )


class TestCombinaisonEtSelection(IntegrationTestCase):
    """Combinaison d'évaluations et sélection automatique des formules."""

    def test_combinaison_formule(self):
        doc = frappe.new_doc("Grade Formula")
        doc.name = _next("FORMULE-TEST")
        doc.cycle = "Licence"
        doc.active = 0
        doc.seuil_validation = 50
        doc.append("components", {"composante": EXAMEN, "pourcentage": 60})
        doc.append("components", {"composante": CC, "pourcentage": 40})
        doc.insert(ignore_permissions=True)
        self.assertEqual(
            combinaison_formule(doc), "Controle Continu(CC) + Examen"
        )

    def test_combinaison_type_ue(self):
        self.assertEqual(
            combinaison_type_ue("Sans TP"), "Controle Continu(CC) + Examen"
        )
        self.assertEqual(
            combinaison_type_ue("Avec TP"),
            "Controle Continu(CC) + Examen + Travaux Pratique (TP)",
        )
        self.assertEqual(combinaison_type_ue("Stage SMSB"), "Examen + Rapport")

    def test_selection_automatique_par_combinaison(self):
        seed_formule("Licence", [CC, EXAMEN], [40, 60])
        seed_formule("Licence", [CC, EXAMEN, TP], [30, 50, 20])
        seed_formule("Licence", [EXAMEN, "Rapport"], [70, 30])

        sans_tp = get_formula("Licence", combinaison_type_ue("Sans TP"))
        self.assertIsNotNone(sans_tp)
        self.assertEqual(combinaison_formule(sans_tp), "Controle Continu(CC) + Examen")

        avec_tp = get_formula("Licence", combinaison_type_ue("Avec TP"))
        self.assertEqual(
            combinaison_formule(avec_tp),
            "Controle Continu(CC) + Examen + Travaux Pratique (TP)",
        )

        stage = get_formula("Licence", combinaison_type_ue("Stage SMSB"))
        self.assertEqual(combinaison_formule(stage), "Examen + Rapport")

    def test_aucune_formule_pour_combinaison_manquante(self):
        self.assertIsNone(get_formula("Master", combinaison_type_ue("Stage SMSB")))
        with self.assertRaises(frappe.ValidationError):
            get_active_formula("Master", combinaison_type_ue("Stage SMSB"))
