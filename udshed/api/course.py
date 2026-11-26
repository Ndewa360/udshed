import frappe
from frappe.utils import cint
from frappe.query_builder import DocType
import json

import udshed.api.planning_permission as planning_permission


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

	scope = planning_permission.assert_can_view_planning(academic_year, faculty, filiere, niveau, require_filters=False)
	filters = scope["filters"]
	academic_year = filters["academic_year"] or academic_year
	faculty = filters["faculty"]
	filiere = filters["filiere"]
	niveau = filters["niveau"]

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
			nom_filiere = frappe.db.get_value("Field of study", c.filiere, "name_of_field") or c.filiere
			classes.append(f"{nom_filiere} — {level.level}")
		

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

def get_single_teaching_unit(cours,academic_year):
	if not frappe.db.exists('Teaching Unit', { 'name': cours,"academic_year":academic_year }):
		frappe.throw("Unité d'enseignement introuvable")
	teaching_unit = frappe.get_doc("Teaching Unit",{"name":cours,"academic_year":academic_year})
	return teaching_unit

@frappe.whitelist()
def get_levels_for_field(field_of_study):
	planning_permission.assert_can_view_planning(filiere=field_of_study, require_filters=False)
	doc = frappe.get_doc("Field of study", field_of_study)
	return [{"level":row.level,"name":row.name} for row in doc.field_of_study_level]


@frappe.whitelist()
def get_levels(doctype, txt, searchfield, start, page_len, filters):
    filiere = filters.get("parent")
    if not filiere:
        return []
    planning_permission.assert_can_view_planning(filiere=filiere, require_filters=False)

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
	filters = filters or {}
	planning_permission.assert_can_view_planning(
		filters.get("academic_year"),
		filters.get("faculty"),
		filters.get("filiere"),
		filters.get("niveau"),
		require_filters=False,
	)
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

def clean_course_and_ue_by_academic_year(academic_year, faculty, filiere, niveau, semestre, proced_cours, proced_ue):
	teaching_units = frappe.get_all(
		"Teaching Unit",
		filters={"academic_year": academic_year, "semestre": semestre},
		fields=["name", "course", "unite_de_valeur"],
	)
	kept_units = set(proced_cours or [])
	kept_ues = set(proced_ue or [])
	deleted_units = []
	for unit in teaching_units:
		if unit.course in kept_units:
			continue
		levels = frappe.get_all(
			"Course Field of study level item",
			filters={"parent": unit.name, "filiere": filiere, "niveau": niveau},
			pluck="name",
		)
		if not levels:
			continue
		frappe.delete_doc("Course Field of study level item", levels[0], ignore_permissions=True)
		remaining = frappe.db.count("Course Field of study level item", {"parent": unit.name})
		planning_count = frappe.db.count("Planning Item", {"cours": unit.name})
		if not remaining and not planning_count:
			ue_name = unit.unite_de_valeur
			frappe.delete_doc("Teaching Unit", unit.name, ignore_permissions=True)
			deleted_units.append(unit.name)
			if ue_name and ue_name not in kept_ues:
				other_units = frappe.db.count("Teaching Unit", {"unite_de_valeur": ue_name})
				if not other_units:
					frappe.delete_doc("Teaching Unit Value", ue_name, ignore_permissions=True)
	return deleted_units


def clean_course_and_ue_by_acaemic_year(academic_year, faculty, filiere, niveau, semestre, proced_cours, proced_ue):
	return clean_course_and_ue_by_academic_year(
		academic_year, faculty, filiere, niveau, semestre, proced_cours, proced_ue
	)


@frappe.whitelist()
def update_teacher_unit(teaching_unit_code, grid_teacher):
	if isinstance(grid_teacher, str):
		grid_teacher = frappe.parse_json(grid_teacher)
	scope = planning_permission.assert_can_plan(teaching_unit=teaching_unit_code)
	with planning_permission.as_coordinator(scope):
		teaching_unit = frappe.get_doc("Teaching Unit", teaching_unit_code)
		teaching_unit.set("table_enseignant", [])
		for teacher in grid_teacher or []:
			teaching_unit.append("table_enseignant", {
				"enseignant": teacher.get("enseignant"),
				"type_de_cours": teacher.get("type_de_cours"),
			})
		teaching_unit.save(ignore_permissions=True)
	return True

