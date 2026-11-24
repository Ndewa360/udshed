# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Tests du planning : conflits de créneau, droits (tronc commun), email.

Cas couverts :
  - deux cours sur le même créneau d'une même classe sont refusés, quel que
    soit le chemin d'écriture (insertion directe du Planning Item) ;
  - conflit d'enseignant et de salle sur un même créneau ;
  - un créneau différent (autre période ou autre jour) reste libre ;
  - tronc commun : le coordinateur de CHAQUE classe peut planifier le cours
    partagé pour sa classe (auparavant toutes les classes devaient être dans
    son périmètre) ;
  - un coordinateur ne peut pas planifier pour une classe hors périmètre ;
  - plus d'usurpation d'identité (as_coordinator ne change plus l'utilisateur) ;
  - l'envoi du planning par email ne plante plus (« _ » n'est plus écrasé).
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from udshed.api import planning_calendar, planning_calendar_email, planning_permission
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
from udshed.utils.planning_conflits import conflits


class TestPlanning(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Chaque enseignant créé crée aussi un User : Frappe limite à 60 créations
		# d'utilisateurs par heure (« Throttled »), limite atteinte par cette classe.
		cls._sans_limite = patch("frappe.core.doctype.user.user.throttle_user_creation")
		cls._sans_limite.start()

	@classmethod
	def tearDownClass(cls):
		cls._sans_limite.stop()
		super().tearDownClass()

	def setUp(self):
		self.annee = make_academic_year("2026", "2027")
		self.calendrier = make_calendar_planing()
		periode = self.calendrier.append(
			"heure_planification", {"libelle": "Matin", "heure_de_debut": "08:00:00", "heure_de_fin": "12:00:00"}
		)
		periode2 = self.calendrier.append(
			"heure_planification", {"libelle": "Soir", "heure_de_debut": "13:00:00", "heure_de_fin": "16:00:00"}
		)
		self.calendrier.save(ignore_permissions=True)
		self.matin, self.soir = periode.name, periode2.name

		faculte = make_faculty()
		self.coord_a, self.coord_b = make_teacher(), make_teacher()
		self.filiere_a = make_field_of_study(faculte, self.calendrier, self.coord_a)
		self.niveau_a = make_level(self.filiere_a)
		self.filiere_b = make_field_of_study(faculte, self.calendrier, self.coord_b)
		self.niveau_b = make_level(self.filiere_b)

		self.cours_a1 = make_teaching_unit(make_course(), self.annee, self.filiere_a, self.niveau_a)
		self.cours_a2 = make_teaching_unit(make_course(), self.annee, self.filiere_a, self.niveau_a)
		# Tronc commun : un seul cours suivi par A et B.
		self.tronc = make_teaching_unit(make_course(), self.annee, self.filiere_a, self.niveau_a)
		self.tronc.append("course_levels", {"filiere": self.filiere_b.name, "niveau": self.niveau_b.name, "course_poid": 3})
		self.tronc.save(ignore_permissions=True)

		self.prof1, self.prof2 = make_teacher(), make_teacher()
		for cours, prof in ((self.cours_a1, self.prof1), (self.cours_a2, self.prof2), (self.tronc, self.prof2)):
			cours.append("table_enseignant", {"enseignant": prof.name, "type_de_cours": "Cours Magistral (CM)"})
			cours.save(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")

	def seance(self, cours, jour="2026-11-02", period=None, salle=None, inserer=True):
		doc = frappe.get_doc({
			"doctype": "Planning Item",
			"cours": cours.name,
			"type": "Cours Magistral (CM)",
			"date": jour,
			"period": period or self.matin,
			"academic_year": self.annee.name,
			"mode": "En présentiel",
			"salle": salle,
		})
		if inserer:
			doc.insert(ignore_permissions=True)
		return doc

	def coordinateur(self, teacher):
		user = make_user_with_role("Coordonateur")
		frappe.db.set_value("Teacher", teacher.name, "email", user.name)
		return user.name

	# ------------------------------------------------------------------ #
	#  Conflits
	# ------------------------------------------------------------------ #
	def test_deux_cours_meme_classe_meme_creneau_refuse(self):
		self.seance(self.cours_a1)
		with self.assertRaises(frappe.ValidationError):
			self.seance(self.cours_a2)

	def test_creneau_different_reste_libre(self):
		self.seance(self.cours_a1)
		self.seance(self.cours_a2, period=self.soir)
		self.seance(self.cours_a2, jour="2026-11-03")

	def test_tronc_commun_occupe_les_deux_classes(self):
		self.seance(self.tronc)
		# La classe A est occupée par le tronc commun : impossible d'y mettre a1.
		types = {c["type"] for c in conflits(self.cours_a1.name, "2026-11-02", self.matin)}
		self.assertIn("classe", types)

	def test_conflit_enseignant(self):
		self.cours_a1.set("table_enseignant", [{"enseignant": self.prof2.name, "type_de_cours": "Cours Magistral (CM)"}])
		self.cours_a1.save(ignore_permissions=True)
		autre_classe = make_teaching_unit(make_course(), self.annee, self.filiere_b, self.niveau_b)
		autre_classe.append("table_enseignant", {"enseignant": self.prof2.name, "type_de_cours": "Cours Magistral (CM)"})
		autre_classe.save(ignore_permissions=True)
		self.seance(self.cours_a1)
		liste = conflits(autre_classe.name, "2026-11-02", self.matin)
		self.assertEqual([c["type"] for c in liste], ["enseignant"])

	def test_modification_ne_se_bloque_pas_elle_meme(self):
		doc = self.seance(self.cours_a1)
		doc.mode = "Hybride"
		doc.save(ignore_permissions=True)

	def test_seance_annulee_libere_le_creneau(self):
		doc = self.seance(self.cours_a1)
		self.assertEqual(doc.status, "Non fait")  # plus « Fait » par défaut
		doc.status = "Annulée"
		doc.save(ignore_permissions=True)
		self.seance(self.cours_a2)  # même classe, même créneau : désormais libre

	def test_pointage_automatique_du_dimanche(self):
		from frappe.utils import add_days

		from udshed.utils import pointage

		lundi = pointage.debut_semaine()
		seance = lambda decalage: self.seance(self.cours_a1, jour=add_days(lundi, decalage)).name  # noqa: E731
		auto = seance(0)                 # lundi de la semaine : planifiée
		declaree = seance(1)             # mardi : déclarée « Non fait » à la main
		annulee = seance(2)              # mercredi : annulée
		suivante = seance(7)             # semaine suivante
		rattrapage = seance(-7)          # semaine passée jamais traitée

		planning_calendar.update_planning(
			declaree, self.annee.name, self.cours_a1.name, "Cours Magistral (CM)", str(add_days(lundi, 1)),
			self.matin, mode="En ligne", statut="Non fait",
		)
		self.assertEqual(frappe.db.get_value("Planning Item", declaree, "pointage_manuel"), 1)
		doc = frappe.get_doc("Planning Item", annulee)
		doc.status = "Annulée"
		doc.save(ignore_permissions=True)

		pointage.pointer_semaine()
		statut = lambda n: frappe.db.get_value("Planning Item", n, "status")  # noqa: E731
		self.assertEqual(statut(auto), "Fait")
		self.assertEqual(statut(rattrapage), "Fait")
		self.assertEqual(statut(declaree), "Non fait")   # choix explicite respecté
		self.assertEqual(statut(annulee), "Annulée")
		self.assertEqual(statut(suivante), "Non fait")

	def test_statut_planifiee_et_seance_deplacee(self):
		from frappe.utils import add_days

		from udshed.utils import pointage

		lundi = pointage.debut_semaine()
		doc = self.seance(self.cours_a1, jour=add_days(lundi, -14))
		pointage.pointer_semaine()
		doc.reload()
		self.assertEqual((doc.status, doc.pointage_manuel), ("Fait", 0))
		# Repoussée à la semaine prochaine (Desk) : redevient « Non fait », toujours automatique.
		doc.date = add_days(lundi, 9)
		doc.save(ignore_permissions=True)
		self.assertEqual((doc.status, doc.pointage_manuel), ("Non fait", 0))
		# Retour au pointage automatique après un choix manuel.
		planning_calendar.update_planning(
			doc.name, self.annee.name, self.cours_a1.name, "Cours Magistral (CM)", str(add_days(lundi, 9)),
			self.matin, mode="En ligne", statut="Annulée",
		)
		planning_calendar.update_planning(
			doc.name, self.annee.name, self.cours_a1.name, "Cours Magistral (CM)", str(add_days(lundi, 9)),
			self.matin, mode="En ligne", statut="auto",
		)
		doc.reload()
		self.assertEqual((doc.status, doc.pointage_manuel), ("Non fait", 0))

	def test_pointage_fait_refuse_pour_une_seance_future(self):
		doc = self.seance(self.cours_a1, jour="2099-01-05")
		with self.assertRaises(frappe.ValidationError):
			planning_calendar.update_planning(
				doc.name, self.annee.name, self.cours_a1.name, "Cours Magistral (CM)", "2099-01-05", self.matin,
				mode="En ligne", statut="Fait",
			)
		planning_calendar.update_planning(
			doc.name, self.annee.name, self.cours_a1.name, "Cours Magistral (CM)", "2099-01-05", self.matin,
			mode="En ligne", statut="Annulée",
		)
		self.assertEqual(frappe.db.get_value("Planning Item", doc.name, "status"), "Annulée")

	# ------------------------------------------------------------------ #
	#  Droits
	# ------------------------------------------------------------------ #
	def test_coordinateur_peut_planifier_tronc_commun_pour_sa_classe(self):
		user_b = self.coordinateur(self.coord_b)
		frappe.set_user(user_b)
		resultat = planning_calendar.create_planning(
			self.annee.name, self.tronc.name, "Cours Magistral (CM)", "2026-11-04", self.matin,
			filiere=self.filiere_b.name, niveau=self.niveau_b.name,
		)
		self.assertTrue(resultat["status"])
		# Plus d'usurpation : la séance est créée au nom du coordinateur B.
		self.assertEqual(frappe.db.get_value("Planning Item", resultat["data"]["name"], "owner"), user_b)
		self.assertEqual(frappe.session.user, user_b)

	def test_coordinateur_refuse_hors_perimetre(self):
		frappe.set_user(self.coordinateur(self.coord_b))
		with self.assertRaises(frappe.PermissionError):
			planning_calendar.create_planning(
				self.annee.name, self.tronc.name, "Cours Magistral (CM)", "2026-11-04", self.matin,
				filiere=self.filiere_a.name, niveau=self.niveau_a.name,
			)
		# Cours qui n'est pas au programme de la classe B.
		with self.assertRaises(frappe.ValidationError):
			planning_calendar.create_planning(
				self.annee.name, self.cours_a1.name, "Cours Magistral (CM)", "2026-11-04", self.matin,
				filiere=self.filiere_b.name, niveau=self.niveau_b.name,
			)

	def test_as_coordinator_ne_change_plus_l_utilisateur(self):
		with planning_permission.as_coordinator({"acting_user": "Guest"}):
			self.assertEqual(frappe.session.user, "Administrator")

	# ------------------------------------------------------------------ #
	#  Email
	# ------------------------------------------------------------------ #
	def faux_pdf(self, filtres):
		"""PDF factice, mais séances réelles : vérifie le périmètre envoyé."""
		from datetime import date

		items = planning_calendar.get_week_planning(
			academic_year=filtres["academic_year"], week_start=filtres["week_start"],
			filiere=filtres.get("filiere"), niveau=filtres.get("niveau"), teacher=filtres.get("teacher"),
		)
		return b"%PDF", "Planning.pdf", items, date(2026, 11, 2), date(2026, 11, 7)

	def envoyer(self, filtres, **options):
		with (
			patch.object(planning_calendar_email.planning_calendar_pdf, "generate_planning_pdf", side_effect=self.faux_pdf),
			patch.object(planning_calendar_email.frappe, "sendmail") as sendmail,
		):
			resultat = planning_calendar_email.send_planning_to_mail(filtres, **options)
		return resultat, sendmail

	def test_envoi_email_ne_plante_plus(self):
		filtres = {"academic_year": self.annee.name, "week_start": "2026-11-02", "teacher": self.prof1.name}
		resultat, sendmail = self.envoyer(filtres, to_teacher=1)
		self.assertEqual(resultat["sent"], 1)
		sendmail.assert_called_once()

	def test_chaque_enseignant_recoit_tout_son_planning_et_seulement_le_sien(self):
		# prof2 : a2 (classe A) + tronc commun (A et B) + un cours propre à la classe B.
		cours_b = make_teaching_unit(make_course(), self.annee, self.filiere_b, self.niveau_b)
		cours_b.append("table_enseignant", {"enseignant": self.prof2.name, "type_de_cours": "Cours Magistral (CM)"})
		cours_b.save(ignore_permissions=True)
		self.seance(self.cours_a1)
		self.seance(self.cours_a2, period=self.soir)
		self.seance(self.tronc, jour="2026-11-03")
		self.seance(cours_b, jour="2026-11-04")

		# Envoi depuis la vue de la classe A, à tous ses enseignants.
		filtres = {
			"academic_year": self.annee.name, "week_start": "2026-11-02",
			"filiere": self.filiere_a.name, "niveau": self.niveau_a.name,
		}
		resultat, sendmail = self.envoyer(filtres, to_all_teacher=1)
		self.assertEqual(resultat["sent"], 2)
		mails = {c.kwargs["recipients"][0]: c.kwargs for c in sendmail.call_args_list}
		self.assertEqual(set(mails), {self.prof1.email, self.prof2.email})

		corps_prof2 = mails[self.prof2.email]["message"]
		# prof2 reçoit aussi sa séance de la classe B (hors de la vue affichée)…
		self.assertIn(cours_b.course, corps_prof2)
		self.assertIn(self.tronc.course, corps_prof2)
		# … mais jamais le cours de prof1.
		self.assertNotIn(self.cours_a1.course, corps_prof2)
		self.assertIn(self.cours_a2.course, corps_prof2)
		corps_prof1 = mails[self.prof1.email]["message"]
		self.assertNotIn(cours_b.course, corps_prof1)

	def test_mail_contient_etablissement_et_editeur(self):
		self.seance(self.cours_a1)
		filtres = {"academic_year": self.annee.name, "week_start": "2026-11-02", "teacher": self.prof1.name}
		_resultat, sendmail = self.envoyer(filtres, to_teacher=1)
		mail = sendmail.call_args.kwargs
		self.assertIn("2 novembre", mail["subject"])
		for attendu in ("Ndewa360", "+237 6 80 91 61 59", "contact@ndewa-360.com", "Bonjour", "novembre"):
			self.assertIn(attendu, mail["message"])
		self.assertEqual(mail["attachments"][0]["fname"], "Planning.pdf")

	def test_enseignant_sans_email_signale(self):
		frappe.db.set_value("Teacher", self.prof1.name, "email", "")
		self.seance(self.cours_a1)
		self.seance(self.cours_a2, period=self.soir)
		filtres = {
			"academic_year": self.annee.name, "week_start": "2026-11-02",
			"filiere": self.filiere_a.name, "niveau": self.niveau_a.name,
		}
		resultat, sendmail = self.envoyer(filtres, to_all_teacher=1)
		self.assertEqual(resultat["sent"], 1)
		self.assertEqual(len(resultat["sans_email"]), 1)
		sendmail.assert_called_once()

	def test_pdf_enseignant_affiche_toutes_ses_seances(self):
		"""Les créneaux du calendrier de la classe (absents du calendrier par
		défaut) ne font plus disparaître les séances du PDF d'un enseignant."""
		from udshed.api import planning_calendar_pdf

		self.seance(self.cours_a2)
		self.seance(self.tronc, jour="2026-11-03", period=self.soir)
		filtres = {"academic_year": self.annee.name, "week_start": "2026-11-02", "teacher": self.prof2.name}
		with patch.object(planning_calendar_pdf, "_pdf", side_effect=lambda html: html):
			html, nom, items, _debut, _fin = planning_calendar_pdf.generate_planning_pdf(filtres)
		self.assertEqual(len(items), 2)
		for cours in (self.cours_a2, self.tronc):
			self.assertIn(frappe.db.get_value("Course", cours.course, "intitule") or cours.course, html)
		self.assertIn("novembre", nom)
		self.assertIn("Ndewa360", html)

	def test_planning_enseignant_inclut_cours_lie(self):
		if not frappe.get_meta("Teaching Unit").has_field("groupe_cours_commun"):
			self.skipTest("groupe_cours_commun absent")
		# Cours de la classe B lié à a1 (même enseignement), planifié via la grille B.
		cours_b = make_teaching_unit(make_course(), self.annee, self.filiere_b, self.niveau_b)
		groupe = "G-" + frappe.generate_hash(length=6)
		for cours in (self.cours_a1, cours_b):
			frappe.db.set_value("Teaching Unit", cours.name, "groupe_cours_commun", groupe)
		self.seance(cours_b)
		items = planning_calendar.get_week_planning(self.annee.name, "2026-11-02", teacher=self.prof1.name)
		self.assertEqual([i.cours for i in items], [cours_b.name])
		self.assertEqual(len(items[0]["classes"]), 2)
