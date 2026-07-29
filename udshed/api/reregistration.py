import frappe
from frappe.query_builder import DocType


@frappe.whitelist()
def get_open_sessions():
	"""Retourne toutes les sessions de réinscription ouvertes"""
	return frappe.get_all(
		"Reinscription",
		filters={"statut": "Ouverte"},
		fields=["name", "academic_year", "date_ouverture", "date_cloture", "note_minimale"]
	)


@frappe.whitelist()
def get_student_by_matricule(matricule):
	"""Retrouver un étudiant par son matricule"""
	if not frappe.db.exists("Student", matricule):
		frappe.throw(f"Aucun étudiant trouvé avec le matricule {matricule}")
	return frappe.get_doc("Student", matricule)


@frappe.whitelist()
def get_ordered_levels(filiere):
	"""Retourne les niveaux d'une filière triés par ordre croissant"""
	doc = frappe.get_doc("Field of study", filiere)
	levels = sorted(doc.field_of_study_level, key=lambda x: x.order or 0)
	return [
		{
			"name": l.name,
			"level": l.level,
			"order": l.order
		}
		for l in levels
	]


@frappe.whitelist()
def get_previous_level_courses(filiere, niveau_label, academic_year):
	"""
	Retourne les matières du niveau précédent
	pour pré-remplir la table des résultats précédents.

	Args:
		filiere: name/ID de la filière (Field of study)
		niveau_label: label du niveau actuel (ex: "Licence 1"), valeur du Select
		academic_year: name/ID de l'année académique
	"""
	filiere_doc = frappe.get_doc("Field of study", filiere)

	# Trouver l'order du niveau actuel par son label (valeur Select)
	niveau_actuel_order = None
	niveau_precedent_name = None

	for row in filiere_doc.field_of_study_level:
		if row.level == niveau_label:
			niveau_actuel_order = row.order
			break

	if not niveau_actuel_order:
		return []

	# Trouver le niveau précédent (order - 1)
	for row in filiere_doc.field_of_study_level:
		if row.order == (niveau_actuel_order - 1):
			niveau_precedent_name = row.name
			break

	if not niveau_precedent_name:
		return []

	# Récupérer les matières du niveau précédent
	TeachingUnit = DocType("Teaching Unit")
	CourseLevel = DocType("Course Field of study level item")

	matieres = (
		frappe.qb.from_(TeachingUnit)
		.join(CourseLevel).on(CourseLevel.parent == TeachingUnit.name)
		.select(
			TeachingUnit.name,
			TeachingUnit.intitule_cours,
			TeachingUnit.semestre
		)
		.where(
			(TeachingUnit.academic_year == academic_year) &
			(CourseLevel.filiere == filiere) &
			(CourseLevel.niveau == niveau_precedent_name)
		)
	).run(as_dict=True)

	return matieres


@frappe.whitelist()
def get_student_notes(student, filiere, niveau_precedent_label):
	"""
	Récupère les notes d'un étudiant pour un niveau précédent donné.
	Utilise directement les champs filiere/niveau de Session Examen Note.

	Args:
		student: name/ID de l'étudiant
		filiere: name/ID de la filière
		niveau_precedent_label: label du niveau précédent (ex: "Licence 1")
	"""
	# Convertir le label en name (ID) du child table Field of study Level
	filiere_doc = frappe.get_doc("Field of study", filiere)
	niveau_precedent_name = None
	for row in filiere_doc.field_of_study_level:
		if row.level == niveau_precedent_label:
			niveau_precedent_name = row.name
			break

	if not niveau_precedent_name:
		return []

	SessionExamenNote = DocType("Session Examen Note")
	TeachingUnit = DocType("Teaching Unit")

	notes = (
		frappe.qb.from_(SessionExamenNote)
		.join(TeachingUnit)
		.on(TeachingUnit.name == SessionExamenNote.teaching_unit)
		.select(
			SessionExamenNote.teaching_unit,
			SessionExamenNote.note_finale,
			SessionExamenNote.session_examen,
			TeachingUnit.intitule_cours,
			TeachingUnit.semestre
		)
		.where(
			(SessionExamenNote.student == student) &
			(SessionExamenNote.filiere == filiere) &
			(SessionExamenNote.niveau == niveau_precedent_name)
		)
	).run(as_dict=True)

	return notes


@frappe.whitelist()
def get_reregistration_summary(student, academic_year):
	"""
	Retourne un résumé de la réinscription d'un étudiant
	pour une année académique donnée
	"""
	reregistration = frappe.get_all(
		"Academic Reregistration",
		filters={
			"student": student,
			"academic_year": academic_year
		},
		fields=["name", "statut", "niveau", "filiere", "semestre"]
	)

	if not reregistration:
		return None

	doc = frappe.get_doc("Academic Reregistration", reregistration[0].name)

	# Compter les matières par statut
	inscrits = len([c for c in doc.cours_inscrits if c.statut == "Inscrit"])
	dispenses = len([c for c in doc.cours_inscrits if c.statut == "Dispensé"])
	reportes = len([c for c in doc.cours_inscrits if c.statut == "Reporté"])

	return {
		"name": doc.name,
		"statut": doc.statut,
		"niveau": doc.niveau,
		"filiere": doc.filiere,
		"semestre": doc.semestre,
		"total_matieres": len(doc.cours_inscrits),
		"inscrits": inscrits,
		"dispenses": dispenses,
		"reportes": reportes,
		"dettes": reportes
	}


@frappe.whitelist()
def valider_reregistration(reregistration_name):
	"""Valider une réinscription — action du coordonateur"""
	doc = frappe.get_doc("Academic Reregistration", reregistration_name)

	if doc.statut != "En attente":
		frappe.throw("Seules les réinscriptions en attente peuvent être validées.")

	doc.valider()

	return {"status": True, "message": "Réinscription validée avec succès"}


@frappe.whitelist()
def rejeter_reregistration(reregistration_name, motif=None):
	"""Rejeter une réinscription — action du coordonateur"""
	doc = frappe.get_doc("Academic Reregistration", reregistration_name)
	doc.rejeter(motif=motif)
	return {"status": True, "message": "Réinscription rejetée"}


@frappe.whitelist()
def get_reregistrations_by_session(reinscription_session):
	"""
	Retourne toutes les réinscriptions d'une session
	avec leurs statuts — pour le tableau de bord du coordonateur
	"""
	reregistrations = frappe.get_all(
		"Academic Reregistration",
		filters={"reinscription_session": reinscription_session},
		fields=[
			"name", "student", "academic_year",
			"filiere", "niveau", "semestre", "statut"
		],
		order_by="creation desc"
	)

	result = []
	student_names = list(set(r.student for r in reregistrations))
	student_map = {}
	for s_name in student_names:
		s = frappe.get_doc("Student", s_name)
		student_map[s_name] = {
			"nom_etudiant": f"{s.nom} {s.prenom}",
			"matricule": s.name,
			"email": s.email
		}

	for r in reregistrations:
		result.append({
			**r,
			**student_map.get(r.student, {})
		})

	return result
