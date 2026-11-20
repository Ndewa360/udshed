import frappe

from frappe.query_builder import DocType

import udshed.api.planning_permission as planning_permission

@frappe.whitelist()
def get_user_context():
	user = frappe.session.user
	default_academic_year = frappe.db.get_single_value('Udshed Setting', 'current_year')
	scope = planning_permission.get_scope(user)
	academic_year_list = frappe.get_all(
		'Academic Year',
		filters={'name': ['in', scope['academic_years']]} if scope['academic_years'] else None,
	)
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
	if "Coordonateur" in roles:
		role = "Coordonateur"
	elif "Planning Manager" in roles:
		role = "Planning Manager"

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
				"teacher": teacher[0].enseignant if teacher else None,
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


_MONTH_NUMBERS = {
	"janvier": 1,
	"fevrier": 2,
	"mars": 3,
	"avril": 4,
	"mai": 5,
	"juin": 6,
	"juillet": 7,
	"aout": 8,
	"septembre": 9,
	"octobre": 10,
	"novembre": 11,
	"decembre": 12,
}


def _month_number(value):
	text = str(value or "").strip().lower()
	text = text.replace("é", "e").replace("è", "e").replace("ê", "e").replace("à", "a").replace("ç", "c")
	if text.isdigit():
		number = int(text)
		return number if 1 <= number <= 12 else 0
	return _MONTH_NUMBERS.get(text, 0)


@frappe.whitelist()
def get_academic_year_months(academic_year):
	if not academic_year or not frappe.db.exists("Academic Year", academic_year):
		return []

	scope = planning_permission.get_scope(frappe.session.user)
	if scope["academic_years"] and academic_year not in scope["academic_years"]:
		return []

	doc = frappe.get_doc("Academic Year", academic_year)
	parts = str(academic_year).split("-")
	start_year = frappe.utils.cint(doc.start_year) or (frappe.utils.cint(parts[0]) if parts else 0)
	end_year = frappe.utils.cint(doc.end_year) or (frappe.utils.cint(parts[1]) if len(parts) > 1 else 0)
	start_month = _month_number(doc.start_month) or 9
	end_month = _month_number(doc.end_month) or 8

	if not start_year:
		return []
	if not end_year:
		end_year = start_year + (1 if end_month < start_month else 0)
	if (end_year, end_month) < (start_year, start_month):
		return []

	months = []
	year = start_year
	month = start_month
	while (year, month) <= (end_year, end_month) and len(months) < 24:
		months.append({"year": year, "month": month - 1})
		month += 1
		if month > 12:
			month = 1
			year += 1
	return months
