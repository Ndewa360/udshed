import frappe
from frappe.utils import cint
from frappe.query_builder import DocType
import json


@frappe.whitelist()
def get_teaching_units(
	academic_year: str,
	faculty: str,
	filiere: str = None,
	niveau: str = None
):
	"""
	Retourne les Teaching Units selon le contexte sélectionné
	"""

	# =========================
	# Validation minimale
	# =========================
	if not academic_year or not faculty:
		frappe.throw("Année académique et faculté requises")

	# =========================
	# Récupération Teaching Units
	# =========================
	conditions = {
		"academic_year": academic_year,
		"docstatus": 0
	}

	teaching_units = frappe.get_all(
		"Teaching Unit",
		filters=conditions,
		fields=[
			"name",
			"course",
		]
	)

	if not teaching_units:
		return []

	results = []

	for tu in teaching_units:
		# =========================
		# Charger le document complet
		# =========================
		doc = frappe.get_doc("Teaching Unit", tu.name)

		# =========================
		# Filtrage par filière / niveau
		# =========================
		if filiere or niveau:
			match = False
			for cls in doc.course_levels:				
				if filiere and cls.filiere != filiere:
					# if filiere and cls.faculty != faculty:
					# 	continue
					continue
				if niveau and cls.niveau != niveau:
					continue
				match = True
				break

			if not match:
				continue

		# =========================
		# Infos cours
		# =========================
		course = frappe.get_doc("Course", doc.course)

		# =========================
		# Classes concernées
		# =========================
		classes = [
			# f"{c.filiere} {c.niveau.level}"
			# for c in doc.course_levels
		]
		for c in doc.course_levels:
			if not c.filiere or not c.niveau:
				continue
			level = frappe.get_doc("Field of study Level", c.niveau)
			classes.append(f"{c.filiere} {level.level}")
		

		# =========================
		# Sections & enseignants
		# =========================
		sections = [
			{
				"type": s.type_de_cours,
				"teacher": s.enseignant
			}
			for s in doc.table_enseignant
		]

		results.append({
			"name": doc.name,
			"course": doc.course,
			"semestre":doc.semestre,
			"course_title": doc.intitule_cours,
			"ue_code":doc.unite_de_valeur,
			"course_code": course.code if hasattr(course, "code") else "",
			# "is_common": cint(doc.is_common),
			"classes": classes,
			"sections": sections
		})

	return results

@frappe.whitelist()
def get_teaching_unit_by_year(academic_year,faculty=None,field_of_study=None,level=None,teacher=None,semestre=None):
	TeachingUnit = DocType("Teaching Unit")
	Course = DocType("Course")
	CourseTeacherItem = DocType("Course Teacher Item")
	CourseFieldOfStudyLevelItem = DocType("Course Field of study level item")
	CourseFieldOfStudy = DocType("Field of study")

	query = (
		frappe.qb.from_(TeachingUnit)
		.join(Course)
		.on(TeachingUnit.course==Course.name)
		.left_join(CourseTeacherItem)
		.on(CourseTeacherItem.parent == TeachingUnit.name)
		.join(CourseFieldOfStudyLevelItem)
		.on(CourseFieldOfStudyLevelItem.parent == TeachingUnit.name)
		.join(CourseFieldOfStudy)
		.on(CourseFieldOfStudy.name==CourseFieldOfStudyLevelItem.filiere)
		.select(
			TeachingUnit.name,
			Course.nombre_dheure_cm,
			Course.nombre_dheure_tp,
			Course.intitule,
			Course.nombre_dheure_td,
			Course.name.as_("course_name"),
			Course.semestre,
			CourseTeacherItem.enseignant,
			CourseTeacherItem.type_de_cours,
			CourseFieldOfStudyLevelItem.filiere,
			CourseFieldOfStudyLevelItem.niveau,
			CourseFieldOfStudyLevelItem.course_poid,
			CourseFieldOfStudy.faculte	
		)
		.where(
			(TeachingUnit.academic_year == academic_year)
		)	
	)
	if faculty:
		query = query.where(CourseFieldOfStudy.faculte == faculty)

	if field_of_study:
		query = query.where(CourseFieldOfStudy.field_of_study_code==field_of_study)
	
	if level:
		query = query.where(CourseFieldOfStudyLevelItem.niveau==level)

	if semestre:
		query = query.where( TeachingUnit.semestre == semestre )
	
	if teacher:
		query = query.where( CourseTeacherItem.enseignant == teacher )
	
	data = query.run(as_dict = True)
	process_data = {}


	#Pour regrouper les enseignants et les niveau en fonction du cours
	for d in data:
		niveau_key = f"{d.filiere}-{d.niveau}"
		if d.name in process_data:
			if d.enseignant not in process_data[d.name]["enseignant_key"]:
				process_data[d.name]["enseignant"].append({"enseignant":d.enseignant,"type_cours":d.type_de_cours})
				process_data[d.name]["enseignant_key"].append(d.enseignant)
			
			if niveau_key not in process_data[d.name]["niveau_key"]:

				process_data[d.name]["niveau"].append({"filiere":d.filiere,"niveau":d.niveau,"course_poid":d.course_poid})
				process_data[d.name]["niveau_key"].append(niveau_key)
		else:
			process_data[d.name]={
				"enseignant":[{"enseignant":d.enseignant, "type_cours":d.type_de_cours}],
				"enseignant_key":[d.enseignant],
				"niveau":[{"filiere":d.filiere, "niveau":d.niveau, "course_poid":d.course_poid,"faculty":d.faculte}],
				"niveau_key":[niveau_key],
				"course_name":d.course_name,
				"intitule":d.intitule,
				"nombre_dheure_cm":d.nombre_dheure_cm,
				"nombre_dheure_td":d.nombre_dheure_td,
				"nombre_dheure_tp":d.nombre_dheure_tp,
				"semestre":d.semestre,
				"faculte":d.faculte,
				"name":d.name
			}
			
	#On supprime les élements qui ont aidé au traitement
	for key in process_data.keys():
		process_data[key].pop("niveau_key")
		process_data[key].pop("enseignant_key")

	return process_data


	

