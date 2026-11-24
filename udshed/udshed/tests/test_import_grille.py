# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests de l'import de grille d'enseignement (prévisualisation + import).

Cas couverts :
  - la prévisualisation n'écrit rien et décrit fidèlement l'import ;
  - import initial : UE, cours, crédits de la classe et enseignants créés ;
  - ré-import idempotent : aucun doublon de ligne de classe ni d'enseignant ;
  - un cours retiré du fichier est supprimé s'il n'a aucune donnée, conservé
    (et signalé) s'il a des séances planifiées ;
  - un fichier en erreur est refusé en bloc : la grille existante est intacte
    (auparavant elle était effacée puis importée à moitié) ;
  - tronc commun : l'import d'une classe ne modifie pas l'intitulé, les heures
    ni les enseignants partagés avec une autre classe ;
  - avertissement de cohérence crédits / heures (10-15 h par crédit).
"""

import os

import frappe
import openpyxl
from frappe.tests import IntegrationTestCase

from udshed.api import teaching_grid
from udshed.udshed._fixture_factory import (
	make_academic_year,
	make_calendar_planing,
	make_faculty,
	make_field_of_study,
	make_level,
	make_teacher,
	unique_code,
)
from udshed.utils import grille

ENTETES = ["Code UE", "Code Cours", "Intitulés", "Crédits", "TYPE", "CM", "TD", "TP", "TPE",
           "Email Enseignant (CM)", "Email Enseignant (TD)", "Email Enseignant (TP)"]


class TestImportGrille(IntegrationTestCase):
	def setUp(self):
		self.annee = make_academic_year("2026", "2027")
		self.calendrier = make_calendar_planing()
		self.faculte = make_faculty()
		self.filiere = make_field_of_study(self.faculte, self.calendrier, make_teacher())
		self.filiere.has_uv_in_grid = 1
		self.niveau = make_level(self.filiere)  # enregistre aussi has_uv_in_grid
		self.prof = make_teacher()
		self.ue = unique_code("UE")
		self.c1, self.c2 = unique_code("C1"), unique_code("C2")

	def fichier(self, lignes):
		wb = openpyxl.Workbook()
		ws = wb.active
		ws.append(ENTETES)
		for ligne in lignes:
			ws.append(ligne)
		nom = f"grille-{frappe.generate_hash(length=8)}.xlsx"
		chemin = frappe.get_site_path("private", "files", nom)
		os.makedirs(os.path.dirname(chemin), exist_ok=True)
		wb.save(chemin)
		self.addCleanup(os.remove, chemin)
		return f"/private/files/{nom}"

	def lignes_standard(self, avec_c2=True, heures_c1=30):
		lignes = [
			[self.ue, "", "Mathématiques", 6, "UE"],
			["", self.c1, "Analyse", 3, "ENS", heures_c1, 10, 0, 20, self.prof.email, "", ""],
		]
		if avec_c2:
			lignes.append(["", self.c2, "Algèbre", 3, "ENS", 25, 15, 0, 20, self.prof.email, "", ""])
		return lignes

	def args(self, file_url):
		return dict(
			file_url=file_url, academic_year=self.annee.name, faculty=self.faculte.name,
			filiere=self.filiere.name, niveau=self.niveau.name, semestre="Semestre 1",
		)

	def tu(self, code):
		return frappe.db.get_value("Teaching Unit", {"course": code, "academic_year": self.annee.name}, "name")

	# ------------------------------------------------------------------ #
	def test_previsualisation_sans_ecriture(self):
		avant = frappe.db.count("Teaching Unit")
		analyse = teaching_grid.previsualiser_import_grille(**self.args(self.fichier(self.lignes_standard())))
		self.assertEqual(frappe.db.count("Teaching Unit"), avant)
		self.assertEqual(analyse["erreurs"], [])
		self.assertEqual(analyse["stats"]["cours_nouveaux"], 2)
		self.assertEqual(analyse["stats"]["ues_nouvelles"], 1)

	def test_import_puis_reimport_idempotent(self):
		url = self.fichier(self.lignes_standard())
		resultat = teaching_grid.import_grid(**self.args(url))
		self.assertEqual(resultat["data"]["courses_created"], 2)
		tu = frappe.get_doc("Teaching Unit", self.tu(self.c1))
		self.assertEqual([(r.filiere, str(r.niveau), r.course_poid) for r in tu.course_levels],
		                 [(self.filiere.name, str(self.niveau.name), 3)])
		self.assertEqual([r.enseignant for r in tu.table_enseignant], [self.prof.name])

		teaching_grid.import_grid(**self.args(url))
		tu.reload()
		self.assertEqual(len(tu.course_levels), 1)
		self.assertEqual(len(tu.table_enseignant), 1)

	def test_cours_retire_supprime_ou_conserve_selon_dependances(self):
		teaching_grid.import_grid(**self.args(self.fichier(self.lignes_standard())))
		# c1 a une séance planifiée : il doit être conservé.
		periode = self.calendrier.append("heure_planification", {"libelle": "Matin", "heure_de_debut": "08:00:00", "heure_de_fin": "12:00:00"})
		self.calendrier.save(ignore_permissions=True)
		frappe.get_doc({"doctype": "Planning Item", "cours": self.tu(self.c1), "type": "Cours Magistral (CM)",
		                "date": "2026-11-02", "period": periode.name, "academic_year": self.annee.name,
		                "mode": "En ligne"}).insert(ignore_permissions=True)

		fichier_vide = self.fichier([[self.ue, "", "Mathématiques", 0, "UE"], ["", unique_code("C3"), "Autre", 3, "ENS", 30, 10, 0, 0, "", "", ""]])
		analyse = teaching_grid.previsualiser_import_grille(**self.args(fichier_vide))
		etats = {r["code"]: r["bloque"] for r in analyse["retraits"]}
		self.assertEqual(etats, {self.c1: True, self.c2: False})

		resultat = teaching_grid.import_grid(**self.args(fichier_vide))
		self.assertEqual(resultat["data"]["courses_kept"], 1)
		self.assertTrue(self.tu(self.c1))  # conservé
		self.assertFalse(self.tu(self.c2))  # orphelin sans données : supprimé

	def test_fichier_invalide_ne_touche_pas_la_grille(self):
		teaching_grid.import_grid(**self.args(self.fichier(self.lignes_standard())))
		mauvais = self.lignes_standard() + [["", self.c1, "Doublon", 3, "ENS", 30, 10, 0, 0, "inconnu@nulle-part.test", "", ""]]
		analyse = teaching_grid.previsualiser_import_grille(**self.args(self.fichier(mauvais)))
		messages = " ".join(e["message"] for e in analyse["erreurs"])
		self.assertIn("deux fois", messages)
		with self.assertRaises(frappe.ValidationError):
			teaching_grid.import_grid(**self.args(self.fichier(mauvais + [["", unique_code("C9"), "X", 2, "ENS", 20, 0, 0, 0, "inconnu@nulle-part.test", "", ""]])))
		self.assertTrue(self.tu(self.c1) and self.tu(self.c2))
		self.assertEqual(len(frappe.get_doc("Teaching Unit", self.tu(self.c1)).course_levels), 1)

	def test_tronc_commun_valeurs_partagees_preservees(self):
		teaching_grid.import_grid(**self.args(self.fichier(self.lignes_standard(avec_c2=False))))
		autre_filiere = make_field_of_study(self.faculte, self.calendrier, make_teacher())
		autre_niveau = make_level(autre_filiere)
		tu = frappe.get_doc("Teaching Unit", self.tu(self.c1))
		tu.append("course_levels", {"filiere": autre_filiere.name, "niveau": autre_niveau.name, "course_poid": 4})
		tu.save(ignore_permissions=True)

		modifie = [[self.ue, "", "Mathématiques", 5, "UE"],
		           ["", self.c1, "Analyse renommée", 5, "ENS", 99, 10, 0, 20, "", "", ""]]
		analyse = teaching_grid.previsualiser_import_grille(**self.args(self.fichier(modifie)))
		self.assertTrue(any("partagé" in a for a in analyse["cours"][0]["avertissements"]))
		teaching_grid.import_grid(**self.args(self.fichier(modifie)))
		tu.reload()
		self.assertEqual(tu.intitule_cours, "Analyse")
		self.assertEqual(tu.nombre_dheure_cm, 30)
		self.assertEqual([r.enseignant for r in tu.table_enseignant], [self.prof.name])
		poids = {str(r.niveau): r.course_poid for r in tu.course_levels}
		self.assertEqual(poids[str(self.niveau.name)], 5)
		self.assertEqual(poids[str(autre_niveau.name)], 4)

	def test_colonnes_reconnues_par_entetes(self):
		"""Format préparé à la main : pas de colonne TYPE, une seule colonne
		« Enseignant », intitulé « Intitulés des cours » (cas réel signalé).
		Lire par position décalait tout : l'email tombait dans la colonne TPE."""
		entetes = ["Code UE", "Code Cours", "Intitulés des cours", "Crédits", "CM", "TD", "TP", "TPE", "Enseignant"]
		lignes = [
			[self.ue, None, "Mathématiques", 4, None, None, None, None, None],
			[None, self.c1, "Analyse", 2, 16, 6, 0, 8, self.prof.email],
			[None, self.c2, "TP de mesures", 2, 0, 0, 20, 10, self.prof.email],
		]
		wb = openpyxl.Workbook()
		ws = wb.active
		ws.append(entetes)
		for ligne in lignes:
			ws.append(ligne)
		nom = f"grille-{frappe.generate_hash(length=8)}.xlsx"
		chemin = frappe.get_site_path("private", "files", nom)
		wb.save(chemin)
		self.addCleanup(os.remove, chemin)

		analyse = teaching_grid.previsualiser_import_grille(**self.args(f"/private/files/{nom}"))
		self.assertEqual(analyse["erreurs"], [])
		self.assertEqual(analyse["mode_colonnes"], "entetes")
		c1, c2 = analyse["cours"]
		self.assertEqual((c1["nombre_dheure_cm"], c1["nombre_dheure_td"], c1["nombre_dheure_tpe"]), (16, 6, 8))
		# Colonne « Enseignant » unique : type déduit des heures.
		self.assertEqual(c1["enseignants"], [{"enseignant": self.prof.name, "type_de_cours": "Cours Magistral (CM)"}])
		self.assertEqual(c2["enseignants"][0]["type_de_cours"], "Travaux Pratique (TP)")
		self.assertEqual(c1["avertissements"], [])  # 22 h pour 2 crédits : dans la norme

	def test_reconnaissance_des_entetes(self):
		cas = {
			"Code UE": "code_ue", "Code de l'UE": "code_ue", "Code Cours": "code_cours",
			"Intitulés des cours": "intitule", "Libellé": "intitule", "Crédits": "credits",
			"Email Enseignant (CM)": "ens_cm", "Enseignant TP": "ens_tp", "Enseignant": "ens",
			"Volume CM": "cm", "Heures TD": "td", "TPE": "tpe", "TYPE": "type", "Total": "total",
			"Observations": None,
		}
		for entete, role in cas.items():
			self.assertEqual(teaching_grid._role_colonne(entete), role, entete)

	def test_coherence_credits_heures(self):
		self.assertIsNone(grille.coherence_credits(3, {"nombre_dheure_cm": 30, "nombre_dheure_td": 10}))
		self.assertTrue(grille.coherence_credits(3, {"nombre_dheure_cm": 10}))
		self.assertTrue(grille.coherence_credits(2, {"nombre_dheure_cm": 60}))
		analyse = teaching_grid.previsualiser_import_grille(**self.args(self.fichier(self.lignes_standard(heures_c1=200))))
		self.assertTrue(analyse["cours"][0]["avertissements"])
