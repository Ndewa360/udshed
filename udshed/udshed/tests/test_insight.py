# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests du moteur Insight (udshed.insight) : chiffres vérifiés à la main.

Scénario — tarifs : Professeur 10 000 / h, Assistant 7 000 / h ; séances de 2 h.
  c1  (classe A)       CM 4 h (vacataire Professeur), TD 2 h (permanent)
      séances : CM passée, TD passée pointée « Fait », CM future,
                CM passée annulée, examen passé
  c2  (A + B, tronc commun) TD 4 h (vacataire Assistant)
      séance  : TD passée (type orthographié « Traveaux Dirigés (TD) »)
  c3  (classe A) ↔ c4 (classe B) cours liés, CM 2 h chacun (vacataire Professeur)
      séance  : une CM passée planifiée via c3
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate

from udshed.api import cours_commun
from udshed.insight import api, moteur
from udshed.udshed._fixture_factory import (
	make_academic_year,
	make_calendar_planing,
	make_course,
	make_faculty,
	make_field_of_study,
	make_level,
	make_teacher,
	make_teaching_unit,
	make_user_with_role,
)


class TestInsight(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Scénario construit une fois : chaque enseignant crée un compte User et
		# Frappe limite les créations d'utilisateurs (60 / heure).
		cls.annee = make_academic_year("2026", "2027")
		setting = frappe.get_single("Udshed Setting")
		tarifs = {"Professeur": 10000, "Assistant": 7000}
		setting.set("configuration_des_paiements_par_grade", [
			r for r in setting.configuration_des_paiements_par_grade if r.grade not in tarifs
		])
		for grade, prix in tarifs.items():
			setting.append("configuration_des_paiements_par_grade", {"grade": grade, "prix_heure": prix})
		setting.save(ignore_permissions=True)

		cls.cal = make_calendar_planing()
		p = cls.cal.append("heure_planification", {"libelle": "M", "heure_de_debut": "08:00:00", "heure_de_fin": "10:00:00"})
		cls.cal.save(ignore_permissions=True)
		cls.periode = p.name
		cls.faculte = make_faculty()
		cls.coord_a = make_teacher()
		cls.fil_a = make_field_of_study(cls.faculte, cls.cal, cls.coord_a)
		cls.niv_a = make_level(cls.fil_a)
		cls.fil_b = make_field_of_study(cls.faculte, cls.cal, make_teacher())
		cls.niv_b = make_level(cls.fil_b)
		cls.A = (cls.fil_a.name, str(cls.niv_a.name))
		cls.B = (cls.fil_b.name, str(cls.niv_b.name))

		cls.vac_pr = cls.prof("Vacataire", "Professeur")
		cls.vac_as = cls.prof("Vacataire", "Assistant")
		cls.perm = cls.prof("Permanent", "Professeur")

		cls.c1 = cls.cours([cls.A], cm=4, td=2, profs=[(cls.vac_pr, "Cours Magistral (CM)"), (cls.perm, "Travaux Dirigés (TD)")])
		cls.c2 = cls.cours([cls.A, cls.B], td=4, profs=[(cls.vac_as, "Travaux Dirigés (TD)")])
		cls.c3 = cls.cours([cls.A], cm=2, profs=[(cls.vac_pr, "Cours Magistral (CM)")])
		cls.c4 = cls.cours([cls.B], cm=2, profs=[(cls.vac_pr, "Cours Magistral (CM)")])
		cours_commun.lier_cours([cls.c3.name, cls.c4.name])

		j = lambda n: add_days(getdate(), n)  # noqa: E731
		cls.seance(cls.c1, j(-20), "Cours Magistral (CM)")
		cls.seance(cls.c1, j(-19), "Traveaux Dirigés (TD)", "Fait")
		cls.seance(cls.c1, j(12), "Cours Magistral (CM)")
		cls.seance(cls.c1, j(-18), "Cours Magistral (CM)", "Annulée")
		cls.seance(cls.c1, j(-17), "Examen de session normal")
		cls.seance(cls.c2, j(-16), "Traveaux Dirigés (TD)")
		cls.seance(cls.c3, j(-15), "Cours Magistral (CM)")

	@classmethod
	def prof(cls, statut, titre):
		t = make_teacher()
		frappe.db.set_value("Teacher", t.name, {"status": statut, "titre": titre})
		return t.name

	@classmethod
	def cours(cls, classes, cm=0, td=0, tp=0, profs=()):
		(fil, niv), reste = classes[0], classes[1:]
		tu = make_teaching_unit(make_course(), cls.annee,
		                        frappe.get_doc("Field of study", fil),
		                        frappe._dict(name=niv), credits=2)
		for f, n in reste:
			tu.append("course_levels", {"filiere": f, "niveau": n, "course_poid": 2})
		tu.nombre_dheure_cm, tu.nombre_dheure_td, tu.nombre_dheure_tp = cm, td, tp
		for e, t in profs:
			tu.append("table_enseignant", {"enseignant": e, "type_de_cours": t})
		tu.save(ignore_permissions=True)
		return tu

	@classmethod
	def seance(cls, tu, jour, type_, statut="Non fait"):
		frappe.get_doc({
			"doctype": "Planning Item", "cours": tu.name, "type": type_, "date": jour, "period": cls.periode,
			"academic_year": cls.annee.name, "mode": "En ligne", "status": statut,
		}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")

	def calcul(self, classes=None, **kw):
		d = moteur.Donnees(self.annee.name)
		return d, moteur.calculer(d, classes, **kw)

	# ------------------------------------------------------------------ #
	def test_types_normalises(self):
		cas = {"Traveaux Dirigés (TD)": "TD", "Travaux Dirigés (TD)": "TD", "Travaux Pratique (TP)": "TP",
		       "Traveaux Pratiques (TP)": "TP", "Cours Magistral (CM)": "CM", "Controlle Continue (CC)": "CC",
		       "Examen de session normal": "EXAMEN", "Examen de rattrapage": "RATTRAPAGE"}
		for libelle, code in cas.items():
			self.assertEqual(moteur.type_seance(libelle), code, libelle)

	def test_heures_planifiees_echues_pointees(self):
		_d, r = self.calcul({self.A, self.B})
		s = r["stats"][self.c1.name]
		self.assertEqual(s["cible"], 6)              # volume du cours de l'année
		self.assertEqual(s["planifie"], 6)           # 2 CM + 1 TD (annulée et examen exclus)
		self.assertEqual(s["echu"], 4)               # CM passée + TD passée
		self.assertEqual(s["pointe"], 2)             # seule la TD est « Fait »
		self.assertEqual((s["annulees"], s["evaluations"]), (1, 1))
		self.assertEqual(s["statut"], "en_cours")

	def test_cours_lies_comptent_pour_chaque_cours(self):
		_d, r = self.calcul({self.A, self.B})
		self.assertEqual(r["stats"][self.c3.name]["echu"], 2)
		self.assertEqual(r["stats"][self.c4.name]["echu"], 2)
		self.assertEqual(r["stats"][self.c4.name]["statut"], "termine")

	def test_finance_par_cours(self):
		_d, r = self.calcul({self.A, self.B})
		c1 = r["stats"][self.c1.name]
		# Budget : CM 4 h × 10 000 ; TD assurée par un permanent = 0.
		self.assertEqual((c1["budget"], c1["engage"], c1["realise"]), (40000, 40000, 20000))
		c2 = r["stats"][self.c2.name]
		# TD payée malgré l'orthographe « Traveaux » : 4 h × 7 000 et 2 h × 7 000.
		self.assertEqual((c2["budget"], c2["engage"], c2["realise"]), (28000, 14000, 14000))

	def test_finance_sans_double_comptage(self):
		d, r = self.calcul({self.A, self.B})
		tout = moteur.agreger(d, r, list(r["stats"]), [self.A, self.B])
		# Budget : c1 40 000 + c2 28 000 + groupe c3/c4 20 000 (compté une fois).
		self.assertEqual(tout["budget"], 88000)
		# Engagé : c1 40 000 + c2 14 000 + séance commune 20 000.
		self.assertEqual(tout["engage"], 74000)
		classe_a = moteur.agreger(d, r, list(r["stats"]), [self.A])
		classe_b = moteur.agreger(d, r, list(r["stats"]), [self.B])
		self.assertAlmostEqual(classe_a["engage"] + classe_b["engage"], tout["engage"])
		self.assertAlmostEqual(classe_a["budget"] + classe_b["budget"], tout["budget"])
		# Classe B : moitié du tronc commun (7 000) + moitié de la séance liée (10 000).
		self.assertAlmostEqual(classe_b["engage"], 17000)

	def test_vue_enseignant_remuneration_propre(self):
		d, r = self.calcul({self.A, self.B}, enseignant=self.vac_as)
		self.assertEqual(sorted(r["stats"]), [self.c2.name])
		totaux = moteur.agreger(d, r, list(r["stats"]), [self.A, self.B])
		self.assertEqual((totaux["budget"], totaux["engage"]), (28000, 14000))
		_d, r = self.calcul({self.A, self.B}, enseignant=self.perm)
		self.assertEqual(moteur.agreger(_d, r, list(r["stats"]), [self.A, self.B])["budget"], 0)

	def test_tarif_manquant_alerte_sans_planter(self):
		inconnu = self.prof("Vacataire", "Docteur")
		self.c1.append("table_enseignant", {"enseignant": inconnu, "type_de_cours": "Travaux Pratique (TP)"})
		self.c1.save(ignore_permissions=True)
		frappe.db.delete("Financial Payment Grade Config", {"grade": "Docteur", "parenttype": "Udshed Setting"})
		_d, r = self.calcul({self.A})
		self.assertIn("Docteur", r["alertes_tarifs"])

	def test_filtre_type_de_seance(self):
		_d, r = self.calcul({self.A}, type_filtre="TD")
		s = r["stats"][self.c1.name]
		self.assertEqual((s["cible"], s["planifie"], s["echu"]), (2, 2, 2))

	def test_bornes_et_avancement(self):
		frappe.db.set_value("Academic Year", self.annee.name, {"start_month": "Septembre", "end_month": "Juillet"})
		debut, fin = moteur.bornes_annee(self.annee.name)
		self.assertEqual((debut.month, fin.month, fin.day), (9, 7, 31))
		bornes = moteur.bornes_semestre(self.annee.name, "Semestre 1")
		self.assertEqual(moteur.avancement_attendu(bornes, bornes[0]), 0.0)
		self.assertEqual(moteur.avancement_attendu(bornes, bornes[1]), 1.0)

	# ------------------------------------------------------------------ #
	#  API : vues, périmètre
	# ------------------------------------------------------------------ #
	def test_tableau_de_bord_vues(self):
		data = api.tableau_de_bord("financier", self.annee.name, faculty=self.faculte.name)
		self.assertEqual(data["vue"], "faculte")
		self.assertEqual({l["filtre"]["filiere"] for l in data["lignes"]}, {self.fil_a.name, self.fil_b.name})
		classe = api.tableau_de_bord("academique", self.annee.name, self.faculte.name, self.fil_a.name, self.niv_a.name)
		self.assertEqual(classe["vue"], "classe")
		self.assertEqual({c["name"] for c in classe["cours"]}, {self.c1.name, self.c2.name, self.c3.name})
		self.assertEqual(classe["kpis"]["echu"], 4 + 2 + 2)

	def test_coordinateur_limite_a_ses_classes(self):
		user = make_user_with_role("Coordonateur")
		frappe.db.set_value("Teacher", self.coord_a.name, "email", user.name)
		frappe.set_user(user.name)
		data = api.tableau_de_bord("academique", self.annee.name)   # plus d'erreur au niveau « année »
		self.assertEqual(data["vue"], "annee")
		self.assertNotIn(self.c4.name, {c["name"] for c in data["cours"]})
		with self.assertRaises(frappe.PermissionError):
			api.tableau_de_bord("academique", self.annee.name, self.faculte.name, self.fil_b.name, self.niv_b.name)

	def test_enseignant_ne_voit_que_lui(self):
		user = make_user_with_role("Teacher")
		frappe.db.set_value("Teacher", self.vac_as, "email", user.name)
		frappe.set_user(user.name)
		data = api.tableau_de_bord("financier", self.annee.name)
		self.assertEqual(data["vue"], "enseignant")
		self.assertEqual(data["kpis"]["budget"], 28000)
		with self.assertRaises(frappe.PermissionError):
			api.tableau_de_bord("financier", self.annee.name, teacher=self.vac_pr)

	def test_comptable_finance_globale_mais_pas_academique(self):
		user = make_user_with_role("Comptable")
		frappe.set_user(user.name)
		self.assertGreaterEqual(api.tableau_de_bord("financier", self.annee.name)["kpis"]["budget"], 88000)
		with self.assertRaises(frappe.PermissionError):
			api.tableau_de_bord("academique", self.annee.name)

	def test_export_excel(self):
		import io

		import openpyxl

		api.exporter("financier", self.annee.name, faculty=self.faculte.name)
		wb = openpyxl.load_workbook(io.BytesIO(frappe.response["filecontent"]))
		self.assertEqual(wb.sheetnames, ["Synthèse", "Répartition", "Cours", "Évolution", "Alertes"])
