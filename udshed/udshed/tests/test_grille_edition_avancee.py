# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Édition avancée de la grille et import par nom d'enseignant.

Cas couverts :
  - changement de code d'un cours EN CASCADE (le planning suit), code déjà pris refusé,
    ancien code conservé par les autres années ;
  - tronc commun : changement de code / d'UE refusé sans confirmation ;
  - code et intitulé d'une UE, UE de même code refusée ;
  - déplacement d'un cours vers une UE existante ou nouvelle, l'UE vidée est supprimée ;
  - fiche complète (intitulé, heures, enseignants, UE, code en une fois) ;
  - import : enseignant reconnu par son nom (sans titre, ordre inversé, sans accents),
    enseignant inconnu ou homonyme ignoré (case vide) sans bloquer l'import ;
  - prévisualisation : avant / après des cours modifiés.
"""

import os

import frappe
import openpyxl
from frappe.tests import IntegrationTestCase

from udshed.api import grille_edition, teaching_grid
from udshed.udshed._fixture_factory import (
	make_academic_year,
	make_calendar_planing,
	make_faculty,
	make_field_of_study,
	make_level,
	make_teacher,
	unique_code,
)

ENTETES = ["Code UE", "Code Cours", "Intitulés", "Crédits", "TYPE", "CM", "TD", "TP", "TPE",
           "Enseignant (CM)", "Enseignant (TD)", "Enseignant (TP)"]


def _enseignant(prenom, nom, grade="Dr"):
	doc = frappe.new_doc("Teacher")
	doc.update({"grade": grade, "first_name": prenom, "last_name": nom, "status": "Permanent",
	            "email": f"{frappe.generate_hash(length=10)}@example.com"})
	return doc.insert(ignore_permissions=True)


class TestGrilleEditionAvancee(IntegrationTestCase):
	def setUp(self):
		self.annee = make_academic_year("2026", "2027")
		self.calendrier = make_calendar_planing()
		self.faculte = make_faculty()
		self.filiere = make_field_of_study(self.faculte, self.calendrier, make_teacher())
		self.filiere.has_uv_in_grid = 1
		self.niveau = make_level(self.filiere)
		self.ctx = dict(academic_year=self.annee.name, faculty=self.faculte.name, filiere=self.filiere.name,
		                niveau=self.niveau.name, semestre="Semestre 1")
		self.ue = unique_code("UE")
		self.code = unique_code("CRS")
		self.tu = teaching_grid.ajouter_cours(**self.ctx, code=self.code, intitule_cours="Analyse", credits=3,
		                                      ue_code=self.ue, ue_intitule="Mathématiques",
		                                      nombre_dheure_cm=30, nombre_dheure_td=10)["teaching_unit"]

	def ue_de(self, tu):
		return frappe.db.get_value("Teaching Unit Value", frappe.db.get_value("Teaching Unit", tu, "unite_de_valeur"), "code")

	def autre_classe(self):
		filiere = make_field_of_study(self.faculte, self.calendrier, make_teacher())
		filiere.has_uv_in_grid = 1
		niveau = make_level(filiere)
		return {**self.ctx, "filiere": filiere.name, "niveau": niveau.name}

	# ------------------------------------------------------------------ codes
	def test_code_cours_renomme_en_cascade(self):
		periode = self.calendrier.append("heure_planification", {"libelle": "Matin", "heure_de_debut": "08:00:00", "heure_de_fin": "12:00:00"})
		self.calendrier.save(ignore_permissions=True)
		seance = frappe.get_doc({"doctype": "Planning Item", "cours": self.tu, "type": "Cours Magistral (CM)",
		                         "date": "2026-11-02", "period": periode.name, "academic_year": self.annee.name,
		                         "mode": "En ligne"}).insert(ignore_permissions=True)
		nouveau = unique_code("NEW")
		res = grille_edition.enregistrer_cours(self.tu, **self.ctx, valeurs={"code": nouveau})
		tu = res["teaching_unit"]
		self.assertNotEqual(tu, self.tu)
		self.assertTrue(tu.startswith(nouveau + "-"))
		self.assertEqual(frappe.db.get_value("Teaching Unit", tu, "course"), nouveau)
		self.assertFalse(frappe.db.exists("Course", self.code))  # renommé, pas dupliqué
		self.assertEqual(frappe.db.get_value("Course", nouveau, "code"), nouveau)
		self.assertEqual(frappe.db.get_value("Planning Item", seance.name, "cours"), tu)  # la séance suit

	def test_code_deja_pris_dans_l_annee_refuse(self):
		autre = unique_code("CRS")
		teaching_grid.ajouter_cours(**self.ctx, code=autre, intitule_cours="Algèbre", credits=3, ue_code=self.ue)
		with self.assertRaises(frappe.ValidationError):
			grille_edition.enregistrer_cours(self.tu, **self.ctx, valeurs={"code": autre})
		self.assertEqual(frappe.db.get_value("Teaching Unit", self.tu, "course"), self.code)

	def test_ancien_code_garde_par_les_autres_annees(self):
		annee2 = make_academic_year("2027", "2028")
		ancien = frappe.get_doc({"doctype": "Teaching Unit", "course": self.code, "academic_year": annee2.name,
		                         "intitule_cours": "Analyse", "semestre": "Semestre 1", "credits": 3}).insert(
			ignore_permissions=True, ignore_mandatory=True)
		nouveau = unique_code("NEW")
		tu = grille_edition.enregistrer_cours(self.tu, **self.ctx, valeurs={"code": nouveau})["teaching_unit"]
		self.assertEqual(frappe.db.get_value("Teaching Unit", tu, "course"), nouveau)
		self.assertEqual(frappe.db.get_value("Teaching Unit", ancien.name, "course"), self.code)
		self.assertTrue(frappe.db.exists("Course", self.code))

	def test_tronc_commun_exige_confirmation(self):
		ctx_b = self.autre_classe()
		teaching_grid.ajouter_cours(**ctx_b, code=self.code, credits=4)
		with self.assertRaises(frappe.ValidationError):
			grille_edition.enregistrer_cours(self.tu, **self.ctx, valeurs={"code": unique_code("NEW")})
		with self.assertRaises(frappe.ValidationError):
			grille_edition.changer_ue(self.tu, unique_code("UE"), **self.ctx, ue_intitule="Autre")
		# Crédits seuls : propres à la classe, pas de confirmation.
		grille_edition.enregistrer_cours(self.tu, **self.ctx, valeurs={"credits": 2})
		nouveau = unique_code("NEW")
		tu = grille_edition.enregistrer_cours(self.tu, **self.ctx, valeurs={"code": nouveau},
		                                      appliquer_au_tronc_commun=1)["teaching_unit"]
		self.assertEqual(frappe.db.get_value("Teaching Unit", tu, "course"), nouveau)
		self.assertEqual(len(frappe.get_doc("Teaching Unit", tu).course_levels), 2)  # les deux classes suivent

	def test_code_et_intitule_ue(self):
		nouveau = unique_code("UEN")
		res = grille_edition.enregistrer_ue(self.ue, **self.ctx, code=nouveau, intitule="Analyse et algèbre")
		self.assertEqual(frappe.db.get_value("Teaching Unit Value", res["ue"], ["code", "intitule"]),
		                 (nouveau, "Analyse et algèbre"))
		self.assertEqual(self.ue_de(self.tu), nouveau)
		# Code d'une autre UE de l'année : refusé.
		autre_ue = unique_code("UE")
		teaching_grid.ajouter_cours(**self.ctx, code=unique_code("CRS"), intitule_cours="X", credits=2,
		                            ue_code=autre_ue, ue_intitule="Autre")
		with self.assertRaises(frappe.ValidationError):
			grille_edition.enregistrer_ue(nouveau, **self.ctx, code=autre_ue)

	# ------------------------------------------------------------------ UE
	def test_deplacement_vers_ue_existante_puis_nouvelle(self):
		autre_ue = unique_code("UE")
		teaching_grid.ajouter_cours(**self.ctx, code=unique_code("CRS"), intitule_cours="Physique", credits=3,
		                            ue_code=autre_ue, ue_intitule="Physique")
		ancienne = frappe.db.get_value("Teaching Unit", self.tu, "unite_de_valeur")
		grille_edition.changer_ue(self.tu, autre_ue, **self.ctx)
		self.assertEqual(self.ue_de(self.tu), autre_ue)
		self.assertFalse(frappe.db.exists("Teaching Unit Value", ancienne))  # UE vidée : supprimée

		nouvelle = unique_code("UEN")
		grille_edition.changer_ue(self.tu, nouvelle, **self.ctx, ue_intitule="Nouvelle UE")
		self.assertEqual(self.ue_de(self.tu), nouvelle)
		self.assertEqual(frappe.db.get_value("Teaching Unit Value", {"code": nouvelle}, "intitule"), "Nouvelle UE")

	def test_fiche_complete(self):
		prof = make_teacher()
		res = grille_edition.enregistrer_cours(self.tu, **self.ctx, valeurs={
			"intitule_cours": "Analyse I", "credits": 4, "nombre_dheure_cm": 40, "nombre_dheure_td": 15,
			"enseignants": [{"enseignant": prof.name, "type_de_cours": "Travaux Dirigés (TD)"}],
			"ue_code": unique_code("UEN"), "ue_intitule": "Analyse",
		})
		doc = frappe.get_doc("Teaching Unit", res["teaching_unit"])
		self.assertEqual((doc.intitule_cours, doc.nombre_dheure_cm, doc.course_levels[0].course_poid), ("Analyse I", 40, 4))
		self.assertEqual([(r.enseignant, r.type_de_cours) for r in doc.table_enseignant], [(prof.name, "Travaux Dirigés (TD)")])
		infos = grille_edition.infos_cours(doc.name, **self.ctx)
		self.assertEqual(infos["ue_code"], self.ue_de(doc.name))

	# ------------------------------------------------------------------ import
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
		return dict(file_url=f"/private/files/{nom}", **self.ctx)

	def test_import_par_nom_et_enseignant_inconnu(self):
		suffixe = frappe.generate_hash(length=6).lower()
		aline = _enseignant("Aline", f"Fötso{suffixe}")
		paul = _enseignant("Paul", f"Mbarga{suffixe}", grade="Pr")
		_enseignant("Jean", f"Kamga{suffixe}")
		_enseignant("Jean", f"Kamga{suffixe}", grade="Ing")  # homonyme
		c1, c2, c3 = unique_code("C1"), unique_code("C2"), unique_code("C3")
		lignes = [
			[self.ue, "", "Mathématiques", 9, "UE"],
			["", c1, "Analyse", 3, "ENS", 30, 10, 0, 0, f"FOTSO{suffixe} aline", f"Pr Paul Mbarga{suffixe}", ""],
			["", c2, "Algèbre", 3, "ENS", 30, 10, 0, 0, "Inconnu Total", "", ""],
			["", c3, "Logique", 3, "ENS", 30, 10, 0, 0, f"Jean Kamga{suffixe}", "", ""],
		]
		analyse = teaching_grid.previsualiser_import_grille(**self.fichier(lignes))
		self.assertEqual(analyse["erreurs"], [])
		self.assertEqual(analyse["stats"]["enseignants_ignores"], 2)
		par_code = {c["code"]: c for c in analyse["cours"]}
		self.assertEqual(par_code[c1]["enseignants"], [
			{"enseignant": aline.name, "type_de_cours": "Cours Magistral (CM)"},
			{"enseignant": paul.name, "type_de_cours": "Travaux Dirigés (TD)"},
		])
		self.assertIn("Plusieurs enseignants", par_code[c3]["enseignants_ignores"][0])

		teaching_grid.import_grid(**self.fichier(lignes))
		tu2 = frappe.db.get_value("Teaching Unit", {"course": c2, "academic_year": self.annee.name}, "name")
		self.assertEqual(frappe.get_doc("Teaching Unit", tu2).table_enseignant, [])  # case vide

	def test_previsualisation_avant_apres(self):
		lignes = [[self.ue, "", "Mathématiques", 4, "UE"], ["", self.code, "Analyse réelle", 4, "ENS", 30, 10, 0, 0, "", "", ""]]
		analyse = teaching_grid.previsualiser_import_grille(**self.fichier(lignes))
		changements = {c["champ"]: (c["avant"], c["apres"]) for c in analyse["cours"][0]["changements"]}
		self.assertEqual(changements["Intitulé"], ("Analyse", "Analyse réelle"))
		self.assertEqual(changements["Crédits"], (3, 4.0))
		self.assertNotIn("CM", changements)
		self.assertEqual(analyse["stats"]["cours_modifies"], 1)
