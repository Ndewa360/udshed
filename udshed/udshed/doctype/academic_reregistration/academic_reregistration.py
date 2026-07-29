import frappe
from frappe.model.document import Document


class AcademicReregistration(Document):

	def validate(self):
		self.verifier_session_ouverte()
		self.verifier_doublon()
		self.calculer_niveau_precedent()
		self.charger_resultats_precedents()
		self.calculer_cours_inscrits()

	def verifier_session_ouverte(self):
		"""Vérifie qu'une session de réinscription est ouverte"""
		session = frappe.db.exists("Reinscription", {
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
		"""Trouve automatiquement le niveau précédent selon le champ order"""
		if not self.niveau or not self.filiere:
			return

		filiere_doc = frappe.get_doc("Field of study", self.filiere)
		niveau_actuel_order = None

		for row in filiere_doc.field_of_study_level:
			if row.level == self.niveau:
				niveau_actuel_order = row.order
				break

		if not niveau_actuel_order:
			return

		self.niveau_precedent = None
		for row in filiere_doc.field_of_study_level:
			if row.order == (niveau_actuel_order - 1):
				self.niveau_precedent = row.level
				break

	def charger_resultats_precedents(self):
		"""
		Lit les notes de l'étudiant depuis Session Examen Note
		pour les matières du niveau précédent.
		Utilise directement les champs filiere/niveau de Session Examen Note.
		"""
		if not self.niveau_precedent or not self.student:
			return

		niveau_precedent_name = self.get_niveau_name(self.niveau_precedent)
		if not niveau_precedent_name:
			return

		# Requête simplifiée grâce aux champs filiere/niveau sur Session Examen Note
		notes = frappe.get_all(
			"Session Examen Note",
			filters={
				"student": self.student,
				"filiere": self.filiere,
				"niveau": niveau_precedent_name
			},
			fields=["teaching_unit", "note_finale"]
		)

		if not notes:
			return

		note_minimale = frappe.db.get_value(
			"Reinscription", self.reinscription_session, "note_minimale"
		) or 10

		self.set("resultats_precedents", [])

		for note in notes:
			intitule = frappe.db.get_value(
				"Teaching Unit", note.teaching_unit, "intitule_cours"
			) or ""

			semestre = frappe.db.get_value(
				"Teaching Unit", note.teaching_unit, "semestre"
			) or ""

			note_finale = note.note_finale or 0
			valide = 1 if note_finale >= note_minimale else 0
			est_dette = 1 if note_finale < note_minimale else 0

			self.append("resultats_precedents", {
				"teaching_unit": note.teaching_unit,
				"intitule": intitule,
				"semestre": semestre,
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

		for matiere in matieres:
			if matiere.name in resultats_dict:
				statut = "Dispensé" if resultats_dict[matiere.name] else "Reporté"
			else:
				statut = "Inscrit"

			self.append("cours_inscrits", {
				"teaching_unit": matiere.name,
				"semestre": matiere.semestre,
				"statut": statut,
				"est_obligatoire": 1
			})

	def valider(self):
		"""Valide la réinscription et met à jour le niveau de l'étudiant"""
		if self.statut != "En attente":
			frappe.throw("Seules les réinscriptions en attente peuvent être validées.")

		self.db_set("statut", "Validée")

		# Mettre à jour le niveau actuel de l'étudiant
		frappe.db.set("Student", self.student, "niveau_actuel", self.niveau)

		self.envoyer_email_confirmation()

	def rejeter(self, motif=None):
		"""Rejette la réinscription"""
		if self.statut != "En attente":
			frappe.throw("Seules les réinscriptions en attente peuvent être rejetées.")

		self.db_set("statut", "Rejetée")
		self.envoyer_email_rejet(motif)

	def envoyer_email_confirmation(self):
		"""Envoie un email de confirmation à l'étudiant"""
		student = frappe.get_doc("Student", self.student)
		if not student.email:
			return

		frappe.sendmail(
			recipients=[student.email],
			subject=f"Réinscription confirmée - {self.academic_year}",
			message=f"""
				Bonjour {student.nom} {student.prenom},<br><br>
				Votre réinscription pour l'année académique <b>{self.academic_year}</b>
				au niveau <b>{self.niveau}</b> a été validée.<br><br>
				Matricule : <b>{student.name}</b><br><br>
				Cordialement,<br>
				L'administration
			"""
		)

	def envoyer_email_rejet(self, motif=None):
		"""Envoie un email de rejet à l'étudiant"""
		student = frappe.get_doc("Student", self.student)
		if not student.email:
			return

		frappe.sendmail(
			recipients=[student.email],
			subject=f"Réinscription rejetée - {self.academic_year}",
			message=f"""
				Bonjour {student.nom} {student.prenom},<br><br>
				Votre réinscription pour l'année académique
				<b>{self.academic_year}</b> a été rejetée.<br>
				{f"Motif : {motif}" if motif else ""}<br><br>
				Veuillez contacter l'administration pour plus d'informations.<br><br>
				Cordialement,<br>
				L'administration
			"""
		)
