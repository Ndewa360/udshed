import frappe

from frappe.query_builder import DocType

@frappe.whitelist()
def get_user_context():
	user = frappe.session.user
	default_academic_year = frappe.db.get_single_value('Udshed Setting', 'current_year')
	academic_year_list = frappe.get_all('Academic Year')
	roles = frappe.get_roles(user)
	data_result = []

	# ADMIN
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return [{
			"role": "Administrator",
			"lock_faculty": False,
			"lock_filiere": False,
			"lock_niveau": False,
			"can_create_course": True,
			"can_edit_course": True,
			"default_academic_year": default_academic_year,
			"academic_year_list": academic_year_list
		}]

	# COORDINATEUR DE NIVEAU / GESTIONNAIRE DE PLANNING
	role = None
	if "Planning Manager" in roles:
		role = "Planning Manager"
	if "Coordinateur" in roles or "Coordonateur" in roles:
		role = "Coordonateur"

	if role is not None:
		Teacher = DocType("Teacher")
		FieldOfStudy = DocType("Field of study")
		FieldOfStudyLevel = DocType("Field of study Level")

		query_coordo = (
			frappe.qb.from_(FieldOfStudy)
			.join(FieldOfStudyLevel)
			.on(FieldOfStudyLevel.parent == FieldOfStudy.name)
			.join(Teacher)
			.on(
				(FieldOfStudyLevel.coordonateur == Teacher.name) |
				(FieldOfStudyLevel.gestionnaire_de_planning == Teacher.name)
			)
			.select(
				FieldOfStudy.name.as_("filiere_name"),
				FieldOfStudyLevel.name.as_("niveau_name"),
				FieldOfStudyLevel.coordonateur,
				FieldOfStudyLevel.gestionnaire_de_planning,
				FieldOfStudy.name_of_field,
				FieldOfStudy.field_of_study_code,
				FieldOfStudy.faculte,
				FieldOfStudyLevel.level
			)
			.where(
				(Teacher.email == user)
			)
		)

		coord = query_coordo.run(as_dict=True)

		if len(coord) > 0:
			coordo_data = {
				"role": role,
				"faculty": [],
				"filiere": [],
				"niveau": [],
				"lock_faculty": True,
				"lock_filiere": True,
				"lock_niveau": True,
				"can_create_course": True,
				"can_edit_course": True,
				"default_academic_year": default_academic_year,
				"academic_year_list": academic_year_list
			}
			for c in coord:
				faculte_name = frappe.db.get_value("Faculty", c.faculte, "name")
				faculty_name = frappe.db.get_value("Faculty", c.faculte, "faculty_name")

				coordo_data["filiere"].append({"name": c.filiere_name, "filiere": c.name_of_field, "code": c.field_of_study_code, "faculte": c.faculte})
				if faculte_name:
					coordo_data["faculty"].append({"name": faculte_name, "faculte": faculty_name})
				coordo_data["niveau"].append({"name": c.niveau_name, "level": c.level})

			data_result.append(coordo_data.copy())

	if "Teacher" in roles:
		# ENSEIGNANT
		Teacher = DocType("Teacher")
		TeachingUnit = DocType("Teaching Unit")
		CourseNiveauFiliere = DocType("Course Field of study level item")
		CourseTeacherItem = DocType("Course Teacher Item")
		
		query_teacher = (
			frappe.qb.from_(TeachingUnit)
			.join(CourseTeacherItem)
			.on(CourseTeacherItem.parent == TeachingUnit.name)
			.join(CourseNiveauFiliere)
			.on(TeachingUnit.name == CourseNiveauFiliere.parent)
			.join(Teacher)
			.on(CourseTeacherItem.enseignant == Teacher.name)			
			.select(
				CourseNiveauFiliere.filiere,
				CourseNiveauFiliere.niveau,
				CourseTeacherItem.enseignant			
			)	
			.where(
				(Teacher.email == user)
			)
		)

		teacher = query_teacher.run(as_dict=True)
		if len(teacher) > 0:
			teacher_data = {
				"role": "Teacher",
				"faculty": [],
				"filiere": [],
				"niveau": [],
				"lock_faculty": True,
				"lock_filiere": True,
				"lock_niveau": True,
				"can_create_course": False,
				"can_edit_course": False,
				"default_academic_year": default_academic_year,
				"academic_year_list": academic_year_list
			}
			for t in teacher:
				filiere_name = frappe.db.get_value("Field of study", t.filiere, "name")
				name_of_field = frappe.db.get_value("Field of study", t.filiere, "name_of_field")
				faculte = frappe.db.get_value("Field of study", t.filiere, "faculte")
				faculte_name = frappe.db.get_value("Faculty", faculte, "name")
				faculty_name = frappe.db.get_value("Faculty", faculte, "faculty_name")
				level_name = frappe.db.get_value("Field of study Level", t.niveau, "name")
				level_label = frappe.db.get_value("Field of study Level", t.niveau, "level")

				teacher_data["filiere"].append({"name": filiere_name, "filiere": name_of_field, "faculte": faculte})
				if faculte_name:
					teacher_data["faculty"].append({"name": faculte_name, "faculte": faculty_name})
				teacher_data["niveau"].append({"name": level_name, "level": level_label})
			
			data_result.append(teacher_data.copy())

		

	if not data_result:
			# AUTRES UTILISATEURS
		data_result.append({
			"role": "Guest",
			"can_create_course": False,
			"can_edit_course": False,
			"default_academic_year": default_academic_year,
			"academic_year_list": academic_year_list
		})
	
	return data_result



def get_field_of_study_and_levels_for_coordinator(user):
    list_of_fields_of_study = frappe.db.get_all('Field of study Level', filters={"coordonateur": user.name}, fields=['parent'])
    return {
        "fields_of_study": [field.parent for field in list_of_fields_of_study],
        "levels": ["Licence 1", "Licence 2"]
    }


@frappe.whitelist()
def get_teacher_ues(teacher):
    """Retourne la liste des UE assignées à un enseignant."""
    return frappe.db.get_all(
        "Course Teacher Item",
        filters={"enseignant": teacher},
        pluck="parent",
        distinct=True,
    )