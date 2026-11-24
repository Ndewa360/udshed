# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests du site vitrine Udshed (/udshed) et du formulaire de démo."""

import json
import re

import frappe
from frappe.tests import IntegrationTestCase
from frappe.website.serve import get_response

from udshed.api import demo

PAGES = ("udshed", "udshed/mentions-legales", "udshed/politique-de-confidentialite", "udshed/conditions-utilisation")


class TestSiteVitrine(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_pages_publiques_et_seo(self):
		frappe.set_user("Guest")
		for route in PAGES:
			html = get_response(route).get_data(as_text=True)
			self.assertIn('rel="canonical"', html, route)
			self.assertIn('property="og:title"', html, route)
			self.assertIn('name="description"', html, route)
			self.assertIn("contact@ndewa-360.com", html, route)
			self.assertIn("Ndewa360", html, route)

	def test_donnees_structurees_valides(self):
		html = get_response("udshed").get_data(as_text=True)
		bloc = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
		donnees = json.loads(bloc)
		types = {n["@type"] for n in donnees["@graph"]}
		self.assertEqual(types, {"Organization", "SoftwareApplication", "FAQPage"})

	def test_demande_de_demo(self):
		frappe.set_user("Guest")
		avant = frappe.db.count("Communication", {"recipients": demo.CONTACT_UDSHED})
		self.assertTrue(demo.demander_demo(nom="Awa", etablissement="Université X", email="awa@example.com", consentement=1)["ok"])
		self.assertEqual(frappe.db.count("Communication", {"recipients": demo.CONTACT_UDSHED}), avant + 1)
		# Champ piège rempli (robot) : réponse neutre, rien d'enregistré.
		demo.demander_demo(nom="x", site_web="http://spam")
		self.assertEqual(frappe.db.count("Communication", {"recipients": demo.CONTACT_UDSHED}), avant + 1)

	def test_demande_de_demo_invalide(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.ValidationError):
			demo.demander_demo(nom="A", etablissement="B", email="pas-un-email", consentement=1)
		with self.assertRaises(frappe.ValidationError):
			demo.demander_demo(nom="A", etablissement="B", email="a@example.com", consentement=0)
		with self.assertRaises(frappe.ValidationError):
			demo.demander_demo(email="a@example.com", consentement=1)
