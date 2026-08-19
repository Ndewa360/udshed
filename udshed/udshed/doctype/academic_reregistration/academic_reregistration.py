import frappe
from frappe.model.document import Document

from udshed.utils.niveaux import niveau_precedent


class AcademicReregistration(Document):

	def validate(self):
		self.statut = "Validée"
		self.verifier_session_ouverte()
		self.verifier_doublon()
		self.calculer_niveau_precedent()
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

	def calculer_niveau_precedent(self):
		"""Trouve automatiquement le niveau précédent selon les règles de progression."""
		if not self.niveau or not self.filiere:
			return
		self.niveau_precedent = niveau_precedent(self.filiere, self.niveau)

	def charger_resultats_precedents(self):
		"""
		Charge TOUS les cours du niveau précédent avec leurs notes.
		- Cours avec note >= note_minimale : Validé
		- Cours avec note < note_minimale  : Dette
		- Cours sans note                   : Non évalué (dette par défaut)
		Filtre par semestre si spécifié.
		"""
		if not self.niveau_precedent or not self.student:
			return

		niveau_precedent_name = self.get_niveau_name(self.niveau_precedent)
		if not niveau_precedent_name:
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
				(CourseLevel.niveau == niveau_precedent_name)
			)
		)

		if self.semestre and self.semestre != "Les deux":
			query = query.where(TeachingUnit.semestre == self.semestre)

		tous_les_cours = query.run(as_dict=True)

		if not tous_les_cours:
			return

		tu_names = [c.name for c in tous_les_cours]

		notes = frappe.get_all(
			"Session Examen Note",
			filters={
				"student": self.student,
				"filiere": self.filiere,
				"niveau": niveau_precedent_name,
				"teaching_unit": ["in", tu_names]
			},
			fields=["teaching_unit", "note_finale"]
		)

		notes_dict = {n.teaching_unit: n.note_finale or 0 for n in notes}

		note_minimale = frappe.db.get_value(
			"Session Reinscription", self.reinscription_session, "note_minimale"
		) or 10

		self.set("resultats_precedents", [])

		for cours in tous_les_cours:
			note_finale = notes_dict.get(cours.name, 0)
			a_note = cours.name in notes_dict

			if a_note:
				valide = 1 if note_finale >= note_minimale else 0
				est_dette = 1 if note_finale < note_minimale else 0
			else:
				valide = 0
				est_dette = 1

			self.append("resultats_precedents", {
				"teaching_unit": cours.name,
				"intitule": cours.intitule_cours or "",
				"semestre": cours.semestre or "",
				"note": note_finale,
				"valide": valide,
				"est_dette": est_dette
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
