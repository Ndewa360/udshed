# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Réinscription annuelle et progression académique après publication.

Le parcours complet est exercé : notes « Validé » -> `publier_session`
(publication officielle réelle : résultats puis progression) -> réinscription
par l'étudiant connecté via `submit_reinscription`.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from udshed.api import reregistration as rr
from udshed.api.progression import (
	STATUT_ADMINISTRATIF,
	STATUT_ADMIS,
	STATUT_ATTENTE,
	STATUT_FIN,
	STATUT_REDOUBLEMENT,
	calculer_progression,
)
from udshed.api.saisie_notes import publier_session
from udshed.udshed._fixture_factory import (
	make_academic_year,
	make_calendar_planing,
	make_course,
	make_faculty,
	make_field_of_study,
	make_level,
	make_planning_item,
	make_session_examen,
	make_session_examen_note,
	make_student,
	make_teacher,
	make_teaching_unit,
	make_user_with_role,
	seed_formule,
	seed_grille_grades,
)
from udshed.udshed.doctype.session_reinscription.session_reinscription import mettre_a_jour_statuts

TYPE_NORMALE = "Examen de session normal"
REUSSITE, ECHEC = 15, 4
REFUS = (frappe.ValidationError, frappe.PermissionError)

FAMILLE = {
	"nom_prenom_pere": "Père Initial",
	"pere_telephone": "+237677000001",
	"nom_prenom_mere": "Mère Initiale",
	"telephone_mere": "+237677000002",
	"activites_sportives": "Football",
	"dernier_etablissement": "Lycée de Dschang",
}