def get_single_teaching_unit(cours,academic_year):
	if not frappe.db.exists('Teaching Unit', { 'name': cours,"academic_year":academic_year }):
		frappe.throw("Unité d'enseignement introuvable")
	teaching_unit = frappe.get_doc("Teaching Unit",{"name":cours,"academic_year":academic_year})
	return teaching_unit

@frappe.whitelist()
def get_levels_for_field(field_of_study):
	doc = frappe.get_doc("Field of study", field_of_study)
	return [{"level":row.level,"name":row.name} for row in doc.field_of_study_level]


@frappe.whitelist()
def get_levels(doctype, txt, searchfield, start, page_len, filters):
    filiere = filters.get("parent")
    if not filiere:
        return []

    # On utilise frappe.db.sql pour cibler la child table
    # 'name' est l'ID unique de la ligne dans la table enfant
    return frappe.db.sql("""
        SELECT 
            name, 
            level as label
        FROM `tabField of study Level`
        WHERE parent = %s 
        AND (level LIKE %s OR name LIKE %s)
        ORDER BY level
        LIMIT %s, %s
    """, (filiere, f"%{txt}%", f"%{txt}%", start, page_len))

@frappe.whitelist()
def get_teaching_unit_by_level(doctype, txt, searchfield, start, page_len, filters):
	TeachingUnit = DocType("Teaching Unit")
	CourseNiveauFiliere = DocType("Course Field of study level item")
	# print("Doctype ",txt," searchfiled",searchfield)
	query = (
    	frappe.qb.from_(TeachingUnit)
    	.join(CourseNiveauFiliere)
    	.on(CourseNiveauFiliere.parent == TeachingUnit.name)
    	.select(
        	TeachingUnit.name.as_("value"),
			TeachingUnit.intitule_cours.as_("label") 
    	)
    	.where(
        	(CourseNiveauFiliere.filiere == filters.get("filiere")) &
        	(CourseNiveauFiliere.niveau == filters.get("niveau")) &
        	(TeachingUnit.academic_year == filters.get("academic_year")) 
		)
	)
	if txt:
		query = query.where(
			TeachingUnit.intitule_cours.like(f"%{txt}%") |
			TeachingUnit.name.like(f"%{txt}%")
			
		)
	data =  query.run()
	return data

def clean_course_and_ue_by_acaemic_year(academic_year,faculty,filiere,niveau,semestre,proced_cours,proced_ue):
	# teachings = get_teaching_units(academic_year,faculty,filiere,niveau)
	# # print("ue_proceed",proced_ue)
	# print("proceed_cours",proced_cours)
	# print("Teaching value ",teachings)
	# print("Semestre ",semestre)
	# on_delete_ue = []
	# for t in teachings:
	# 	if t['course'] not in proced_cours and t["semestre"]==semestre:
	# 		print("Course to delete ",t)
	# 		on_delete_ue.append(t["ue_code"])
	# 		frappe.delete_doc("Teaching Unit", t['name'])
	# print("ue to delete ",on_delete_ue)
	# for ue_del in on_delete_ue:
	# 	if ue_del not in proced_ue:
	# 		frappe.delete_doc("Teaching Unit Value",ue_del)

	#Todo
	pass


@frappe.whitelist()
def update_teacher_unit(teaching_unit_code,grid_teacher): 
	if isinstance(grid_teacher, str):
		grid_teacher = json.loads(grid_teacher)

	teaching_unit = frappe.get_doc("Teaching Unit",teaching_unit_code)
	teaching_unit.set("table_enseignant", [])
	print("Grid teacher",grid_teacher)
	for t in grid_teacher:
		print("Teacher ",t)
		teaching_unit.append("table_enseignant", {
			"enseignant": t["enseignant"],
			"type_de_cours": t["type_de_cours"]
		})
	teaching_unit.save()

	return True

