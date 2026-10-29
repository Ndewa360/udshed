# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests de la grille officielle des grades et des points UDSHED.

Cas couverts :
  - chaque intervalle de la grille (§1) ;
  - chaque valeur limite du cahier des charges (§8) ;
  - conversion note /20 -> pourcentage (§9) ;
  - grade, point et profil académique par tranche (§10, §11) ;
  - indépendance des crédits LMD (§12) ;
  - cohérence entre moteur, statut UE et échelle exposée (§17).
"""

import frappe
from frappe.tests import IntegrationTestCase

from udshed.grade_calculation import (
    determiner_statut_ue,
    get_grade_info,
    get_grade_scale,
    get_grille_grades,
)

# Grille officielle : (min/20, grade attendu, point attendu, mention attendue)
OFFICIELLE = [
    (16.00, "A", 4.00, "Excellent / Très Honorable avec Félicitations du Jury"),
    (15.00, "A-", 3.70, "Très Bien / Très Honorable"),
    (14.00, "B+", 3.30, "Très Bien"),
    (13.00, "B", 3.00, "Assez Bien"),
    (12.00, "B-", 2.70, "Assez Bien"),
    (11.00, "C+", 2.30, "Passable"),
    (10.00, "C", 2.00, "Passable"),
    (9.00, "C-", 1.70, "Insuffisant"),
    (8.00, "D+", 1.30, "Insuffisant"),
    (7.00, "D", 1.00, "Insuffisant"),
    (6.00, "E", 0.00, "Échec"),
    (0.00, "F", 0.00, "Échec"),
]

# Valeurs limites obligatoires du cahier des charges (§8)
LIMITES = [
    (5.99, "F", 0.00),
    (6.00, "E", 0.00),
    (6.99, "E", 0.00),
    (7.00, "D", 1.00),
    (7.99, "D", 1.00),
    (8.00, "D+", 1.30),
    (8.99, "D+", 1.30),
    (9.00, "C-", 1.70),
    (9.99, "C-", 1.70),
    (10.00, "C", 2.00),
    (10.99, "C", 2.00),
    (11.00, "C+", 2.30),
    (11.99, "C+", 2.30),
    (12.00, "B-", 2.70),
    (12.99, "B-", 2.70),
    (13.00, "B", 3.00),
    (13.99, "B", 3.00),
    (14.00, "B+", 3.30),
    (14.99, "B+", 3.30),
    (15.00, "A-", 3.70),
    (15.99, "A-", 3.70),
    (16.00, "A", 4.00),
    (20.00, "A", 4.00),
]


class TestGrilleOfficielle(IntegrationTestCase):
    """La grille en base est la grille officielle et s'applique partout."""

    def test_23_limites_du_cahier_des_charges(self):
        for note, grade_attendu, point_attendu in LIMITES:
            info = get_grade_info(note)
            self.assertIsNotNone(info, f"Aucun grade pour {note}")
            self.assertEqual(
                info["grade"], grade_attendu,
                f"Note {note} : attendu {grade_attendu}, obtenu {info['grade']}",
            )
            self.assertAlmostEqual(
                float(info["point"]), point_attendu, places=2,
                msg=f"Note {note} : point attendu {point_attendu}, obtenu {info['point']}",
            )

    def test_chaque_intervalle_et_mention(self):
        for min20, grade, point, mention in OFFICIELLE:
            note = min20 + 0.50 if min20 < 16 else 18.0
            info = get_grade_info(note)
            self.assertEqual(info["grade"], grade)
            self.assertAlmostEqual(float(info["point"]), point, places=2)
            self.assertEqual(info["mention"], mention)

    def test_conversion_note_vers_pourcentage(self):
        for note, pct in [(10, 50), (15, 75), (16, 80), (14.5, 72.5), (12.8, 64)]:
            info = get_grade_info(note)
            self.assertEqual(info["note_20"], round(note, 2))
            self.assertEqual(info["note_pct"], pct)

    def test_regles_equivalentes_sur_les_deux_echelles(self):
        """Une même note donne le même grade sur /20 ou sur /100 (§9)."""
        for note in [5.99, 8.35, 10, 12.64, 14.02, 16]:
            via20 = get_grade_info(note, echelle=20)
            via100 = get_grade_info(note * 5, echelle=100)
            self.assertEqual(via20["grade"], via100["grade"])
            self.assertAlmostEqual(float(via20["point"]), float(via100["point"]), places=2)

    def test_exemple_officiel_du_cahier(self):
        """14,50/20 -> 72,50 % -> B+ -> 3,30 -> Très Bien."""
        info = get_grade_info(14.50)
        self.assertEqual(info["grade"], "B+")
        self.assertEqual(info["note_pct"], 72.5)
        self.assertAlmostEqual(float(info["point"]), 3.30, places=2)
        self.assertEqual(info["mention"], "Très Bien")

    def test_statut_ue_cohérent_avec_grille(self):
        for note, grade_attendu, point_attendu in LIMITES:
            statut = determiner_statut_ue(note, cycle="Licence")
            self.assertEqual(statut["grade"], grade_attendu, f"Note {note}")
            self.assertAlmostEqual(float(statut["point"]), point_attendu, places=2)
            # Validation indépendante de la grille : seuil Licence = 50 %
            self.assertEqual(statut["valide"], note >= 10)

    def test_capitalisation_seulement_a_partir_de_10(self):
        for note in [10, 12, 16]:
            info = get_grade_info(note)
            self.assertTrue(info["capitalise"])
        for note in [0, 6.5, 9.99]:
            info = get_grade_info(note)
            self.assertFalse(info["capitalise"])

    def test_grille_en_base_est_la_grille_officielle(self):
        lignes = get_grille_grades()
        self.assertEqual(len(lignes), len(OFFICIELLE))
        grades_base = {r.grade: round(float(r.note_min_20), 2) for r in lignes}
        for min20, grade, _point, _mention in OFFICIELLE:
            self.assertEqual(grades_base.get(grade), min20)

    def test_echelle_exposee_triee_et_complete(self):
        scale = get_grade_scale()
        self.assertEqual(len(scale), len(OFFICIELLE))
        mins = [g["note_min_20"] for g in scale]
        self.assertEqual(mins, sorted(mins, reverse=True))
        for g in scale:
            self.assertIn({"grade": g["grade"], "point": g["point"]},
                          [{"grade": gr, "point": pt} for _, gr, pt, _m in OFFICIELLE])

    def test_notes_hors_domaine(self):
        self.assertIsNone(get_grade_info(None))
        self.assertIsNone(get_grade_info(-1))
