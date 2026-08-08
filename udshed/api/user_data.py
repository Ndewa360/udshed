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

	print("Frappe role ", frappe.get_roles(user))
	# COORDINATEUR DE NIVEAU
	role = None
	if "Planning Manager" in roles:
		role="Planning Manager"
	if "Coordinateur" in roles:
		role="Coordinateur"
	
	if "Coordonateur" or "Planning Manager" in roles:
		Teacher = DocType("Teacher")
		FieldOfStudy = DocType("Field of study")
		FieldOfStudyLevel = DocType("Field of study Level")
	
		query_coordo = (
			frappe.qb.from_(FieldOfStudy)
			.join(FieldOfStudyLevel)
			.on(FieldOfStudyLevel.parent == FieldOfStudy.name)
			.join(Teacher)
			.on(
				( FieldOfStudyLevel.coordonateur == Teacher.name ) |
				(FieldOfStudyLevel.gestionnaire_de_planning == Teacher.name)
			)
			.select(
				FieldOfStudyLevel.name,
				FieldOfStudyLevel.coordonateur,
				FieldOfStudyLevel.gestionnaire_de_planning,
				FieldOfStudy.name_of_field,
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
				filiere = frappe.get_doc("Field of study", {"name_of_field": c.name_of_field})
				faculte = frappe.get_doc("Faculty", {"name": filiere.faculte})

				coordo_data["filiere"].append({"name": c.name, "filiere": filiere.name_of_field, "code":filiere.field_of_study_code, "faculte": filiere.faculte})
				coordo_data["faculty"].append({"name": faculte.name, "faculte": faculte.faculty_name})
				coordo_data["niveau"].append({"name": c.name, "level": c.level})
			
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
				filiere = frappe.get_doc("Field of study", {"name": t.filiere})
				faculte = frappe.get_doc("Faculty", {"name": filiere.faculte})
				level = frappe.get_doc("Field of study Level", {"name": t.niveau})

				teacher_data["filiere"].append({"name": filiere.name, "filiere": filiere.name_of_field, "faculte": filiere.faculte})
				teacher_data["faculty"].append({"name": faculte.name, "faculte": faculte.faculty_name})
				teacher_data["niveau"].append({"name": level.name, "level": level.level})
			
			data_result.append(teacher_data.copy())

		

	if not data_result or "Guest" in roles:
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
    list_of_fields_of_study = frappe.db.get_all('Field of study Level', filters={"coordinator": user.name}, fields=['field_of_study'])
    return {
        "fields_of_study": [field.field_of_study for field in list_of_fields_of_study],
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

