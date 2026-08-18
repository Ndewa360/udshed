import os

import frappe
from frappe.utils.pdf import get_pdf
from frappe.query_builder import DocType


@frappe.whitelist()
def get_open_sessions():
	"""Retourne toutes les sessions de réinscription ouvertes"""
	return frappe.get_all(
		"Session Reinscription",
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
def soumettre_reregistration(reregistration_name):
	"""Soumettre une réinscription pour validation (Brouillon -> En attente)"""
	doc = frappe.get_doc("Academic Reregistration", reregistration_name)
	doc.soumettre()
	return {"status": True, "message": "Réinscription soumise pour validation"}


@frappe.whitelist()
def valider_reregistration(reregistration_name):
	"""Valider une réinscription — action du coordonateur"""
	doc = frappe.get_doc("Academic Reregistration", reregistration_name)
	doc.valider()
	return {"status": True, "message": "Réinscription validée avec succès"}


@frappe.whitelist()
def refuser_reregistration(reregistration_name, motif=None):
	"""Refuser une réinscription — action du coordonateur"""
	doc = frappe.get_doc("Academic Reregistration", reregistration_name)
	doc.refuser(motif=motif)
	return {"status": True, "message": "Réinscription refusée"}


@frappe.whitelist()
def reouvrir_reregistration(reregistration_name):
	"""Rouvrir une réinscription soumise pour correction (En attente -> Brouillon)"""
	doc = frappe.get_doc("Academic Reregistration", reregistration_name)
	doc.reouvrir()
	return {"status": True, "message": "Réinscription rouvert en brouillon"}


@frappe.whitelist()
def get_all_levels(faculty=None, filiere=None):
	"""Retourne tous les niveaux groupés par filière, triés par ordre"""
	filters = {}
	if filiere:
		filters["name"] = filiere
	elif faculty:
		filters["faculte"] = faculty

	fields_of_study = frappe.get_all("Field of study", filters=filters, fields=["name", "name_of_field", "faculte"])
	result = []
	for fos in fields_of_study:
		doc = frappe.get_doc("Field of study", fos.name)
		levels = sorted(doc.field_of_study_level, key=lambda x: x.order or 0)
		result.append({
			"filiere_name": fos.name,
			"filiere_label": fos.name_of_field,
			"faculte": fos.faculte,
			"levels": [
				{
					"name": l.name,
					"level": l.level,
					"cycle": l.cycle,
					"order": l.order,
					"coordonateur": l.coordonateur,
					"calendrier": l.calendrier,
				}
				for l in levels
			]
		})
	return result


@frappe.whitelist()
def add_level(filiere, level, cycle=None, coordonateur=None, calendrier="Defaut", gestionnaire_de_planning=None):
	"""Ajoute un niveau à une filière. Le save() déclenche before_save
	qui renumérote les ordres et déduit le cycle si non renseigné."""
	doc = frappe.get_doc("Field of study", filiere)
	if any(r.level == level for r in doc.field_of_study_level):
		frappe.throw(f"Le niveau {level} existe déjà dans {filiere}")
	doc.append("field_of_study_level", {
		"level": level,
		"cycle": cycle or None,
		"order": (len(doc.field_of_study_level) or 0) + 1,
		"coordonateur": coordonateur,
		"calendrier": calendrier or "Defaut",
		"gestionnaire_de_planning": gestionnaire_de_planning,
	})
	doc.save(ignore_permissions=True)
	return {"status": True, "message": f"Niveau {level} ajouté à {filiere}"}


@frappe.whitelist()
def move_level(filiere, level_name, direction):
	"""
	Déplace un niveau vers le haut (up) ou vers le bas (down)
	en réordonnant physiquement les lignes du tableau.
	"""
	doc = frappe.get_doc("Field of study", filiere)
	names = [r.name for r in sorted(doc.field_of_study_level, key=lambda x: x.order or 0)]

	if level_name not in names:
		frappe.throw("Niveau introuvable")

	current_idx = names.index(level_name)

	if direction == "up":
		if current_idx == 0:
			frappe.throw("Le niveau est déjà en première position")
		names[current_idx], names[current_idx - 1] = names[current_idx - 1], names[current_idx]
	elif direction == "down":
		if current_idx == len(names) - 1:
			frappe.throw("Le niveau est déjà en dernière position")
		names[current_idx], names[current_idx + 1] = names[current_idx + 1], names[current_idx]
	else:
		frappe.throw("Direction invalide. Utilisez 'up' ou 'down'")

	return reorder_levels(filiere, names)


@frappe.whitelist()
def reorder_levels(filiere, level_names):
	"""Réordonne physiquement les lignes de niveaux selon l'ordre de level_names.

	Le save() déclenche before_save qui renumérote `order` = position de chaque ligne.
	"""
	doc = frappe.get_doc("Field of study", filiere)
	name_to_row = {row.name: row for row in doc.field_of_study_level}
	rows = [name_to_row[n] for n in level_names if n in name_to_row]
	rows += [row for row in doc.field_of_study_level if row.name not in name_to_row]
	doc.field_of_study_level = rows
	doc.save(ignore_permissions=True)
	return {"status": True, "message": "Ordre des niveaux mis à jour"}


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
	student_names = list(set(r.get("student") for r in reregistrations))
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
			**student_map.get(r.get("student"), {})
		})

	return result


