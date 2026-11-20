import frappe
from frappe.query_builder import DocType

import udshed.api.planning_permission as planning_permission


@frappe.whitelist()
def get_all_planning_item_by_filter(academic_year, faculty=None, field_of_study=None, level=None, course_type=None, teacher=None, semestre=None):
	field_code = field_of_study
	if field_of_study:
		field_of_study = (
			frappe.db.get_value("Field of study", field_of_study, "name")
			or frappe.db.get_value("Field of study", {"field_of_study_code": field_of_study}, "name")
			or field_of_study
		)
	planning_permission.assert_can_view_planning(
		academic_year=academic_year,
		faculty=faculty,
		filiere=field_of_study,
		niveau=level,
		teacher=teacher,
	)
	PlanningItem = DocType("Planning Item")
	TeachingUnit = DocType("Teaching Unit")
	CourseTeacherItem = DocType("Course Teacher Item")
	CourseFieldOfStudyLevelItem = DocType("Course Field of study level item")
	FieldOfStudy = DocType("Field of study")
	Course = DocType("Course")

	query = (
		frappe.qb.from_(PlanningItem)
		.join(TeachingUnit)
		.on(PlanningItem.cours == TeachingUnit.name)
		.join(Course)
		.on(TeachingUnit.course == Course.name)
		.join(CourseFieldOfStudyLevelItem)
		.on(CourseFieldOfStudyLevelItem.parent == TeachingUnit.name)
		.join(FieldOfStudy)
		.on(FieldOfStudy.name == CourseFieldOfStudyLevelItem.filiere)
		.left_join(CourseTeacherItem)
		.on(CourseTeacherItem.parent == TeachingUnit.name)
		.select(
			PlanningItem.name,
			PlanningItem.cours,
			PlanningItem.period,
			PlanningItem.date,
			PlanningItem.status,
			PlanningItem.type.as_("planning_type"),
			PlanningItem.academic_year.as_("planning_academic_year"),
			TeachingUnit.name.as_("teachingunit_name"),
			TeachingUnit.intitule_cours.as_("intitule_cours"),
			TeachingUnit.nombre_dheure_cm,
			TeachingUnit.nombre_dheure_td,
			TeachingUnit.nombre_dheure_tp,
			TeachingUnit.semestre.as_("unit_semestre"),
			Course.name.as_("course_name"),
			Course.intitule.as_("course_label"),
			Course.nombre_dheure_cm.as_("course_cm"),
			Course.nombre_dheure_td.as_("course_td"),
			Course.nombre_dheure_tp.as_("course_tp"),
			Course.semestre.as_("course_semestre"),
			CourseFieldOfStudyLevelItem.filiere,
			CourseFieldOfStudyLevelItem.niveau,
			CourseFieldOfStudyLevelItem.course_poid,
			FieldOfStudy.faculte,
			CourseTeacherItem.enseignant,
		)
		.where(PlanningItem.academic_year == academic_year)
		.distinct()
	)
	if faculty:
		query = query.where(FieldOfStudy.faculte == faculty)
	if course_type:
		query = query.where(PlanningItem.type == course_type)
	if field_code:
		query = query.where(FieldOfStudy.field_of_study_code == field_code)
	if level:
		query = query.where(CourseFieldOfStudyLevelItem.niveau == level)
	if semestre:
		query = query.where(TeachingUnit.semestre == semestre)
	if teacher:
		query = query.where(CourseTeacherItem.enseignant == teacher)

	data = query.run(as_dict=True)
	process_data = {}
	for row in data:
		niveau_key = "{0}-{1}".format(row.filiere, row.niveau)
		entry = process_data.get(row.teachingunit_name)
		if not entry:
			entry = {
				"niveau": [],
				"niveau_key": [],
				"teacher": [],
				"teacher_key": [],
				"course_name": row.course_name,
				"course_label": row.course_label,
				"intitule": row.intitule_cours or row.course_label,
				"nombre_dheure_cm": row.nombre_dheure_cm or row.course_cm,
				"nombre_dheure_td": row.nombre_dheure_td or row.course_td,
				"nombre_dheure_tp": row.nombre_dheure_tp or row.course_tp,
				"semestre": row.unit_semestre or row.course_semestre,
				"faculte": row.faculte,
				"faculty": row.faculte,
				"name": row.teachingunit_name,
				"teaching_unit": row.teachingunit_name,
				"planning": [],
			}
			process_data[row.teachingunit_name] = entry
		if niveau_key not in entry["niveau_key"]:
			entry["niveau_key"].append(niveau_key)
			entry["niveau"].append({
				"filiere": row.filiere,
				"niveau": row.niveau,
				"course_poid": row.course_poid,
				"faculty": row.faculte,
			})
		if row.enseignant and row.enseignant not in entry["teacher_key"]:
			entry["teacher_key"].append(row.enseignant)
			entry["teacher"].append(row.enseignant)
		if not any(plan["name"] == row.name for plan in entry["planning"]):
			entry["planning"].append({
				"name": row.name,
				"cours": row.cours,
				"period": row.period,
				"date": row.date,
				"status": row.status,
				"type": row.planning_type,
			})

	for entry in process_data.values():
		entry.pop("niveau_key", None)
		entry.pop("teacher_key", None)
	return process_data
