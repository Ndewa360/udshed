import frappe
from frappe.model.document import Document

from udshed.utils.niveaux import niveau_precedent, cycle_niveau

from udshed.api.reregistration import (
	_admission_decision,
	_decision_annee_etudiant,
	_dettes_with_credits,
	_derniere_classe_etudiant,
	_resolve_level_name,
	_credit_from_grid,
	_teaching_units_niveau_year,
	_annee_resultats_etudiant,
	get_student_derniere_annee_academique,
	get_next_academic_year,
)


class AcademicReregistration(Document):

	def validate(self):
		self.statut = "Validée"
		self.verifier_session_ouverte()
		self.verifier_annee_suivante()
		self.verifier_doublon()
		self.calculer_niveau_precedent()
		self._evaluer_admission()
		self.verifier_progression()
		self.charger_resultats_precedents()
		self.calculer_cours_inscrits()
		self._verifier_limite_credits()

	def verifier_session_ouverte(self):
		session = frappe.db.exists("Session Reinscription", {
			"name": self.reinscription_session,
			"statut": "Ouverte"
		})
		if not session:
			frappe.throw("La session de réinscription sélectionnée n'est pas ouverte.")

	def verifier_doublon(self):
		existant = frappe.db.exists("Academic Reregistration", {
			"student": self.student,
			"academic_year": self.academic_year,
			"niveau": self.niveau,
			"name": ["!=", self.name]
		})
		if existant:
			frappe.throw("Cet étudiant est déjà réinscrit pour cette année et ce niveau.")

	def verifier_annee_suivante(self):
		if not self.is_new():
			return
		if not self.academic_year or not self.student:
			return

		annee_base = get_student_derniere_annee_academique(self.student)
		if not annee_base:
			frappe.throw("Aucune inscription initiale trouvée pour cet étudiant.")

		annee_attendue = get_next_academic_year(annee_base)
		if annee_attendue and self.academic_year != annee_attendue:
			frappe.throw(
				"Réinscription refusée : vous ne pouvez vous réinscrire que pour l'année académique {0} "
				"(suivante votre dernière inscription en {1})."
				.format(annee_attendue, annee_base)
			)

	def calculer_niveau_precedent(self):
		if not self.niveau or not self.filiere:
			return
		self.niveau_precedent = niveau_precedent(self.filiere, self.niveau)

	def _evaluer_admission(self):
		"""Évalue l'admission via la règle de crédits (50 % + ≤ 30 dettes, L3 complet, Master complet)."""
		if not self.filiere or not self.niveau:
			return

		if self._est_redoublement():
			# Redoublement : la décision se réfère au dernier niveau réellement suivi
			# (ex. l'étudiant a échoué sa Licence 2), pas au niveau précédant.
			dernier_classe = _derniere_classe_etudiant(self.student)
			annee_dernier = _annee_resultats_etudiant(self.student, dernier_classe) or self.academic_year
			self.admission_info = _admission_decision(
				self.student, self.filiere, dernier_classe, self.niveau, annee_dernier
			)
			self.decision_notes = _decision_annee_etudiant(self.student, annee_dernier) or ""
			return

		niveau_prec_label = self.niveau_precedent or niveau_precedent(self.filiere, self.niveau)
		self.admission_info = _admission_decision(
			self.student, self.filiere, niveau_prec_label, self.niveau, self.academic_year
		)
		self.decision_notes = self.admission_info.get("decision", "") or ""

	def verifier_progression(self):
		"""Vérifie l'admission via la règle de crédits."""
		if not self.filiere or not self.niveau:
			return

		admission = getattr(self, "admission_info", None)
		if not admission:
			return

		# Redoublement toujours autorisé (reprise du dernier niveau suivi)
		if self._est_redoublement():
			return

		# Master : validation complète de la Licence. L'accord du coordinateur
		# (admission_master_accordee) est rempli a posteriori pour officialiser.
		if cycle_niveau(self.niveau) == "Master":
			if not admission.get("admissible"):
				frappe.throw(
					"L'accès au Master exige la validation complète de la Licence. "
					"Crédits validés : {0}/{1}, dette : {2} crédits. {3}".format(
						admission.get("credits_validated", 0),
						admission.get("total_credits", 0),
						admission.get("debt_credits", 0),
						admission.get("motif", "")
					)
				)
			return

		# Redoublement / entrée sans niveau antérieur : toujours autorisé
		if not self.niveau_precedent:
			return

		# Progression : exige admissible
		if not admission.get("admissible"):
			frappe.throw(
				"Progression refusée vers « {0} » : {1}. "
				"Crédits validés : {2}/{3} (minimum 50 %), dette : {4} crédits (maximum 30). "
				"Seul le redoublement de « {5} » est possible.".format(
					self.niveau,
					admission.get("motif", ""),
					admission.get("credits_validated", 0),
					admission.get("total_credits", 0),
					admission.get("debt_credits", 0),
					self.niveau_precedent or "—"
				)
			)

	def charger_resultats_precedents(self):
		"""Charge les résultats du niveau précédent avec les crédits (course_poid).

		En redoublement, ce sont les résultats du niveau réellement suivi qui sont
		repris (le niveau en cours), pas ceux du niveau encore antérieur.
		"""
		if not self.student:
			return

		redoublement = self._est_redoublement()
		niveau_resultats_label = self.niveau if redoublement else self.niveau_precedent
		if not niveau_resultats_label:
			return

		niveau_resultats_name = _resolve_level_name(self.filiere, niveau_resultats_label)
		annee_resultats = _annee_resultats_etudiant(self.student, niveau_resultats_label)
		if not annee_resultats or not niveau_resultats_name:
			return

		rows = frappe.get_all(
			"Resultat Academique",
			filters={
				"student": self.student,
				"academic_year": annee_resultats,
			},
			fields=["teaching_unit", "ue_name", "semestre", "note_finale", "statut", "decision_annee"],
			order_by="semestre asc, ue_name asc",
		)

		if not rows:
			return

		if self.semestre and self.semestre != "Les deux":
			rows = [r for r in rows if r.semestre == self.semestre]

		self.set("resultats_precedents", [])

		for resultat in rows:
			valide = 1 if resultat.statut == "Validé" else 0
			intitule = resultat.ue_name or frappe.db.get_value(
				"Teaching Unit", resultat.teaching_unit, "intitule_cours"
			) or resultat.teaching_unit

			credits = _credit_from_grid(
				self.filiere, niveau_resultats_name, resultat.teaching_unit
			)

			self.append("resultats_precedents", {
				"teaching_unit": resultat.teaching_unit,
				"intitule": intitule,
				"semestre": resultat.semestre or "",
				"note": resultat.note_finale or 0,
				"valide": valide,
				"est_dette": 1 if not valide else 0,
				"credits": credits,
			})

	def calculer_cours_inscrits(self):
		"""Construit la grille dynamique :
		- Dettes du niveau précédent (source=dette) : cochées et verrouillées.
		- Matières du niveau admis (source=niveau_actuel) : laissées décochées
		  (sauf redoublement : tout le programme est repris, cochable verrouillé).
		"""
		if not self.niveau or not self.academic_year or not self.filiere:
			return

		niveau_cible = self.niveau
		redoublement = self._est_redoublement()

		# Choix de l'étudiant (cases cochées reçues du formulaire) — à préserver
		selections = {
			c.teaching_unit for c in self.get("cours_inscrits") or []
			if c.teaching_unit and c.inscrire
		}
		self.set("cours_inscrits", [])

		# 1. Dettes (source=dette, verrouillées) — les 2 semestres sont repris
		# En redoublement, les dettes proviennent du niveau repris lui-même.
		niveau_dettes_label = self.niveau if redoublement else self.niveau_precedent
		niveau_dettes_name = _resolve_level_name(self.filiere, niveau_dettes_label) if niveau_dettes_label else None
		if niveau_dettes_name:
			annee_dettes = _annee_resultats_etudiant(self.student, niveau_dettes_label)
			dettes = _dettes_with_credits(
				self.student, self.filiere, niveau_dettes_name, annee_dettes or self.academic_year
			)
			for dette in dettes:
				self.append("cours_inscrits", {
					"teaching_unit": dette["teaching_unit"],
					"intitule": dette["intitule"],
					"semestre": dette["semestre"],
					"statut": "Reporté",
					"inscrire": 1,
					"est_obligatoire": 1,
					"source": "dette",
					"verrouille": 1,
					"motif": "Dette du niveau précédent (note: {0}/20)".format(dette["note"]),
					"credits": dette["credits"],
				})

		# 2. Matières du niveau admis (source=niveau_actuel) — à cocher par l'étudiant
		niveau_name = _resolve_level_name(self.filiere, niveau_cible)
		if niveau_name:
			tu_niveau = _teaching_units_niveau_year(self.filiere, niveau_name, self.academic_year)
			deja_ajoutes = {c["teaching_unit"] for c in dettes} if niveau_dettes_name else set()
			for tu in tu_niveau:
				if tu in deja_ajoutes:
					continue
				if self.semestre and self.semestre != "Les deux":
					semestre_tu = frappe.db.get_value("Teaching Unit", tu, "semestre") or ""
					if semestre_tu != self.semestre:
						continue
				credits = _credit_from_grid(self.filiere, niveau_name, tu)
				intitule = frappe.db.get_value("Teaching Unit", tu, "intitule_cours") or tu
				semestre_tu = frappe.db.get_value("Teaching Unit", tu, "semestre") or ""
				self.append("cours_inscrits", {
					"teaching_unit": tu,
					"intitule": intitule,
					"semestre": semestre_tu,
					"statut": "Inscrit",
					"inscrire": 1 if (redoublement or tu in selections) else 0,
					"est_obligatoire": 1 if redoublement else 0,
					"source": "niveau_actuel",
					"verrouille": 1 if redoublement else 0,
					"motif": "Matière du niveau {0}{1}".format(
						niveau_cible,
						" — redoublement : programme complet à reprendre" if redoublement else " — à cocher"
					),
					"credits": credits,
				})

	def _est_redoublement(self):
		"""True si l'étudiant se réinscrit dans le niveau qu'il vient de suivre."""
		if not self.niveau:
			return False
		dernier_classe = _derniere_classe_etudiant(self.student)
		return bool(dernier_classe and self.niveau == dernier_classe)

	def _verifier_limite_credits(self):
		"""Vérifie que les crédits cochés ne dépassent pas 30 par semestre."""
		if not self.cours_inscrits:
			return
		for sem in ["Semestre 1", "Semestre 2"]:
			credits_sem = sum(
				c.credits for c in self.cours_inscrits
				if c.inscrire and c.semestre == sem
			)
			if credits_sem > 30:
				frappe.throw(
					"Limite de crédits dépassée pour {0} : {1} crédits cochés (maximum 30)."
					.format(sem, credits_sem)
				)
