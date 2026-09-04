import frappe
from frappe.model.document import Document

from udshed.utils.niveaux import niveau_precedent, prochain_niveau, cycle_niveau

from udshed.api.reregistration import _decision_annee_etudiant


class AcademicReregistration(Document):

	def validate(self):
		self.statut = "Validée"
		self.verifier_session_ouverte()
		self.verifier_doublon()
		self.calculer_niveau_precedent()
		self.decision_notes = _decision_annee_etudiant(self.student, self._annee_resultats()) or ""
		self.verifier_progression()
		self.charger_resultats_precedents()
		self.calculer_cours_inscrits()

	def verifier_session_ouverte(self):
		"""Vérifie qu'une session de réinscription est ouverte"""
		session = frappe.db.exists("Session Reinscription", {
			"name": self.reinscription_session,
			"statut": "Ouverte"
		})
		if not session:
			frappe.throw("La session de réinscription sélectionnée n'est pas ouverte.")

	def verifier_doublon(self):
		"""Vérifie qu'un étudiant ne se réinscrit pas deux fois pour le même niveau et la même année"""
		existant = frappe.db.exists("Academic Reregistration", {
			"student": self.student,
			"academic_year": self.academic_year,
			"niveau": self.niveau,
			"name": ["!=", self.name]
		})
		if existant:
			frappe.throw("Cet étudiant est déjà réinscrit pour cette année et ce niveau.")

	def _annee_resultats(self):
		"""Année académique dont les résultats conditionnent la réinscription."""
		return _annee_resultats_etudiant(self.student, self.niveau_precedent)

	def verifier_progression(self):
		"""Vérifie le droit de suivre le niveau demandé selon la décision du module de notes.

		- Redoublement (même niveau) : toujours autorisé.
		- Progression (niveau supérieur) : exige la décision "Admis" sur l'année
		  du niveau précédent et le niveau suivant exact (prochain_niveau).
		- Entrée en Master : exige la validation de la Licence ("Admis") ET
		  l'accord du coordinateur (admission_master_accordee).
		"""
		if not self.filiere or not self.niveau:
			return

		if cycle_niveau(self.niveau) == "Master":
			if self.decision_notes != "Admis":
				frappe.throw(
					"L'accès au Master exige la validation de la Licence. Décision du module de notes : « {0} ».".format(
						self.decision_notes or "En attente"
					)
				)
			if not self.admission_master_accordee:
				frappe.throw(
					"L'accès au Master doit être accordé par le coordinateur : cochez « Admission en Master accordée »."
				)
			return

		if not self.niveau_precedent:
			return

		if self.niveau == self.niveau_precedent:
			return

		suivant = prochain_niveau(self.filiere, self.niveau_precedent)
		if suivant and self.niveau != suivant:
			frappe.throw(
				"Progression non valide : depuis « {0} », le niveau suivant est « {1} ».".format(
					self.niveau_precedent, suivant
				)
			)

		if self.decision_notes != "Admis":
			frappe.throw(
				"La réinscription en « {0} » est refusée : décision du module de notes « {1} ». "
				"Seul le redoublement de « {2} » est possible.".format(
					self.niveau, self.decision_notes or "En attente", self.niveau_precedent
				)
			)

	def calculer_niveau_precedent(self):
		"""Trouve automatiquement le niveau précédent selon les règles de progression."""
		if not self.niveau or not self.filiere:
			return
		self.niveau_precedent = niveau_precedent(self.filiere, self.niveau)

	def charger_resultats_precedents(self):
		"""
		Charge les résultats de l'année du niveau précédent depuis le module de
		gestion de notes (Resultat Academique) :
		- UE au statut "Validé"  -> valide (dette = 0)
		- UE au statut "Non Validé" ou absente -> dette (valide = 0)
		Filtre par semestre si spécifié.
		"""
		if not self.niveau_precedent or not self.student:
			return

		annee_resultats = self._annee_resultats()
		if not annee_resultats:
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

			self.append("resultats_precedents", {
				"teaching_unit": resultat.teaching_unit,
				"intitule": intitule,
				"semestre": resultat.semestre or "",
				"note": resultat.note_finale or 0,
				"valide": valide,
				"est_dette": 1 if not valide else 0,
			})

	def get_niveau_name(self, niveau_label):
		"""Retourne le name (ID) d'un niveau depuis son label"""
		if not niveau_label or not self.filiere:
			return None
		filiere_doc = frappe.get_doc("Field of study", self.filiere)
		for row in filiere_doc.field_of_study_level:
			if row.level == niveau_label:
				return row.name
		return None

	def calculer_cours_inscrits(self):
		"""
		Calcule les matières à inscrire selon :
		- Les matières du niveau actuel
		- Les résultats du niveau précédent
		"""
		if not self.niveau or not self.academic_year:
			return

		niveau_name = self.get_niveau_name(self.niveau)
		if not niveau_name:
			return

		from frappe.query_builder import DocType
		TeachingUnit = DocType("Teaching Unit")
		CourseLevel = DocType("Course Field of study level item")

		query = (
			frappe.qb.from_(TeachingUnit)
			.join(CourseLevel).on(CourseLevel.parent == TeachingUnit.name)
			.select(
				TeachingUnit.name,
				TeachingUnit.intitule_cours,
				TeachingUnit.semestre
			)
			.where(
				(TeachingUnit.academic_year == self.academic_year) &
				(CourseLevel.filiere == self.filiere) &
				(CourseLevel.niveau == niveau_name)
			)
		)

		if self.semestre and self.semestre != "Les deux":
			query = query.where(TeachingUnit.semestre == self.semestre)

		matieres = query.run(as_dict=True)

		resultats_dict = {}
		for r in self.resultats_precedents:
			resultats_dict[r.teaching_unit] = r.valide

		self.set("cours_inscrits", [])

		resultats_details = {}
		for r in self.resultats_precedents:
			resultats_details[r.teaching_unit] = r

		for matiere in matieres:
			if matiere.name in resultats_dict:
				valide = resultats_dict[matiere.name]
				detail = resultats_details.get(matiere.name)
				note_obtenue = detail.note if detail else 0
				if valide:
					statut = "Dispensé"
					inscrire = 0
					motif = f"Déjà validé au niveau précédent (note: {note_obtenue}/20)"
				else:
					statut = "Reporté"
					inscrire = 1
					motif = f"Échec au niveau précédent (note: {note_obtenue}/20)"
			else:
				statut = "Inscrit"
				inscrire = 1
				motif = "Nouvelle matière du niveau actuel"

			self.append("cours_inscrits", {
				"teaching_unit": matiere.name,
				"intitule": matiere.intitule_cours,
				"semestre": matiere.semestre,
				"statut": statut,
				"inscrire": inscrire,
				"est_obligatoire": 1,
				"motif": motif
			})


def _annee_resultats_etudiant(student, niveau_label=None):
	"""Année académique dont les résultats conditionnent la réinscription.

	- dernière année où l'étudiant a été inscrit au niveau passé (Academic
	  Reregistration) ;
	- à défaut, dernière année ayant des résultats publiés (Resultat Academique).
	"""
	if student and niveau_label:
		row = frappe.get_all(
			"Academic Reregistration",
			filters={"student": student, "niveau": niveau_label},
			fields=["academic_year"],
			order_by="creation desc",
			limit_page_length=1,
		)
		if row and row[0].academic_year:
			return row[0].academic_year

	rows = frappe.get_all(
		"Resultat Academique",
		filters={"student": student},
		fields=["academic_year"],
		order_by="creation desc",
		limit_page_length=1,
	)
	return rows[0].academic_year if rows else None


