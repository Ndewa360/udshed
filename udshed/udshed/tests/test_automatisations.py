# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Automatisations : moteur de notifications, attentes (file « À faire », relances,
escalade), calendrier, frais et blocages, assiduité, stages et soutenances."""

import frappe
from unittest.mock import patch

from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from udshed.notifications import emettre, envoyer_resumes, synchroniser_catalogue
from udshed.notifications import attentes, taches
from udshed.udshed._fixture_factory import (
	make_academic_year,
	make_agent_scolarite,
	make_calendar_planing,
	make_course,
	make_faculty,
	make_field_of_study,
	make_level,
	make_student,
	make_teacher,
	make_teaching_unit,
	make_user_with_role,
	unique_code,
)
from udshed.utils import frais


def journal(code, **filtres):
	return frappe.get_all("Journal Notification", filters={"regle": code, **filtres},
						  fields=["destinataire", "canal", "statut", "cle", "utilisateur"])


class TestAutomatisations(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		synchroniser_catalogue()
		cls.annee = make_academic_year("2026", "2027")
		cls.cal = make_calendar_planing()
		cls.faculte = make_faculty()
		cls.coord_teacher = make_teacher()
		cls.coord_user = make_user_with_role("Coordonateur")
		frappe.db.set_value("Teacher", cls.coord_teacher.name, "user", cls.coord_user.name)
		cls.filiere = make_field_of_study(cls.faculte, cls.cal, cls.coord_teacher)
		cls.niveau = make_level(cls.filiere)
		cls.doyen = make_user_with_role("Doyen")
		frappe.db.set_value("Faculty", cls.faculte.name, "doyen", cls.doyen.name)
		cls.agent = make_agent_scolarite(cls.filiere)
		cls.student = make_student(cls.filiere, cls.niveau)
		cls.user_etudiant = make_user_with_role("Student")
		frappe.db.set_value("Student", cls.student.name, "utilisateur", cls.user_etudiant.name)
		cls.prof = make_teacher()
		cls.user_prof = make_user_with_role("Teacher")
		cls.daa = make_user_with_role("Directeur des Affaires Académiques")

	def setUp(self):
		# Pas de compte d'envoi sur le site de test : l'envoi d'e-mail est simulé.
		patcher = patch("frappe.sendmail")
		patcher.start()
		self.addCleanup(patcher.stop)

	# ------------------------------------------------------------------ moteur
	def test_emettre_canaux_journal_et_cle(self):
		cle = unique_code("K")
		n = emettre("requete_reponse", [self.user_etudiant.name], "Sujet test", "Message", cle=cle)
		self.assertEqual(n, 2)  # application + e-mail
		self.assertEqual({j.canal for j in journal("requete_reponse", cle=cle)}, {"Application", "E-mail"})
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": self.user_etudiant.name, "subject": "Sujet test"}))
		# Même clé : rien n'est renvoyé.
		self.assertEqual(emettre("requete_reponse", [self.user_etudiant.name], "Sujet test", cle=cle), 0)

	def test_preference_et_obligatoire(self):
		user = self.user_prof
		frappe.get_doc({"doctype": "Preference Notification", "utilisateur": user.name, "regle": "affectation_cours",
						"application": 1, "email": 0, "sms": 0}).insert(ignore_permissions=True)
		cle = unique_code("K")
		emettre("affectation_cours", [user.name], "Affectation", cle=cle)
		self.assertEqual({j.canal for j in journal("affectation_cours", cle=cle)}, {"Application"})
		# Une notification obligatoire ignore les préférences.
		frappe.get_doc({"doctype": "Preference Notification", "utilisateur": user.name, "regle": "saisie_rappel",
						"application": 0, "email": 0}).insert(ignore_permissions=True)
		cle = unique_code("K")
		emettre("saisie_rappel", [user.name], "Rappel", cle=cle)
		self.assertEqual({j.canal for j in journal("saisie_rappel", cle=cle)}, {"Application", "E-mail"})

	def test_texte_personnalise(self):
		frappe.db.set_value("Regle Notification", "requete_reponse", "sujet_personnalise", "[Udshed] {{ sujet }}")
		frappe.clear_document_cache("Regle Notification", "requete_reponse")
		cle = unique_code("K")
		emettre("requete_reponse", [self.user_etudiant.name], "Bonjour", cle=cle)
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": self.user_etudiant.name,
															  "subject": "[Udshed] Bonjour"}))
		frappe.db.set_value("Regle Notification", "requete_reponse", "sujet_personnalise", "")
		frappe.clear_document_cache("Regle Notification", "requete_reponse")

	def test_resume_quotidien(self):
		cle = unique_code("K")
		emettre("requete_soumise", [self.agent.name], "Requête X", cle=cle)  # e-mail regroupé (personnel)
		statuts = {j.canal: j.statut for j in journal("requete_soumise", cle=cle)}
		self.assertEqual(statuts, {"Application": "Envoyé", "E-mail": "En attente du résumé"})
		envoyer_resumes()
		self.assertEqual(journal("requete_soumise", cle=cle, canal="E-mail")[0].statut, "Regroupé")

	# ------------------------------------------------------------------ attentes
	def _requete(self, jours):
		doc = frappe.get_doc({"doctype": "Requete Etudiant", "student": self.student.name, "type_requete": "Autre",
							  "objet": unique_code("Objet"), "description": "Test", "statut": "Soumise", "academic_year": self.annee.name})
		doc.flags.ignore_validate = True
		doc.insert(ignore_permissions=True)
		frappe.db.set_value("Requete Etudiant", doc.name, "creation", add_days(now_datetime(), -jours),
							update_modified=False)
		return doc

	def test_file_a_faire_relance_et_escalade(self):
		req = self._requete(6)
		groupes = attentes.a_faire(self.agent.name)
		self.assertTrue(any(any(e["lien"].endswith(req.name) for e in g["elements"]) for g in groupes))
		# Le doyen n'est pas responsable, mais l'attente dépasse l'escalade (5 jours) : il la voit.
		escalades = [g for g in attentes.a_faire(self.doyen.name) if g["escalade"]]
		self.assertTrue(escalades)
		attentes.relancer()
		ref = f"Requete Etudiant:{req.name}"
		self.assertTrue(journal("requete_soumise", cle=f"relance:{ref}:3", destinataire=self.agent.name))
		self.assertTrue(journal("requete_soumise", cle=f"escalade:{ref}", destinataire=self.doyen.name))
		# Une fois traitée, l'attente disparaît.
		frappe.db.set_value("Requete Etudiant", req.name, "statut", "Répondue")
		self.assertFalse(any(any(e["lien"].endswith(req.name) for e in g["elements"])
							 for g in attentes.a_faire(self.agent.name)))

	def test_derogation_attend_le_doyen(self):
		d = frappe.get_doc({"doctype": "Derogation Saisie", "teaching_unit": self._ue(), "type_evaluation": "Contrôle continu",
							"academic_year": self.annee.name, "semestre": "Semestre 1", "filiere": self.filiere.name,
							"faculte": self.faculte.name, "statut": "Demandée", "motif": "Oubli",
							"demande_le": now_datetime()})
		d.flags.ignore_mandatory = True
		d.insert(ignore_permissions=True)
		groupes = attentes.a_faire(self.doyen.name)
		self.assertTrue(any(g["critique"] and any(e["lien"].endswith(d.name) for e in g["elements"]) for g in groupes))

	def _ue(self):
		return make_teaching_unit(make_course(), self.annee, self.filiere, self.niveau).name

	def test_affectation_enseignant_notifiee(self):
		tu = frappe.get_doc("Teaching Unit", self._ue())
		prof = self.prof
		tu.append("table_enseignant", {"enseignant": prof.name, "type_de_cours": "Cours Magistral (CM)"})
		tu.save(ignore_permissions=True)
		self.assertTrue(journal("affectation_cours", cle=f"{tu.name}:{prof.name}:Cours Magistral (CM)"))

	# ------------------------------------------------------------------ calendrier
	def test_jalon_synchronise_et_signale(self):
		p = frappe.get_doc({"doctype": "Periode Saisie Notes", "academic_year": self.annee.name, "semestre": "Semestre 1",
							"type_evaluation": "Contrôle continu", "faculte": self.faculte.name,
							"ouverture": add_days(now_datetime(), 1), "fermeture": add_days(now_datetime(), 10)})
		p.insert(ignore_permissions=True)
		jalon = frappe.db.get_value("Jalon Academique", {"reference_doctype": "Periode Saisie Notes",
														 "reference_name": p.name}, ["statut", "type_jalon"], as_dict=True)
		self.assertEqual((jalon.statut, jalon.type_jalon), ("Préparé", "Saisie des notes"))
		daa = self.daa
		j = frappe.get_doc({"doctype": "Jalon Academique", "academic_year": self.annee.name, "type_jalon": "Délibération",
							"libelle": "Délibérations S2", "date_debut": add_days(nowdate(), 5)}).insert(ignore_permissions=True)
		taches.jalons_non_prepares()
		self.assertTrue(journal("jalon_non_prepare", cle=f"{j.name}:j-7", destinataire=daa.name))

	# ------------------------------------------------------------------ frais
	def test_frais_paiement_blocage(self):
		frais_doc = frappe.get_doc({"doctype": "Frais Scolarite", "academic_year": self.annee.name, "libelle": "Tranche 1",
									"montant": 50000, "date_echeance": add_days(nowdate(), -3),
									"filiere": self.filiere.name}).insert(ignore_permissions=True)
		echeances = frais.generer_echeances(self.student.name, self.annee.name, self.filiere.name, "Licence 1")
		self.assertEqual(len(echeances), 1)
		self.assertEqual(frais.generer_echeances(self.student.name, self.annee.name, self.filiere.name, "Licence 1"), [])
		e = frappe.get_doc("Echeance Etudiant", echeances[0])
		self.assertEqual((e.statut, e.reste), ("En retard", 50000))
		frappe.db.set_single_value("Udshed Setting", "activer_blocage_frais", 1)
		try:
			frappe.set_user(self.user_etudiant.name)
			with self.assertRaises(frappe.ValidationError):
				frais.exiger_aucun_blocage(self.student.name, "La réinscription")
			frappe.set_user("Administrator")
			frappe.get_doc({"doctype": "Paiement Etudiant", "student": self.student.name, "echeance": e.name,
							"montant": 20000, "date_paiement": nowdate(), "mode": "Mobile Money"}).insert(ignore_permissions=True)
			e.reload()
			self.assertEqual((e.montant_paye, e.reste, e.statut), (20000, 30000, "En retard"))
			with self.assertRaises(frappe.ValidationError):
				frappe.get_doc({"doctype": "Paiement Etudiant", "student": self.student.name, "echeance": e.name,
								"montant": 40000, "date_paiement": nowdate(), "mode": "Espèces"}).insert(ignore_permissions=True)
			# Décision du comptable : l'impayé ne bloque plus.
			e.blocage_leve, e.motif_derogation = 1, "Bourse en attente"
			e.save(ignore_permissions=True)
			frappe.set_user(self.user_etudiant.name)
			frais.exiger_aucun_blocage(self.student.name, "La réinscription")
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_single_value("Udshed Setting", "activer_blocage_frais", 0)
		self.assertTrue(journal("paiement_recu", destinataire=self.user_etudiant.name))
		del frais_doc

	# ------------------------------------------------------------------ assiduité
	def test_appel_et_seuil_absences(self):
		tu = self._ue()
		frappe.db.set_single_value("Udshed Setting", "seuil_absences", 2)
		periode = self.cal.append("heure_planification", {"libelle": "Matin", "heure_de_debut": "08:00:00",
														   "heure_de_fin": "12:00:00"})
		self.cal.save(ignore_permissions=True)
		try:
			for jour in (-3, -2):
				item = frappe.get_doc({"doctype": "Planning Item", "cours": tu, "type": "Cours Magistral (CM)",
									   "date": add_days(now_datetime(), jour), "period": periode.name,
									   "academic_year": self.annee.name, "mode": "En ligne"})
				item.flags.ignore_validate = True
				item.insert(ignore_permissions=True)
				appel = frappe.get_doc({"doctype": "Appel Seance", "planning_item": item.name,
										"presences": [{"student": self.student.name, "statut": "Absent"}]})
				appel.insert(ignore_permissions=True)
			self.assertEqual(appel.absents, 1)
			self.assertTrue(journal("absences_seuil", cle=f"{self.student.name}:{tu}:2"))
		finally:
			frappe.db.set_single_value("Udshed Setting", "seuil_absences", 0)

	# ------------------------------------------------------------------ stages
	def test_stage_validation_humaine_et_soutenance(self):
		stage = frappe.get_doc({"doctype": "Stage Etudiant", "student": self.student.name, "academic_year": self.annee.name,
								"type_travail": "Mémoire", "sujet": "Analyse des réseaux"}).insert(ignore_permissions=True)
		self.assertTrue(journal("stage_a_valider", destinataire=self.coord_user.name))
		self.assertTrue(any(any(e["lien"].endswith(stage.name) for e in g["elements"])
							for g in attentes.a_faire(self.coord_user.name)))
		# Un utilisateur sans rôle de décision ne valide pas.
		autre = self.user_prof
		frappe.set_user(autre.name)
		try:
			stage.statut = "Validé"
			with self.assertRaises(frappe.PermissionError):
				stage.save(ignore_permissions=True)
		finally:
			frappe.set_user("Administrator")
		stage.reload()
		stage.statut = "Validé"
		stage.save(ignore_permissions=True)
		self.assertTrue(journal("stage_decision", destinataire=self.user_etudiant.name))
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Soutenance", "stage": stage.name, "date_soutenance": add_days(now_datetime(), 3),
							"jury": [{"enseignant": self.coord_teacher.name, "role": "Examinateur"}]}).insert(ignore_permissions=True)
		sou = frappe.get_doc({"doctype": "Soutenance", "stage": stage.name, "date_soutenance": add_days(now_datetime(), 3),
							  "jury": [{"enseignant": self.coord_teacher.name, "role": "Président"}]}).insert(ignore_permissions=True)
		self.assertTrue(journal("soutenance_programmee", destinataire=self.user_etudiant.name))
		sou.statut, sou.note = "Tenue", 15
		sou.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Stage Etudiant", stage.name, "statut"), "Soutenu")

	# ------------------------------------------------------------------ publication programmée
	def test_programmation_publication(self):
		from udshed.notifications.api import programmer_publication

		session = frappe.get_doc({"doctype": "Session Examen", "academic_year": self.annee.name, "calendar": self.cal.name,
								  "type_dexamen": "Examen de session normal", "semestre": "Semestre 1",
								  "date_debut": add_days(nowdate(), -10), "date_de_fin": add_days(nowdate(), -2),
								  "statut": "Brouillon"}).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			programmer_publication(session.name, add_to_date(now_datetime(), hours=-1))
		programmer_publication(session.name, add_to_date(now_datetime(), hours=2))
		self.assertEqual(frappe.db.get_value("Session Examen", session.name, "programme_par"), "Administrator")
		programmer_publication(session.name, "")
		self.assertIsNone(frappe.db.get_value("Session Examen", session.name, "publier_le"))