@frappe.whitelist()
def get_reregistration_report(reinscription_session=None, filiere=None, statut=None):
	"""
	Rapport des réinscriptions : liste détaillée + statistiques
	par statut, filière et niveau.

	Args:
		reinscription_session: name/ID de la Session Reinscription (optionnel)
		filiere: name/ID de la Field of study (optionnel)
		statut: Brouillon | En attente | Validée | Refusée (optionnel)

	Returns:
		dict: {rows, total, par_statut, par_filiere, par_niveau}
	"""
	filters = {}
	if reinscription_session:
		filters["reinscription_session"] = reinscription_session
	if filiere:
		filters["filiere"] = filiere
	if statut:
		filters["statut"] = statut

	reregistrations = frappe.get_all(
		"Academic Reregistration",
		filters=filters,
		fields=[
			"name", "student", "academic_year", "reinscription_session",
			"filiere", "niveau", "semestre", "statut", "creation"
		],
		order_by="creation desc"
	)

	student_names = list(set(r.get("student") for r in reregistrations))
	student_map = {}
	for s_name in student_names:
		s = frappe.get_doc("Student", s_name)
		student_map[s_name] = {
			"matricule": s.name,
			"nom_etudiant": f"{s.nom} {s.prenom}",
			"email": s.email
		}

	filiere_names = list(set(r.get("filiere") for r in reregistrations))
	filiere_map = {}
	for f_name in filiere_names:
		filiere_map[f_name] = (
			frappe.db.get_value("Field of study", f_name, "name_of_field") or f_name
		)

	rows = []
	for r in reregistrations:
		rows.append({
			**r,
			"matricule": student_map.get(r.get("student"), {}).get("matricule", ""),
			"nom_etudiant": student_map.get(r.get("student"), {}).get("nom_etudiant", ""),
			"email": student_map.get(r.get("student"), {}).get("email", ""),
			"filiere_label": filiere_map.get(r.get("filiere"), r.get("filiere"))
		})

	par_statut = {}
	par_filiere = {}
	par_niveau = {}
	for r in rows:
		statut = r.get("statut") or "Brouillon"
		par_statut[statut] = par_statut.get(statut, 0) + 1
		label = r.get("filiere_label") or "Non défini"
		par_filiere[label] = par_filiere.get(label, 0) + 1
		niveau = r.get("niveau") or "Non défini"
		par_niveau[niveau] = par_niveau.get(niveau, 0) + 1

	return {
		"rows": rows,
		"total": len(rows),
		"par_statut": par_statut,
		"par_filiere": par_filiere,
		"par_niveau": par_niveau
	}


@frappe.whitelist()
def telecharger_fiche_reinscription(reregistration_name):
	"""Génère la fiche de réinscription en PDF.

	L'étudiant lié ne peut la télécharger qu'une seule fois (fiche_telechargee).
	Le personnel (Coordonateur / Agent de scolarité / Comptable / System Manager)
	peut la re-télécharger sans consommer le téléchargement unique.
	"""
	doc = frappe.get_doc("Academic Reregistration", reregistration_name)
	student = frappe.get_doc("Student", doc.student)

	roles = frappe.get_roles()
	is_student = student.utilisateur == frappe.session.user
	is_staff = bool(set(roles) & {"System Manager", "Coordonateur", "Agent de scolarité", "Comptable"})
	if not (is_student or is_staff):
		frappe.throw("Vous n'avez pas accès à cette fiche de réinscription.")

	if doc.statut != "Validée":
		frappe.throw("La fiche de réinscription n'est disponible qu'après validation.")

	if is_student and doc.fiche_telechargee:
		frappe.throw("La fiche de réinscription a déjà été téléchargée.")

	filiere_label = frappe.db.get_value("Field of study", doc.filiere, "name_of_field") or doc.filiere
	school_name = frappe.get_single("Udshed Setting").school_name or ""
	coordonnateur = frappe.db.get_value("Field of study Level", doc.niveau, "coordonateur") or ""

	template_path = os.path.join(frappe.get_app_path("udshed"), "templates", "reinscription_fiche.html")
	with open(template_path, encoding="utf-8") as f:
		html = frappe.render_template(f.read(), {
			"school_name": school_name,
			"student": {
				"matricule": student.name,
				"nom": student.nom or "",
				"prenom": student.prenom or "",
				"email": student.email
			},
			"doc": {
				"name": doc.name,
				"reinscription_session": doc.reinscription_session,
				"academic_year": doc.academic_year,
				"filiere_label": filiere_label,
				"niveau": doc.niveau,
				"semestre": doc.semestre,
				"statut": doc.statut
			},
			"coordonnateur": coordonnateur,
			"cours_inscrits": [
				{"intitule": m.intitule, "teaching_unit": m.teaching_unit, "semestre": m.semestre, "statut": m.statut}
				for m in doc.cours_inscrits
			],
			"resultats_precedents": [
				{
					"intitule": r.intitule, "teaching_unit": r.teaching_unit, "semestre": r.semestre,
					"note": r.note, "valide": r.valide, "est_dette": r.est_dette
				}
				for r in doc.resultats_precedents
			]
		})

	pdf = get_pdf(html)

	if is_student:
		doc.db_set("fiche_telechargee", 1)
		frappe.db.commit()

	frappe.local.response.filename = f"Fiche_Reinscription_{doc.name}.pdf"
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "pdf"
