# Copyright (c) 2026, Udshed and contributors
# For license information, please see license.txt

"""Tests du résultat d'UE (moyenne pondérée par les crédits).

Couvrent :
- la pondération par les crédits de la grille d'enseignement ;
- le grade / point repris de la grille officielle ;
- le déclenchement automatique dès la saisie, sans passer par « Publié » ;
- la meilleure note entre session normale et session de rattrapage ;
- l'absence de calcul partiel quand une matière manque ;
- l'idempotence, la re-saisie et le statut non modifiable à la main ;
- la cohérence des statistiques du PV d'UE.
"""

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api.proces_verbal import get_pv_ue_data
from udshed.api.resultat_ue import (
    calculer_resultat_ue,
    calculer_ue_etudiant,
    get_matieres_ue,
    recalculer_ue_depuis_note,
)
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

TYPE_RATTRAPAGE = "Examen de rattrapage"

# Formule 100 % Examen : note_pct = note_examen / 20 x 100. Cela permet de
# viser exactement les valeurs de la maquette (51, 67.5, 55) et d'avoir une
# seule combinaison à gérer.
COMPOSANTES_EXAMEN_SEUL = ["Examen"]


class TestResultatUE(IntegrationTestCase):
    """Résultat d'une UE : composition, pondération, validation, PV."""

    def setUp(self):
        seed_grille_grades()
        # 100 % Examen, seuils LMD : BTS 50, Master 60.
        seed_formule("BTS", COMPOSANTES_EXAMEN_SEUL, [100], seuil=50)
        seed_formule("Master", COMPOSANTES_EXAMEN_SEUL, [100], seuil=60)

        self.academic_year = make_academic_year()
        self.calendar = make_calendar_planing()
        self.faculty = make_faculty()
        self.teacher = make_teacher()
        self.fos = make_field_of_study(self.faculty, self.calendar, self.teacher)
        self.niveau = make_level(self.fos, level="BTS 1")

        # `Teaching Unit Value.code` et `Course.code` sont uniques, et la
        # transaction n'est annulée qu'en fin de classe : les codes portent
        # donc un suffixe unique, tout en gardant un préfixe lisible.
        self.ue_code = unique_code("UTI308")
        self.code_ang = unique_code("ANG302")
        self.code_eco = unique_code("ECO304")
        self.code_ges = unique_code("GES308")

        # Une UE de la grille d'enseignement et ses trois matières (3 crédits).
        self.ue = make_teaching_unit_value(self.academic_year, code=self.ue_code)
        self.tu1 = self._matiere(self.code_ang, credits=3)
        self.tu2 = self._matiere(self.code_eco, credits=3)
        self.tu3 = self._matiere(self.code_ges, credits=3)

        self.student = make_student(self.fos, self.niveau, cycle="BTS")
        make_academic_reregistration(
            self.fos, "BTS 1", self.academic_year, [self.tu1, self.tu2, self.tu3],
            student=self.student,
        )

        self.session = make_session_examen(
            self.academic_year, self.calendar, filiere=self.fos, niveau=self.niveau,
        )
        self.session_rattrapage = make_session_examen(
            self.academic_year, self.calendar, filiere=self.fos, niveau=self.niveau,
            type_dexamen=TYPE_RATTRAPAGE,
        )

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #
    def _matiere(self, code, credits=3, ue=None):
        return make_teaching_unit(
            make_course(code=code), self.academic_year, self.fos, self.niveau,
            credits=credits, unite_de_valeur=ue or self.ue,
        )

    def _saisir(self, teaching_unit, note_examen, session=None, statut="Publié"):
        """Saisit une note (l'insertion déclenche le calcul d'UE via on_update)."""
        return make_session_examen_note(
            session or self.session, self.student, teaching_unit,
            note_examen=note_examen, statut=statut,
        )

    def _saisir_rattrapage(self, teaching_unit, note, statut="Publié"):
        return make_session_examen_note(
            self.session_rattrapage, self.student, teaching_unit,
            note_examen_rattrapage=note, statut=statut,
        )

    def _calculer(self, ue=None, student=None):
        return calculer_resultat_ue(
            (student or self.student).name, (ue or self.ue).name,
            self.academic_year.name, "Semestre 1", self.fos.name, self.niveau.name,
        )

    def _resultat_ue(self, ue=None, student=None):
        return frappe.db.get_value(
            "Resultat UE",
            {
                "student": (student or self.student).name,
                "teaching_unit_value": (ue or self.ue).name,
                "academic_year": self.academic_year.name,
            },
            ["name", "note_ue_pct", "note_ue_20", "grade", "point", "statut",
             "seuil_validation", "total_credits", "credits_obtenus",
             "pct_validation", "n_matieres", "commentaire", "ue_code",
             "est_calculable"],
            as_dict=True,
        )

    def _pv(self, ue=None):
        return get_pv_ue_data(
            self.academic_year.name, self.fos.name, "BTS 1", "Semestre 1",
            (ue or self.ue).name,
        )

    def _nb_resultats(self, ue=None, student=None):
        """Nombre de `Resultat UE` du périmètre de ce test.

        La transaction est partagée par tous les tests de la classe : le comptage
        est donc filtré sur l'étudiant et l'UE du test, jamais global.
        """
        return frappe.db.count(
            "Resultat UE",
            {
                "student": (student or self.student).name,
                "teaching_unit_value": (ue or self.ue).name,
            },
        )

    # ------------------------------------------------------------------ #
    #  Composition de l'UE
    # ------------------------------------------------------------------ #
    def test_matieres_de_lue_viennent_de_la_grille(self):
        matieres = get_matieres_ue(self.ue.name, self.academic_year.name)
        self.assertEqual(len(matieres), 3)
        self.assertEqual(
            sorted(m["code"] for m in matieres),
            sorted([self.code_ang, self.code_eco, self.code_ges]),
        )
        self.assertEqual(sum(m["credits"] for m in matieres), 9)

    def test_matiere_sans_ue_ne_produit_rien(self):
        orpheline = make_teaching_unit(
            make_course(code=unique_code("HORS1")), self.academic_year, self.fos,
            self.niveau, credits=3,
        )
        self.assertIsNone(
            recalculer_ue_depuis_note(
                teaching_unit=orpheline.name,
                student=self.student.name,
                session_examen=self.session.name,
            )
        )
        self._saisir(orpheline, 15.0)
        self.assertEqual(self._nb_resultats(), 0)

    # ------------------------------------------------------------------ #
    #  Pondération par les crédits
    # ------------------------------------------------------------------ #
    def test_moyenne_credits_egaux(self):
        # 51 / 67.5 / 55 sur trois matières de 3 crédits -> (51+67.5+55)/3
        self._saisir(self.tu1, 10.2)
        self._saisir(self.tu2, 13.5)
        self._saisir(self.tu3, 11.0)

        self._calculer()

        res = self._resultat_ue()
        self.assertEqual(res.note_ue_pct, 57.83)
        self.assertEqual(res.note_ue_20, 11.57)
        self.assertEqual(res.est_calculable, 1)
        # Grille officielle : 11.57/20 -> C+ / 2.30
        self.assertEqual(res.grade, "C+")
        self.assertEqual(res.point, 2.3)
        self.assertEqual(res.statut, "Validé")
        self.assertEqual(res.seuil_validation, 50)
        self.assertEqual(res.total_credits, 9)
        self.assertEqual(res.credits_obtenus, 9)
        self.assertEqual(res.pct_validation, 100.0)
        self.assertEqual(res.n_matieres, 3)
        self.assertEqual(res.ue_code, self.ue_code)
        self.assertIsNone(res.commentaire)

    def test_moyenne_ponderee_credits_differents(self):
        """Des crédits différents changent le résultat : la pondération agit."""
        ue = make_teaching_unit_value(self.academic_year, code=unique_code("POND001"))
        t1 = self._matiere(unique_code("P1"), credits=1, ue=ue)
        t2 = self._matiere(unique_code("P2"), credits=2, ue=ue)
        t3 = self._matiere(unique_code("P3"), credits=3, ue=ue)
        # 50 / 60 / 70 avec des poids 1 / 2 / 3 -> (50 + 120 + 210) / 6
        self._saisir(t1, 10.0)
        self._saisir(t2, 12.0)
        self._saisir(t3, 14.0)

        self._calculer(ue=ue)

        res = self._resultat_ue(ue=ue)
        self.assertEqual(res.note_ue_pct, 63.33)
        self.assertEqual(res.grade, "B-")
        self.assertEqual(res.point, 2.7)
        self.assertEqual(res.total_credits, 6)
        self.assertEqual(res.credits_obtenus, 6)
        self.assertEqual(res.statut, "Validé")

    def test_credits_partiels_un_seul_matieres_sous_le_seuil(self):
        """``credits_obtenus`` ne compte que les matières validées."""
        ue = make_teaching_unit_value(self.academic_year, code=unique_code("PART01"))
        t1 = self._matiere(unique_code("Q1"), credits=2, ue=ue)
        t2 = self._matiere(unique_code("Q2"), credits=1, ue=ue)
        self._saisir(t1, 8.0)   # 40 % : non validé
        self._saisir(t2, 12.0)  # 60 % : validé

        self._calculer(ue=ue)

        res = self._resultat_ue(ue=ue)
        # (2 x 40 + 1 x 60) / 3
        self.assertEqual(res.note_ue_pct, 46.67)
        self.assertEqual(res.total_credits, 3)
        self.assertEqual(res.credits_obtenus, 1)
        self.assertEqual(res.pct_validation, 33.33)
        # La moyenne d'UE est sous le seuil -> UE non validée, mention retirée.
        self.assertEqual(res.statut, "Non Validé")
        self.assertEqual(res.grade, "C-")

    def test_note_saisie_vide_vaut_zero(self):
        """Règle métier : une note saisie mais vide vaut 0, et l'UE est délibérée.

        À ne pas confondre avec l'étudiant qui n'a *aucune* note (absent de la
        session) : celui-là reste « En attente », sans calcul
        (cf. `test_pv_ue_liste_les_etudiants_sans_note`).
        """
        for tu, note in ((self.tu1, 10.0), (self.tu2, 10.0), (self.tu3, None)):
            self._saisir(tu, note, statut="Saisi")

        resultat = self._calculer()
        self.assertEqual(resultat.est_calculable, 1)
        # (50 + 50 + 0) / 3
        self.assertEqual(resultat.note_ue_pct, 33.33)
        self.assertEqual(resultat.statut, "Non Validé")
        self.assertEqual(resultat.total_credits, 9)
        # Les deux matières à 50 % franchissent le seuil, pas la matière vide.
        self.assertEqual(resultat.credits_obtenus, 6)
        self.assertEqual(resultat.pct_validation, 66.67)

        res = self._resultat_ue()
        self.assertEqual(res.est_calculable, 1)
        self.assertEqual(res.statut, "Non Validé")
        # Une UE complète est délibérée : elle compte dans le taux de réussite.
        stats = self._pv()["statistiques"]
        self.assertEqual(stats["en_attente"], 0)
        self.assertEqual(stats["echecs"], 1)

    # ------------------------------------------------------------------ #
    #  Déclenchement à la saisie, sans publication
    # ------------------------------------------------------------------ #
    def test_calcul_declenche_a_la_saisie_sans_publier(self):
        self._saisir(self.tu1, 10.2, statut="Saisi")
        self._saisir(self.tu2, 13.5, statut="Saisi")
        # UE encore incomplète : la ligne existe, mais sans note calculable.
        incomplet = self._resultat_ue()
        self.assertEqual(incomplet.statut, "En attente")
        self.assertEqual(incomplet.est_calculable, 0)
        self.assertIn(self.code_ges, incomplet.commentaire)

        # La dernière note saisie déclenche le calcul, sans aucun appel à
        # `publier_session`.
        self._saisir(self.tu3, 11.0, statut="Saisi")

        res = self._resultat_ue()
        self.assertEqual(res.est_calculable, 1)
        self.assertEqual(res.note_ue_pct, 57.83)
        self.assertEqual(res.statut, "Validé")
        self.assertIsNone(res.commentaire)
        self.assertEqual(self._nb_resultats(), 1)

    def test_une_ue_complete_puis_repassee_en_attente(self):
        """Retirer une note fait repasser l'UE en attente (pas de division)."""
        for tu, note in ((self.tu1, 10.2), (self.tu2, 13.5), (self.tu3, 11.0)):
            self._saisir(tu, note)
        self.assertEqual(self._resultat_ue().note_ue_pct, 57.83)

        # GES308 repasse en brouillon -> la note n'est plus retenue.
        frappe.db.set_value(
            "Session Examen Note",
            {"student": self.student.name, "teaching_unit": self.tu3.name,
             "session_examen": self.session.name},
            "statut", "Brouillon",
        )
        self._calculer()

        res = self._resultat_ue()
        self.assertEqual(res.statut, "En attente")
        self.assertEqual(res.est_calculable, 0)
        # Le PV, lui, n'affiche aucune note : il lit le calcul, pas la colonne.
        self.assertIsNone(self._pv()["etudiants"][0]["note_ue_pct"])
        self.assertIn(self.code_ges, res.commentaire)

        # Régression : les colonnes numériques sont NOT NULL DEFAULT 0. Sans le
        # drapeau `est_calculable`, la relecture 0.0 faisait basculer l'UE en
        # « Non Validé » dès la sauvegarde suivante.
        doc = frappe.get_doc("Resultat UE", res.name)
        doc.save(ignore_permissions=True)
        self.assertEqual(self._resultat_ue().statut, "En attente")
        self.assertEqual(self._resultat_ue().est_calculable, 0)

    def test_note_validee_sans_publiee_compte_dans_le_calcul(self):
        """« Validé » (juste avant « Publié ») suffit à déclencher le calcul."""
        for tu, note in ((self.tu1, 10.2), (self.tu2, 13.5), (self.tu3, 11.0)):
            self._saisir(tu, note, statut="Validé")

        res = self._resultat_ue()
        self.assertEqual(res.note_ue_pct, 57.83)
        self.assertEqual(res.statut, "Validé")

        # Une note « Publié » ne change rien au résultat.
        frappe.db.set_value(
            "Session Examen Note",
            {"student": self.student.name, "session_examen": self.session.name},
            "statut", "Publié",
        )
        self._calculer()
        self.assertEqual(self._resultat_ue().note_ue_pct, 57.83)

    def test_statut_non_modifiable_a_la_main(self):
        """Le statut est redérivé à chaque sauvegarde."""
        for tu in (self.tu1, self.tu2, self.tu3):
            self._saisir(tu, 6.0)  # 30 % : sous le seuil BTS
        self._calculer()
        self.assertEqual(self._resultat_ue().statut, "Non Validé")

        doc = frappe.get_doc("Resultat UE", self._resultat_ue().name)
        doc.statut = "Validé"
        doc.save(ignore_permissions=True)

        doc = frappe.get_doc("Resultat UE", self._resultat_ue().name)
        self.assertEqual(doc.statut, "Non Validé")
        self.assertEqual(doc.statut_color, "red")

    # ------------------------------------------------------------------ #
    #  Rattrapage
    # ------------------------------------------------------------------ #
    def test_meilleure_note_entre_normale_et_rattrapage(self):
        # ANG302 : le rattrapage (75) est meilleur que la normale (40).
        self._saisir(self.tu1, 8.0)
        self._saisir_rattrapage(self.tu1, 15.0)
        # ECO304 : la normale (80) est meilleure que le rattrapage (25).
        self._saisir(self.tu2, 16.0)
        self._saisir_rattrapage(self.tu2, 5.0)
        # GES308 : pas de rattrapage.
        self._saisir(self.tu3, 11.0)

        self._calculer()

        doc = frappe.get_doc("Resultat UE", self._resultat_ue().name)
        retenues = {ligne.code: ligne for ligne in doc.table_matieres}
        self.assertEqual(doc.note_ue_pct, 70.0)  # (75 + 80 + 55) / 3
        self.assertEqual(retenues[self.code_ang].note_pct, 75.0)
        self.assertEqual(retenues[self.code_ang].est_rattrapage, 1)
        self.assertEqual(retenues[self.code_eco].note_pct, 80.0)
        self.assertEqual(retenues[self.code_eco].est_rattrapage, 0)
        self.assertEqual(retenues[self.code_ges].note_pct, 55.0)
        self.assertEqual(retenues[self.code_ges].est_rattrapage, 0)

    def test_rattrapage_seul_complète_lue(self):
        """Une UE dont toutes les notes viennent du rattrapage se calcule."""
        self._saisir_rattrapage(self.tu1, 10.0)
        self._saisir_rattrapage(self.tu2, 12.0)
        self._saisir_rattrapage(self.tu3, 14.0)

        self._calculer()

        res = self._resultat_ue()
        self.assertEqual(res.note_ue_pct, 60.0)
        self.assertEqual(res.statut, "Validé")

    # ------------------------------------------------------------------ #
    #  Seuils de validation
    # ------------------------------------------------------------------ #
    def test_seuil_master_60(self):
        # `Student.determiner_cycle()` dérive le cycle de `niveau_actuel` :
        # un étudiant Master doit donc être inscrit en « Master 1 ».
        etudiant = make_student(
            self.fos, self.niveau, cycle="Master", niveau_actuel="Master 1"
        )
        for tu in (self.tu1, self.tu2, self.tu3):
            make_session_examen_note(
                self.session, etudiant, tu, note_examen=10.0, statut="Saisi"
            )

        self._calculer(student=etudiant)

        res = self._resultat_ue(student=etudiant)
        self.assertEqual(res.note_ue_pct, 50.0)
        self.assertEqual(res.seuil_validation, 60)
        self.assertEqual(res.statut, "Non Validé")

    def test_meme_note_validee_selon_le_cycle(self):
        """55 % est validée en BTS (seuil 50) mais pas en Master (seuil 60)."""
        bts = self.student
        master = make_student(
            self.fos, self.niveau, cycle="Master", niveau_actuel="Master 1"
        )

        for etudiant in (bts, master):
            for tu in (self.tu1, self.tu2, self.tu3):
                make_session_examen_note(
                    self.session, etudiant, tu, note_examen=11.0, statut="Saisi"
                )
            self._calculer(student=etudiant)

        # 11/20 = 55 %.
        self.assertEqual(self._resultat_ue(student=bts).note_ue_pct, 55.0)
        self.assertEqual(self._resultat_ue(student=bts).statut, "Validé")
        self.assertEqual(self._resultat_ue(student=master).statut, "Non Validé")

    # ------------------------------------------------------------------ #
    #  Idempotence et re-saisie
    # ------------------------------------------------------------------ #
    def test_idempotence_une_seule_ligne(self):
        for tu, note in ((self.tu1, 10.2), (self.tu2, 13.5), (self.tu3, 11.0)):
            self._saisir(tu, note)

        self._calculer()
        self._calculer()
        self._calculer()

        self.assertEqual(
            frappe.db.count(
                "Resultat UE",
                {
                    "student": self.student.name,
                    "teaching_unit_value": self.ue.name,
                    "academic_year": self.academic_year.name,
                },
            ),
            1,
        )
        self.assertEqual(self._resultat_ue().note_ue_pct, 57.83)

    def test_resaisie_met_a_jour_le_resultat(self):
        for tu, note in ((self.tu1, 10.2), (self.tu2, 13.5), (self.tu3, 11.0)):
            self._saisir(tu, note)
        self.assertEqual(self._resultat_ue().note_ue_pct, 57.83)

        # Le professeur corrige GES308 : la note d'UE suit automatiquement.
        note = frappe.get_doc(
            "Session Examen Note",
            {"student": self.student.name, "teaching_unit": self.tu3.name,
             "session_examen": self.session.name},
        )
        note.note_examen = 18.0
        note.save(ignore_permissions=True)  # on_update -> recalcul de l'UE

        res = self._resultat_ue()
        self.assertEqual(res.note_ue_pct, 69.5)  # (51 + 67.5 + 90) / 3
        self.assertEqual(res.grade, "B")
        self.assertEqual(res.statut, "Validé")
        self.assertEqual(self._nb_resultats(), 1)

    # ------------------------------------------------------------------ #
    #  PV d'UE
    # ------------------------------------------------------------------ #
    def test_pv_ue_une_colonne_par_matiere(self):
        for tu, note in ((self.tu1, 10.2), (self.tu2, 13.5), (self.tu3, 11.0)):
            self._saisir(tu, note)

        data = self._pv()

        self.assertEqual(data["ue"]["code"], self.ue_code)
        self.assertEqual(data["ue"]["n_matieres"], 3)
        self.assertEqual(data["ue"]["credits"], 9)
        self.assertEqual(len(data["matieres"]), 3)
        self.assertEqual(len(data["etudiants"]), 1)

        ligne = data["etudiants"][0]
        self.assertEqual(ligne["matricule"], self.student.matricule)
        self.assertEqual(ligne["note_ue_pct"], 57.83)
        self.assertEqual(ligne["grade"], "C+")
        self.assertEqual(ligne["point"], 2.3)
        self.assertEqual(ligne["statut"], "Validé")
        self.assertEqual(ligne["notes"][self.tu1.name]["note_pct"], 51.0)
        self.assertEqual(ligne["notes"][self.tu2.name]["note_pct"], 67.5)
        self.assertEqual(ligne["notes"][self.tu3.name]["note_pct"], 55.0)

        stats = data["statistiques"]
        self.assertEqual(stats["inscrits"], 1)
        self.assertEqual(stats["admis"], 1)
        self.assertEqual(stats["echecs"], 0)
        self.assertEqual(stats["en_attente"], 0)
        self.assertEqual(stats["taux_reussite"], 100.0)

    def test_pv_ue_liste_les_etudiants_sans_note(self):
        """L'étudiant sans note est listé, avec une ligne vide."""
        data = self._pv()

        self.assertEqual(len(data["etudiants"]), 1)
        ligne = data["etudiants"][0]
        self.assertIsNone(ligne["note_ue_pct"])
        self.assertEqual(ligne["statut"], "En attente")
        # Les trois matières sont bien présentes, sans note.
        self.assertEqual(len(ligne["notes"]), 3)
        self.assertTrue(all(n["note_pct"] is None for n in ligne["notes"].values()))

        stats = data["statistiques"]
        self.assertEqual(stats["inscrits"], 1)
        self.assertEqual(stats["en_attente"], 1)
        self.assertEqual(stats["admis"], 0)
        self.assertEqual(stats["echecs"], 0)
        # Aucun étudiant délibéré -> pas de division par zéro.
        self.assertEqual(stats["taux_reussite"], 0.0)
        self.assertEqual(
            stats["admis"] + stats["echecs"] + stats["en_attente"], stats["inscrits"]
        )

    def test_pv_ue_taux_ignore_les_en_attente(self):
        """Le taux de réussite porte sur les étudiants délibérés seulement."""
        for tu, note in ((self.tu1, 18.0), (self.tu2, 18.0)):
            self._saisir(tu, note)  # l'étudiant inscrit reste « En attente »

        delibre = make_student(self.fos, self.niveau, cycle="BTS")
        make_academic_reregistration(
            self.fos, "BTS 1", self.academic_year, [self.tu1, self.tu2, self.tu3],
            student=delibre,
        )
        for tu, note in ((self.tu1, 16.0), (self.tu2, 16.0), (self.tu3, 16.0)):
            make_session_examen_note(
                self.session, delibre, tu, note_examen=note, statut="Saisi"
            )

        stats = self._pv()["statistiques"]
        self.assertEqual(stats["inscrits"], 2)
        self.assertEqual(stats["en_attente"], 1)
        self.assertEqual(stats["admis"], 1)
        # 1 admis sur 1 délibéré, pas 1 sur 2.
        self.assertEqual(stats["taux_reussite"], 100.0)

    def test_pv_ue_vide_si_ue_sans_matiere(self):
        ue_vide = make_teaching_unit_value(self.academic_year, code=unique_code("VIDE01"))
        data = self._pv(ue=ue_vide)
        self.assertEqual(data["matieres"], [])
        self.assertEqual(data["etudiants"], [])
        self.assertIsNone(data["ue"])

    def test_calcul_ue_etudiant_pur_sans_ecriture(self):
        for tu, note in ((self.tu1, 10.2), (self.tu2, 13.5), (self.tu3, 11.0)):
            self._saisir(tu, note)

        resultat = calculer_ue_etudiant(
            self.student.name, self.ue.name, self.academic_year.name, "Semestre 1",
            self.fos.name, self.niveau.name,
        )
        self.assertEqual(resultat["note_ue_pct"], 57.83)
        self.assertEqual(resultat["note_ue_20"], 11.57)
        self.assertEqual(resultat["statut"], "Validé")
        self.assertEqual(resultat["grade"], "C+")
        self.assertEqual(len(resultat["lignes"]), 3)
        self.assertTrue(all(ligne["valide"] for ligne in resultat["lignes"]))
        # UE sans matière -> None, sans écriture ni erreur.
        ue_vide = make_teaching_unit_value(self.academic_year, code=unique_code("VIDE02"))
        self.assertIsNone(
            calculer_ue_etudiant(
                self.student.name, ue_vide.name, self.academic_year.name, "Semestre 1",
                self.fos.name, self.niveau.name,
            )
        )
