# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests de l'anonymisation de la Saisie des notes (examen / rattrapage).

Pendant les évaluations (examen, rattrapage), l'identité des étudiants ne
doit pas être visible : la page, les exports et la feuille de saisie PDF
utilisent le code d'anonymat de la fiche d'anonymat, au format AN0001,
AN0002, … (numérotation séquentiele globale, aucun autre format n'existe).
Il n'existe pas un code pour toutes les matières : chaque UE et chaque type
d'examen (examen normal et rattrapage) porte son propre code. Le CC reste
nominatif et le PV officiel (generer_pdf) reste nominatif.

Cas couverts :
  - charger_data expose le code de la fiche d'anonymat de chaque étudiant ;
  - aucun code n'est inventé quand la fiche d'anonymat n'existe pas ;
  - le format AN0001 est le seul accepté, l'ancien format est refusé ;
  - le code diffère d'une matière à l'autre et de l'examen au rattrapage ;
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
    TYPE_NORMALE,
    TYPE_RATTRAPAGE as TYPE_RATTRAPAGE_MOTEUR,
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
    make_session_examen,
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

    def _generer_codes(self, type_dexamen=TYPE_NORMALE):
        """Génère les codes d'une session et renvoie {student: code}.

        Les codes ne sont plus calculés par la saisie : ils sont portés par la
        fiche d'anonymat, au format AN0001, et sont donc ceux des copies.
        """
        from udshed.api.examen_anonymat import generer_codes

        session = make_session_examen(
            self.academic_year, self.calendar,
            filiere=self.fos, niveau=self.niveau, type_dexamen=type_dexamen,
        )
        generer_codes(session.name)
        return {
            a.student: a.code_anonymat
            for a in frappe.get_all(
                "Examen Anonymat",
                filters={"session_examen": session.name},
                fields=["student", "code_anonymat"],
            )
        }

    # ------------------------------------------------------------------ #
    #  Codes anonymes
    # ------------------------------------------------------------------ #
    def test_charger_data_expose_le_code_de_la_fiche_d_anonymat(self):
        codes = self._generer_codes()
        data = charger_data(**self.args)
        lignes = data["lignes"]
        self.assertEqual(len(lignes), 2)

        exposes = {l["code_anonyme"] for l in lignes}
        self.assertEqual(exposes, set(codes.values()), "le code vient de la fiche")

        for ligne in lignes:
            self.assertRegex(ligne["code_anonyme"], r"^AN[0-9]{4}$")
            # Un code anonyme ne doit jamais coïncider avec l'identité réelle.
            self.assertNotEqual(ligne["code_anonyme"], ligne["matricule"])

    def test_aucun_code_anonyme_inventé_sans_fiche_d_anonymat(self):
        """Sans fiche d'anonymat, aucun code n'est fabriqué.

        Régression : la saisie calculait ses propres numéros AN001, AN002…
        qui ne correspondaient à aucune copie. Elle affiche désormais un code
        vide, et les documents qui exigent un code refusent de s'imprimer.
        """
        data = charger_data(**self.args)
        for ligne in data["lignes"]:
            self.assertEqual(ligne["code_anonyme"], "")
            self.assertEqual(ligne["code_anonyme_rattrapage"], "")

        with self.assertRaises(frappe.ValidationError):
            export_modele_pdf(
                TYPE_RATTRAPAGE,
                academic_year=self.args["academic_year"],
                filiere=self.args["filiere"],
                niveau=self.args["niveau"],
                semestre=self.args["semestre"],
                teaching_unit=self.args["teaching_unit"],
            )

    def test_ancien_format_de_code_refuse(self):
        """Le format AN0001 est le seul accepté : XRTUSD est refusé."""
        from udshed.api.examen_anonymat import valider_code_anonymat

        for code in ("XRTUSD", "PCDNH7", "AN1", "AN00001", "AN000A", "an0001", ""):
            with self.assertRaises(frappe.ValidationError):
                valider_code_anonymat(code)
        for code in ("AN0001", "AN0012", "AN9999"):
            valider_code_anonymat(code)

    def test_registre_refuse_un_code_hors_format(self):
        """Le contrôleur lui-même bloque un ancien code réinjecté.

        ``valider_code_anonymat`` n'est pas seulement appelé par la saisie :
        toute écriture de fiche passe par lui, donc un code hérité ne peut pas
        revenir par une voie directe.
        """
        self._generer_codes()
        fiche = frappe.get_all("Examen Anonymat", limit=1, pluck="name")[0]

        doc = frappe.get_doc("Examen Anonymat", fiche)
        code_initial = doc.code_anonymat
        doc.code_anonymat = "XRTUSD"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)
        self.assertEqual(
            frappe.db.get_value("Examen Anonymat", fiche, "code_anonymat"),
            code_initial,
            "la fiche conserve son code d'origine",
        )

    def test_sequence_globale_et_sans_trou(self):
        """La numérotation est globale, séquentielle et sans doublon.

        Chaque nouvelle fiche reçoit le numéro suivant l'ensemble des fiches
        existantes, tous examens et toutes matières confondus.
        """
        from udshed.api.examen_anonymat import _generer_code_anonymat

        premier = self._generer_codes(TYPE_NORMALE)
        second = self._generer_codes(TYPE_RATTRAPAGE_MOTEUR)
        tous = set(premier.values()) | set(second.values())
        self.assertEqual(len(tous), 4, "4 fiches => 4 codes distincts")

        numeros = sorted(int(code[2:]) for code in tous)
        self.assertEqual(
            numeros,
            list(range(numeros[0], numeros[0] + len(numeros))),
            "numérotation continue, sans trou ni doublon",
        )

        # Une fiche créée hors de la chaîne (nouvelle matière) prend la suite.
        session = frappe.get_all(
            "Session Examen",
            filters={
                "academic_year": self.academic_year.name,
                "type_dexamen": TYPE_NORMALE,
            },
            pluck="name",
        )[0]
        nouveau = _generer_code_anonymat()
        self.assertRegex(nouveau, r"^AN[0-9]{4}$")
        self.assertGreater(int(nouveau[2:]), numeros[-1])
        self.assertFalse(
            frappe.db.exists("Examen Anonymat", {"session_examen": session,
                                                 "code_anonymat": nouveau}),
            "le nouveau code n'est pas déjà pris",
        )

    def test_codes_anonymes_propres_a_chaque_matiere(self):
        """Un code anonyme par (UE, type d'examen) — pas un code pour tous."""
        self.tu2 = make_teaching_unit(
            make_course(), self.academic_year, self.fos, self.niveau,
            credits=3, type_ue="Sans TP",
        )
        for reinscription in frappe.get_all(
            "Academic Reregistration",
            filters={"academic_year": self.academic_year.name},
            fields=["name"],
        ):
            doc = frappe.get_doc("Academic Reregistration", reinscription.name)
            if not any(
                item.teaching_unit == self.tu2.name
                for item in doc.get("cours_inscrits") or []
            ):
                doc.append(
                    "cours_inscrits",
                    {
                        "teaching_unit": self.tu2.name,
                        "intitule": self.tu2.intitule_cours or self.tu2.name,
                        "semestre": "Semestre 1",
                        "statut": "Inscrit",
                    },
                )
                doc.save()

        codes_normal = self._generer_codes(TYPE_NORMALE)
        codes_rt = self._generer_codes(TYPE_RATTRAPAGE_MOTEUR)

        self.assertEqual(len(set(codes_normal.values())), 2, "un code par étudiant")
        self.assertTrue(
            set(codes_normal.values()).isdisjoint(codes_rt.values()),
            "examen normal et rattrapage : codes distincts",
        )
        for code in set(codes_normal.values()) | set(codes_rt.values()):
            self.assertRegex(code, r"^AN[0-9]{4}$")

        # Les codes de la seconde matière sont distincts de ceux de la première.
        codes_tu2 = {
            a.code_anonymat
            for a in frappe.get_all(
                "Examen Anonymat",
                filters={"teaching_unit": self.tu2.name},
                fields=["code_anonymat"],
            )
        }
        self.assertTrue(
            codes_tu2.isdisjoint(codes_normal.values()),
            "le code d'un étudiant diffère d'une matière à l'autre",
        )

    def test_lignes_exposent_les_codes_examen_et_rattrapage(self):
        """Chaque ligne porte le code examen et rattrapage de sa fiche."""
        self._generer_codes(TYPE_NORMALE)
        self._generer_codes(TYPE_RATTRAPAGE_MOTEUR)
        data = charger_data(**self.args)
        for ligne in data["lignes"]:
            self.assertRegex(ligne["code_anonyme"], r"^AN[0-9]{4}$")
            self.assertRegex(ligne["code_anonyme_rattrapage"], r"^AN[0-9]{4}$")

        set_examen = {l["code_anonyme"] for l in data["lignes"]}
        set_rattrapage = {l["code_anonyme_rattrapage"] for l in data["lignes"]}
        self.assertEqual(len(set_examen), 2)
        self.assertEqual(len(set_rattrapage), 2)
        self.assertTrue(
            set_examen.isdisjoint(set_rattrapage),
            "le code normal ne doit pas apparaître comme code rattrapage",
        )

        # Reproductibles entre deux chargements (le code est stocké).
        data2 = charger_data(**self.args)
        codes1 = [(l["code_anonyme"], l["code_anonyme_rattrapage"]) for l in data["lignes"]]
        codes2 = [(l["code_anonyme"], l["code_anonyme_rattrapage"]) for l in data2["lignes"]]
        self.assertEqual(codes1, codes2)

    # ------------------------------------------------------------------ #
    #  Feuille de saisie PDF
    # ------------------------------------------------------------------ #
    def test_export_modele_pdf_anonyme(self):
        codes = self._generer_codes()
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
        for code in codes.values():
            self.assertIn(code, html)
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
        codes = self._generer_codes()
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
        for code in codes.values():
            self.assertIn(code, html)
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
        codes = self._generer_codes()
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
            sorted(codes.values()),
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
        codes = self._generer_codes(TYPE_RATTRAPAGE_MOTEUR)
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
            sorted(codes.values()),
            "identité remplacée par le code",
        )
        for ligne in rows[1:3]:
            self.assertEqual(ligne[1:3], ["", ""], "Nom / Prénom vidés pour tous")

    # ------------------------------------------------------------------ #
    #  PV officiel : toujours nominatif
    # ------------------------------------------------------------------ #
    def test_generer_pdf_du_pv_reste_nominatif(self):
        from udshed.api.saisie_notes import _sauvegarder_examen

        codes = self._generer_codes()
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
        for code in codes.values():
            self.assertNotIn(code, html)