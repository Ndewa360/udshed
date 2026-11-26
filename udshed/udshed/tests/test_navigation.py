# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Navigation du desk (Frappe 16.6x) : chaque rôle ne voit que ses barres latérales.

Les barres (DocType « Sidebar ») n'ont pas de rôles : une entrée n'apparaît que si
l'utilisateur peut l'ouvrir. Ce test fige donc le résultat des droits par rôle.
"""

import json
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from udshed.udshed._fixture_factory import suppress_commits
from udshed.utils.navigation import BARRES, matrice_visibilite

ADMISSIONS, EXAMENS, PLANNING, INSIGHT, CONFIGURATION, ETUDIANT = BARRES
PERSONNEL = {ADMISSIONS, EXAMENS, PLANNING, INSIGHT, CONFIGURATION}

ATTENDU = {
	"System Manager": PERSONNEL,
	"Registration Manager": {ADMISSIONS, EXAMENS},
	"Agent de scolarité": {ADMISSIONS, EXAMENS},
	"Coordonateur": PERSONNEL,
	"Responsable Diplomation": {ADMISSIONS, EXAMENS},
	"Comptable": {ADMISSIONS, EXAMENS, INSIGHT},
	"Planning Manager": {EXAMENS, PLANNING, INSIGHT},
	"Teacher": {EXAMENS, PLANNING, INSIGHT},
	"Correcteur": {EXAMENS},
	"Student": {ETUDIANT},
}

APP = Path(frappe.get_app_path("udshed"))


class TestNavigation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._sans_limite = patch("frappe.core.doctype.user.user.throttle_user_creation")
		cls._sans_limite.start()
		frappe.set_user("Administrator")
		with suppress_commits():
			cls.matrice = matrice_visibilite()

	@classmethod
	def tearDownClass(cls):
		cls._sans_limite.stop()
		super().tearDownClass()

	def test_barres_par_role(self):
		for role, barres in ATTENDU.items():
			with self.subTest(role=role):
				self.assertEqual(set(self.matrice[role]), barres)

	def test_etudiant_ne_voit_que_son_espace(self):
		self.assertEqual(self.matrice["Student"], {ETUDIANT: ["Mon espace", "Ma réinscription"]})

	def test_enseignant_sans_reglages_ni_admissions(self):
		teacher = self.matrice["Teacher"]
		self.assertIn("Saisie des notes", teacher[EXAMENS])
		self.assertIn("Grille d'enseignement", teacher[PLANNING])
		# Insight financier : l'enseignant n'y voit que sa propre rémunération (vue « enseignant »).
		self.assertIn("Insight financier", teacher[INSIGHT])
		self.assertNotIn("Délibérations du jury", teacher[EXAMENS])

	def test_roles_metier_ont_leurs_ecrans(self):
		self.assertIn("Éditeur de modèles", self.matrice["Responsable Diplomation"][ADMISSIONS])
		self.assertIn("Sessions de réinscription", self.matrice["Registration Manager"][ADMISSIONS])
		self.assertIn("Rapports de réinscription", self.matrice["Registration Manager"][ADMISSIONS])
		self.assertIn("Planning", self.matrice["Planning Manager"][PLANNING])
		self.assertIn("Enseignants", self.matrice["Planning Manager"][PLANNING])

	def test_barres_livrees_coherentes(self):
		"""Aucun lien URL (visible par tous, Frappe ne les filtre pas) et des cibles qui existent."""
		titres = set()
		for fichier in (APP / "udshed" / "sidebar").glob("*/*.json"):
			barre = json.loads(fichier.read_text(encoding="utf-8"))
			titres.add(barre["title"])
			for item in barre["items"]:
				if item["type"] != "Link":
					continue
				with self.subTest(barre=barre["title"], entree=item["label"]):
					self.assertIn(item["link_type"], ("DocType", "Page", "Report"))
					self.assertTrue(frappe.db.exists(item["link_type"], item["link_to"]))
		self.assertEqual(titres, set(BARRES))

		dock = json.loads((APP / "dock" / "udshed" / "udshed.json").read_text(encoding="utf-8"))
		self.assertEqual([i["link_to"] for i in dock["items"]], BARRES)
		self.assertTrue(all(i["link_type"] == "Sidebar" for i in dock["items"]))

	def test_etudiant_sans_acces_aux_dossiers_du_personnel(self):
		for doctype in ("Inscription Academique", "Academic Reregistration", "Acte Academique",
						"Requete Etudiant", "Session Reinscription", "Course", "Field of study"):
			with self.subTest(doctype=doctype):
				self.assertFalse(frappe.permissions.has_permission(
					doctype, "read", user=self._utilisateur("Student"), print_logs=False))

	def test_enseignant_selection_seule_sur_les_referentiels(self):
		user = self._utilisateur("Teacher")
		for doctype in ("Academic Year", "Faculty", "Field of study", "Teaching Unit Value"):
			with self.subTest(doctype=doctype):
				self.assertTrue(frappe.permissions.has_permission(doctype, "select", user=user, print_logs=False))
				self.assertFalse(frappe.permissions.has_permission(doctype, "read", user=user, print_logs=False))
		self.assertFalse(frappe.permissions.has_permission("Udshed Setting", "read", user=user, print_logs=False))

	def _utilisateur(self, role):
		email = f"nav-{frappe.scrub(role)}@udshed.invalid"
		if not frappe.db.exists("User", email):
			with suppress_commits():
				frappe.get_doc({"doctype": "User", "email": email, "first_name": f"Nav {role}",
								"send_welcome_email": 0, "roles": [{"role": role}]}).insert(ignore_permissions=True)
		return email