class TestReinscriptionProgression(IntegrationTestCase):

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Les API testées committent : neutralisé pour que tout soit annulé en fin de classe.
		cls._commit = frappe.db.commit
		frappe.db.commit = lambda *args, **kwargs: None
		seed_grille_grades()
		seed_formule("Licence", ["Controle Continu(CC)", "Examen"], [40, 60])
		cls.y_src = make_academic_year("2028", "2029")
		cls.y_cib = make_academic_year("2029", "2030")
		# Les données existantes ne doivent pas interférer (une seule session ouverte).
		frappe.db.set_value("Session Reinscription", {"statut": "Ouverte"}, "statut", "Fermée")
		cls.session = frappe.get_doc({
			"doctype": "Session Reinscription",
			"academic_year": cls.y_cib.name,
			"statut": "Ouverte",
			"date_ouverture": add_days(nowdate(), -5),
			"date_cloture": add_days(nowdate(), 30),
		}).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.commit = cls._commit
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	# ------------------------------------------------------------------ #
	#  Fixtures
	# ------------------------------------------------------------------ #
	def _parcours(self, note_s1=REUSSITE, note_s2=REUSSITE, niveaux=("Licence 1", "Licence 2", "Licence 3"),
				  niveau_source="Licence 1", publier=("Semestre 1", "Semestre 2")):
		"""Étudiant inscrit en `niveau_source` l'année source, notes saisies et validées."""
		p = frappe._dict()
		p.cal = make_calendar_planing()
		p.fos = make_field_of_study(make_faculty(), p.cal, make_teacher())
		p.levels = {lab: make_level(p.fos, level=lab, order=i + 1) for i, lab in enumerate(niveaux)}
		src = p.levels[niveau_source]

		p.tus = {}
		for semestre in ("Semestre 1", "Semestre 2"):
			tu = make_teaching_unit(make_course(semestre=semestre), self.y_src, p.fos, src, credits=6)
			frappe.db.set_value("Teaching Unit", tu.name, "semestre", semestre)
			make_planning_item(tu, self.y_src, p.cal, type_dexamen=TYPE_NORMALE)
			p.tus[semestre] = tu

		suivant = niveaux[niveaux.index(niveau_source) + 1] if niveau_source != niveaux[-1] else None
		if suivant:
			p.tu_cible = make_teaching_unit(make_course(), self.y_cib, p.fos, p.levels[suivant], credits=6)

		p.student = make_student(p.fos, src, niveau_actuel=niveau_source)
		p.user = make_user_with_role("Student")
		frappe.db.set_value("Student", p.student.name, "utilisateur", p.user.name)

		ia = frappe.get_doc({
			"doctype": "Inscription Academique",
			"matricule": p.student.name,
			"nom_prenom": f"{p.student.nom} {p.student.prenom}",
			"email": p.student.email,
			"telephone": "+237655000000",
			"annee_academique": self.y_src.name,
			"filiere": p.fos.name,
			"classe": niveau_source,
			"sexe": "Masculin",
			**FAMILLE,
		})
		ia.flags.ignore_validate = True
		ia.flags.ignore_mandatory = True
		ia.insert(ignore_permissions=True)
		p.ia = ia

		p.sessions = {}
		for semestre, note in (("Semestre 1", note_s1), ("Semestre 2", note_s2)):
			sess = make_session_examen(self.y_src, p.cal, filiere=p.fos, niveau=src, semestre=semestre)
			make_session_examen_note(sess, p.student, p.tus[semestre], note_cc=note, note_examen=note,
									 statut="Validé")
			p.sessions[semestre] = sess

		for semestre in publier:
			publier_session(p.sessions[semestre].name)
		return p

	def _progression(self, p):
		name = frappe.db.get_value("Progression Academique", {"student": p.student.name}, "name")
		return frappe.get_doc("Progression Academique", name) if name else None

	def _soumettre(self, p, **kwargs):
		frappe.set_user(p.user.name)
		try:
			return rr.submit_reinscription(p.student.name, self.session.name, "Les deux", **kwargs)
		finally:
			frappe.set_user("Administrator")

	def _instantane(self, doctype, filters, champs):
		return [tuple(r.values()) for r in frappe.get_all(doctype, filters=filters, fields=champs, order_by="name")]

	# ------------------------------------------------------------------ #
	#  1-2. Récupération et modification des informations
	# ------------------------------------------------------------------ #
	def test_01_informations_reprises_du_dossier(self):
		p = self._parcours()
		# Réinscription automatique (inscription initiale) sans données famille :
		# chaque champ retombe sur la valeur non vide la plus récente.
		auto = frappe.get_doc({
			"doctype": "Academic Reregistration", "student": p.student.name,
			"nom_prenom": "x", "academic_year": self.y_src.name, "filiere": p.fos.name,
			"niveau": "Licence 1", "semestre": "Les deux", "reinscription_session": self.session.name,
		})
		auto.flags.ignore_validate = True
		auto.insert(ignore_permissions=True)

		frappe.set_user(p.user.name)
		data = rr.get_student_by_matricule()
		self.assertEqual(data["name"], p.student.name)
		for champ, valeur in FAMILLE.items():
			self.assertEqual(data[champ], valeur, champ)
		self.assertEqual(data["telephone"], "+237655000000")
		self.assertIn("telephone", data["champs_modifiables"])
		self.assertIn("nom_prenom_pere", data["champs_modifiables"])
		for verrouille in ("nom_prenom", "email", "niveau", "filiere", "dernier_etablissement"):
			self.assertNotIn(verrouille, data["champs_modifiables"])

	def test_02_champs_autorises_modifiables_sans_toucher_l_historique(self):
		p = self._parcours()
		champs_ra = ["name", "note_finale", "statut", "modified"]
		ra_avant = self._instantane("Resultat Academique", {"student": p.student.name}, champs_ra)
		ia_avant = frappe.db.get_value("Inscription Academique", p.ia.name,
									   ["modified", "nom_prenom_pere", "telephone"], as_dict=True)

		res = self._soumettre(p, infos={"telephone": "+237699111222", "nom_prenom_pere": "Père Modifié"})
		self.assertTrue(res["status"], res)
		rer = frappe.get_doc("Academic Reregistration", res["name"])
		self.assertEqual(rer.telephone, "+237699111222")
		self.assertEqual(rer.nom_prenom_pere, "Père Modifié")
		self.assertEqual(rer.nom_prenom_mere, FAMILLE["nom_prenom_mere"])
		self.assertEqual(rer.dernier_etablissement, FAMILLE["dernier_etablissement"])

		# 10. Anciennes inscriptions et résultats historiques inchangés
		ia_apres = frappe.db.get_value("Inscription Academique", p.ia.name,
									   ["modified", "nom_prenom_pere", "telephone"], as_dict=True)
		self.assertEqual(ia_avant, ia_apres)
		self.assertEqual(ra_avant, self._instantane("Resultat Academique", {"student": p.student.name}, champs_ra))
		self.assertTrue(ra_avant)

		# 9. Même dossier étudiant, matricule conservé
		self.assertEqual(rer.student, p.student.name)
		self.assertEqual(frappe.db.get_value("Student", p.student.name, "matricule"), p.student.matricule)
		self.assertEqual(frappe.db.count("Student", {"email": p.student.email}), 1)

	# ------------------------------------------------------------------ #
	#  3. Niveau / filière verrouillés côté serveur
	# ------------------------------------------------------------------ #
	def test_03_niveau_et_filiere_non_modifiables(self):
		p = self._parcours()
		with self.assertRaises(frappe.PermissionError):
			self._soumettre(p, niveau="Licence 3")
		with self.assertRaises(frappe.ValidationError):
			self._soumettre(p, infos={"nom_prenom": "Pirate"})
		with self.assertRaises(frappe.ValidationError):
			self._soumettre(p, infos={"niveau": "Licence 3"})

		frappe.set_user(p.user.name)
		with self.assertRaises(frappe.PermissionError):
			rr.get_reregistration_grid(p.student.name, self.session.name, "Les deux", niveau="Licence 3")
		# Requête directe (contourne l'API) : refusée par le contrôleur
		for niveau, filiere in (("Licence 3", p.fos.name), ("Licence 2", "AUTRE-FILIERE")):
			doc = frappe.get_doc({
				"doctype": "Academic Reregistration", "student": p.student.name, "nom_prenom": "x",
				"reinscription_session": self.session.name, "academic_year": self.y_cib.name,
				"filiere": filiere, "niveau": niveau, "semestre": "Les deux",
			})
			with self.assertRaises(REFUS):
				doc.insert(ignore_permissions=True)
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.exists("Academic Reregistration", {"student": p.student.name}))

	# ------------------------------------------------------------------ #
	#  4-7. Progression déclenchée par la publication
	# ------------------------------------------------------------------ #
	def test_04_reussite_passe_au_niveau_superieur(self):
		p = self._parcours(publier=())
		# Notes validées mais non publiées : aucune progression
		self.assertIsNone(self._progression(p))
		publier_session(p.sessions["Semestre 1"].name)
		publier_session(p.sessions["Semestre 2"].name)

		prog = self._progression(p)
		self.assertEqual(prog.statut, STATUT_ADMIS)
		self.assertEqual(prog.niveau_cible, "Licence 2")
		self.assertEqual(prog.filiere_cible, p.fos.name)
		self.assertEqual(prog.annee_cible, self.y_cib.name)
		self.assertEqual(prog.inscription_source, p.ia.name)
		self.assertEqual(prog.session_publication, p.sessions["Semestre 2"].name)

		res = self._soumettre(p)
		rer = frappe.get_doc("Academic Reregistration", res["name"])
		self.assertEqual((rer.niveau, rer.filiere, rer.academic_year), ("Licence 2", p.fos.name, self.y_cib.name))
		self.assertEqual(frappe.db.get_value("Progression Academique", prog.name, "reinscription"), rer.name)

	def test_05_echec_suit_la_regle_de_redoublement(self):
		p = self._parcours(note_s1=ECHEC, note_s2=ECHEC)
		prog = self._progression(p)
		self.assertEqual(prog.statut, STATUT_REDOUBLEMENT)
		self.assertEqual(prog.niveau_cible, "Licence 1")
		self.assertEqual(prog.decision_notes, "Ajourné")

		res = self._soumettre(p)
		rer = frappe.get_doc("Academic Reregistration", res["name"])
		self.assertEqual(rer.niveau, "Licence 1")
		dettes = [c for c in rer.cours_inscrits if c.source == "dette"]
		self.assertEqual(len(dettes), 2)

	def test_06_resultats_non_publies_bloquent(self):
		p = self._parcours(publier=("Semestre 1",))
		prog = self._progression(p)
		self.assertEqual(prog.statut, STATUT_ATTENTE)
		self.assertFalse(prog.niveau_cible)
		self.assertIn("Semestre 2", prog.motif)

		frappe.set_user(p.user.name)
		apercu = rr.get_reregistration_preview(p.student.name, self.session.name)
		self.assertTrue(apercu["bloque"])
		self.assertIn("pas encore été publiés", apercu["message"])
		with self.assertRaisesRegex(frappe.ValidationError, "pas encore été publiés"):
			rr.submit_reinscription(p.student.name, self.session.name, "Les deux")

	def test_07_publication_repetee_sans_double_progression(self):
		p = self._parcours()
		prog = self._progression(p)
		versions = frappe.db.count("Version", {"ref_doctype": "Progression Academique", "docname": prog.name})

		publier_session(p.sessions["Semestre 2"].name)
		publier_session(p.sessions["Semestre 1"].name)
		calculer_progression(p.student.name, self.y_src.name)

		self.assertEqual(frappe.db.count("Progression Academique", {"student": p.student.name}), 1)
		apres = self._progression(p)
		self.assertEqual((apres.name, apres.niveau_cible, apres.modified), (prog.name, "Licence 2", prog.modified))
		self.assertEqual(
			frappe.db.count("Version", {"ref_doctype": "Progression Academique", "docname": prog.name}), versions)

		# Après la réinscription, une nouvelle publication ne touche plus la progression
		self._soumettre(p)
		publier_session(p.sessions["Semestre 2"].name)
		self.assertEqual(frappe.db.count("Progression Academique", {"student": p.student.name}), 1)
		self.assertEqual(frappe.db.count("Academic Reregistration", {"student": p.student.name}), 1)

	# ------------------------------------------------------------------ #
	#  8. Seconde réinscription la même année
	# ------------------------------------------------------------------ #
	def test_08_seconde_reinscription_refusee(self):
		p = self._parcours()
		premiere = self._soumettre(p)
		self.assertTrue(premiere["status"])
		seconde = self._soumettre(p)
		self.assertFalse(seconde["status"])
		self.assertIn("déjà réinscrit", seconde["message"])
		self.assertEqual(seconde["name"], premiere["name"])

		doc = frappe.get_doc({
			"doctype": "Academic Reregistration", "student": p.student.name, "nom_prenom": "x",
			"reinscription_session": self.session.name, "academic_year": self.y_cib.name,
			"filiere": p.fos.name, "niveau": "Licence 2", "semestre": "Les deux",
		})
		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)
		self.assertEqual(frappe.db.count("Academic Reregistration", {"student": p.student.name}), 1)

	# ------------------------------------------------------------------ #
	#  11. Fiche PDF
	# ------------------------------------------------------------------ #
	def test_09_telechargement_fiche(self):
		p = self._parcours()
		res = self._soumettre(p)
		frappe.set_user(p.user.name)
		frappe.local.response = frappe._dict()
		rr.telecharger_fiche_reinscription(res["name"])
		self.assertEqual(frappe.local.response.type, "pdf")
		self.assertTrue(frappe.local.response.filecontent.startswith(b"%PDF"))
		self.assertIn(res["name"], frappe.local.response.filename)

	# ------------------------------------------------------------------ #
	#  12. Fin de parcours / niveau suivant absent
	# ------------------------------------------------------------------ #
	def test_10_fin_de_parcours_sans_niveau_inexistant(self):
		p = self._parcours(niveau_source="Licence 3")
		prog = self._progression(p)
		self.assertEqual(prog.statut, STATUT_FIN)
		self.assertFalse(prog.niveau_cible)
		self.assertEqual(len(frappe.get_doc("Field of study", p.fos.name).field_of_study_level), 3)
		with self.assertRaisesRegex(frappe.ValidationError, "dernier niveau"):
			self._soumettre(p)

	def test_11_niveau_suivant_non_configure_signale_a_la_scolarite(self):
		p = self._parcours(niveaux=("Licence 1",))
		prog = self._progression(p)
		self.assertEqual(prog.statut, STATUT_ADMINISTRATIF)
		self.assertIn("Licence 2", prog.motif)
		self.assertFalse(prog.niveau_cible)
		with self.assertRaisesRegex(frappe.ValidationError, "décision de la scolarité"):
			self._soumettre(p)

	# ------------------------------------------------------------------ #
	#  13. Permissions étudiant / scolarité
	# ------------------------------------------------------------------ #
	def test_12_permissions_etudiants(self):
		a = self._parcours()
		b = self._parcours()
		rer_a = self._soumettre(a)["name"]

		frappe.set_user(b.user.name)
		for appel in (
			lambda: rr.get_student_by_matricule(a.student.name),
			lambda: rr.get_reregistration_preview(a.student.name, self.session.name),
			lambda: rr.get_reregistration_grid(a.student.name, self.session.name, "Les deux"),
			lambda: rr.telecharger_fiche_reinscription(rer_a),
			lambda: rr.submit_reinscription(a.student.name, self.session.name, "Les deux"),
		):
			with self.assertRaises(REFUS):
				appel()
		self.assertNotIn(rer_a, frappe.get_list("Academic Reregistration", pluck="name"))
		self.assertFalse(frappe.has_permission("Academic Reregistration", doc=rer_a))
		self.assertFalse(frappe.get_list("Progression Academique", filters={"student": a.student.name}))

		frappe.set_user(a.user.name)
		self.assertEqual(frappe.get_list("Academic Reregistration", pluck="name"), [rer_a])
		self.assertTrue(frappe.has_permission("Academic Reregistration", doc=rer_a))

		# Ancien Web Form public : un invité ne peut rien créer
		frappe.set_user("Guest")
		doc = frappe.get_doc({
			"doctype": "Academic Reregistration", "student": b.student.name, "nom_prenom": "x",
			"reinscription_session": self.session.name, "academic_year": self.y_cib.name,
			"filiere": b.fos.name, "niveau": "Licence 2", "semestre": "Les deux",
		})
		with self.assertRaises(frappe.PermissionError):
			doc.insert(ignore_permissions=True)

	def test_13_correction_par_la_scolarite_tracee(self):
		p = self._parcours(niveaux=("Licence 1",))
		prog = self._progression(p)

		frappe.set_user(p.user.name)
		prog.statut, prog.niveau_cible, prog.filiere_cible = STATUT_REDOUBLEMENT, "Licence 1", p.fos.name
		prog.motif_correction = "tentative"
		with self.assertRaises(frappe.PermissionError):
			prog.save()

		agent = make_user_with_role("Agent de scolarité")
		frappe.set_user(agent.name)
		prog = frappe.get_doc("Progression Academique", prog.name)
		prog.statut, prog.niveau_cible, prog.filiere_cible = STATUT_REDOUBLEMENT, "Licence 1", p.fos.name
		with self.assertRaisesRegex(frappe.ValidationError, "motif"):
			prog.save()
		prog = frappe.get_doc("Progression Academique", prog.name)
		prog.statut, prog.niveau_cible, prog.filiere_cible = STATUT_REDOUBLEMENT, "Licence 1", p.fos.name
		prog.motif_correction = "Décision du jury du 12/07"
		prog.save(ignore_version=False)  # en test, Frappe désactive l'historique par défaut
		prog.reload()
		self.assertTrue(prog.corrigee)
		self.assertEqual(prog.corrigee_par, agent.name)
		self.assertTrue(frappe.db.exists("Version", {"ref_doctype": "Progression Academique", "docname": prog.name}))
		# Niveau inexistant refusé, même pour la scolarité
		prog.niveau_cible = "Licence 2"
		with self.assertRaises(frappe.ValidationError):
			prog.save()

		frappe.set_user("Administrator")
		# Un recalcul (nouvelle publication) ne remplace pas la correction
		calculer_progression(p.student.name, self.y_src.name)
		self.assertEqual(frappe.db.get_value("Progression Academique", prog.name, "statut"), STATUT_REDOUBLEMENT)

		res = self._soumettre(p)
		self.assertEqual(frappe.db.get_value("Academic Reregistration", res["name"], "niveau"), "Licence 1")
		frappe.set_user(agent.name)
		prog = frappe.get_doc("Progression Academique", prog.name)
		prog.statut = STATUT_FIN
		prog.motif_correction = "après coup"
		with self.assertRaisesRegex(frappe.ValidationError, "déjà servi"):
			prog.save()

	# ------------------------------------------------------------------ #
	#  Session : dates et ciblage
	# ------------------------------------------------------------------ #
	def test_14_session_dates_et_ciblage(self):
		p = self._parcours()
		session = frappe.get_doc("Session Reinscription", self.session.name)
		try:
			session.append("cibles", {"filiere": p.fos.name, "niveau": "Licence 2"})
			session.save(ignore_permissions=True)
			frappe.set_user(p.user.name)
			self.assertEqual(rr.get_open_sessions(), [])
			with self.assertRaisesRegex(frappe.ValidationError, "ne concerne pas"):
				rr.get_reregistration_preview(p.student.name, self.session.name)

			frappe.set_user("Administrator")
			session.cibles[0].niveau = "Licence 1"
			session.save(ignore_permissions=True)
			frappe.set_user(p.user.name)
			self.assertEqual([s["name"] for s in rr.get_open_sessions()], [self.session.name])

			frappe.set_user("Administrator")
			frappe.db.set_value("Session Reinscription", self.session.name, "date_cloture", add_days(nowdate(), -1))
			with self.assertRaisesRegex(frappe.ValidationError, "close depuis"):
				self._soumettre(p)

			# Tâche quotidienne : fermeture après clôture, ouverture des sessions planifiées
			planifiee = frappe.get_doc({
				"doctype": "Session Reinscription", "academic_year": self.y_cib.name, "statut": "Planifiée",
				"date_ouverture": nowdate(), "date_cloture": add_days(nowdate(), 10),
			}).insert(ignore_permissions=True)
			mettre_a_jour_statuts()
			self.assertEqual(frappe.db.get_value("Session Reinscription", self.session.name, "statut"), "Fermée")
			self.assertEqual(frappe.db.get_value("Session Reinscription", planifiee.name, "statut"), "Ouverte")
			frappe.db.set_value("Session Reinscription", planifiee.name, "statut", "Fermée")
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Session Reinscription", self.session.name, {
				"statut": "Ouverte", "date_cloture": add_days(nowdate(), 30)})
			frappe.db.delete("Session Reinscription Cible", {"parent": self.session.name})
		self.assertTrue(self._soumettre(p)["status"])
