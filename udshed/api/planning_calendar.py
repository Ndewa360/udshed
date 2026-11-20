import frappe
from frappe import _
from frappe.query_builder import DocType
from datetime import date, datetime

import udshed.api.course as course
import udshed.api.planning_permission as planning_permission


def parse_date(value):
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	if isinstance(value, str) and "T" in value:
		return datetime.fromisoformat(value).date()
	return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def _throw(message, exception=frappe.ValidationError):
	frappe.throw(_(message), exception)


def _log():
	frappe.log_error(title="planning_calendar", message=frappe.get_traceback())


def _resolve_period(half_day):
	if not half_day:
		_throw("Aucun créneau horaire sélectionné.")
	if frappe.db.exists("Planning Period", half_day):
		return half_day
	period = frappe.db.get_value("Planning Period", {"libelle": half_day}, "name")
	if period:
		return period
	_throw("Créneau horaire introuvable : {0}".format(half_day))
	return None


def _unit_info(unit_name):
	if not unit_name or not frappe.db.exists("Teaching Unit", unit_name):
		_throw("Unité d'enseignement introuvable.")
	teachers = frappe.get_all(
		"Course Teacher Item",
		filters={"parent": unit_name},
		pluck="enseignant",
		distinct=True,
	)
	levels = frappe.get_all(
		"Course Field of study level item",
		filters={"parent": unit_name},
		fields=["filiere", "niveau", "course_poid"],
	)
	return {
		"name": unit_name,
		"intitule": frappe.db.get_value("Teaching Unit", unit_name, "intitule_cours") or unit_name,
		"teachers": [teacher for teacher in teachers if teacher],
		"levels": levels,
	}


def _level_label(niveau):
	if not niveau:
		return ""
	label = frappe.db.get_value("Field of study Level", niveau, "level")
	return label or niveau


def _check_conflicts(unit_info, day_date, period, salle, exclude_name=None):
	filters = {"date": day_date, "period": period}
	if exclude_name:
		filters["name"] = ["!=", exclude_name]
	existing = frappe.get_all(
		"Planning Item",
		filters=filters,
		fields=["name", "cours", "salle", "batiment"],
	)
	for row in existing:
		other = _unit_info(row.cours)
		common_levels = {
			(level.filiere, level.niveau)
			for level in unit_info["levels"]
		} & {
			(level.filiere, level.niveau)
			for level in other["levels"]
		}
		if common_levels:
			labels = ", ".join(
				"{0} {1}".format(filiere, _level_label(niveau))
				for filiere, niveau in sorted(common_levels)
			)
			_throw(
				"Conflit de planning : les classes {0} sont déjà occupées par « {1} » sur ce créneau.".format(
					labels, other["intitule"]
				)
			)
		common_teachers = set(unit_info["teachers"]) & set(other["teachers"])
		if common_teachers:
			_throw(
				"Conflit de planning : les enseignants {0} sont déjà programmés sur ce créneau.".format(
					", ".join(sorted(common_teachers))
				)
			)
		if salle and row.salle == salle:
			_throw(
				"Conflit de salle : « {0} » est déjà utilisée par « {1} » sur ce créneau.".format(
					salle, other["intitule"]
				)
			)


@frappe.whitelist()
def get_week_planning(academic_year, week_start, filiere=None, niveau=None, teacher=None, faculty=None):
	try:
		planning_permission.assert_can_view_planning(academic_year, faculty, filiere, niveau, teacher)
		PlanningItem = DocType("Planning Item")
		TeachingUnit = DocType("Teaching Unit")
		Course = DocType("Course")
		CourseNiveauFiliere = DocType("Course Field of study level item")
		CourseEnseignant = DocType("Course Teacher Item")
		FieldOfStudy = DocType("Field of study")
		date_week_start = parse_date(week_start)

		query = (
			frappe.qb.from_(PlanningItem)
			.join(TeachingUnit)
			.on(PlanningItem.cours == TeachingUnit.name)
			.join(Course)
			.on(TeachingUnit.course == Course.name)
			.join(CourseNiveauFiliere)
			.on(CourseNiveauFiliere.parent == TeachingUnit.name)
			.join(FieldOfStudy)
			.on(FieldOfStudy.name == CourseNiveauFiliere.filiere)
			.left_join(CourseEnseignant)
			.on(CourseEnseignant.parent == TeachingUnit.name)
			.select(
				TeachingUnit.course,
				Course.intitule.as_("course_label"),
				PlanningItem.salle,
				PlanningItem.batiment,
				PlanningItem.name,
				PlanningItem.type,
				PlanningItem.cours,
				PlanningItem.date,
				PlanningItem.period,
				PlanningItem.mode,
				CourseNiveauFiliere.niveau,
				CourseNiveauFiliere.filiere,
				FieldOfStudy.faculte.as_("faculty"),
				CourseEnseignant.enseignant,
			)
			.where(
				(PlanningItem.academic_year == academic_year)
				& (PlanningItem.date >= date_week_start)
				& (PlanningItem.date < frappe.utils.add_days(date_week_start, 7))
			)
			.distinct()
		)
		if faculty:
			query = query.where(FieldOfStudy.faculte == faculty)
		if filiere:
			query = query.where(CourseNiveauFiliere.filiere == filiere)
		if niveau:
			query = query.where(CourseNiveauFiliere.niveau == niveau)
		if teacher:
			query = query.where(CourseEnseignant.enseignant == teacher)

		data = query.run(as_dict=True)
		seen = {}
		for row in data:
			pid = row.name
			if pid not in seen:
				row._teachers = [row.enseignant] if row.enseignant else []
				seen[pid] = row
			elif row.enseignant and row.enseignant not in seen[pid]._teachers:
				seen[pid]._teachers.append(row.enseignant)

		teacher_cache = {}
		room_cache = {}
		for doc in seen.values():
			doc["teacher_ids"] = [t for t in (doc._teachers or []) if t]
			doc["teachers"] = [_format_teacher(t, teacher_cache) for t in doc["teacher_ids"]]
			doc["enseignant"] = doc["teachers"][0] if doc["teachers"] else ""
			del doc["_teachers"]
			doc["niveau_label"] = _level_label(doc.niveau)
			doc["salle"] = _room_code(doc.salle, room_cache)
			doc["batiment"] = _batiment_code(doc.batiment, room_cache)
		return list(seen.values())
	except (frappe.ValidationError, frappe.PermissionError):
		raise
	except Exception:
		_log()
		_throw("Erreur lors du chargement du planning.")


def _format_teacher(teacher, cache):
	if not teacher:
		return ""
	if teacher not in cache:
		row = frappe.db.get_value(
			"Teacher", teacher, ["grade", "first_name", "last_name"], as_dict=True
		)
		cache[teacher] = (
			" ".join(part for part in [row.grade or "", row.first_name or "", row.last_name or ""] if part).strip()
			if row
			else teacher
		)
	return cache[teacher]


def _room_code(room, cache):
	if not room:
		return ""
	if room not in cache:
		cache[room] = frappe.db.get_value("Room", room, "code") or ""
	return cache[room]


def _batiment_code(batiment, cache):
	if not batiment:
		return ""
	key = "b:" + batiment
	if key not in cache:
		cache[key] = frappe.db.get_value("Building", batiment, "code") or ""
	return cache[key]


@frappe.whitelist()
def create_planning(academic_year, cours, course_type, day_of_week, half_day, batiment=None, salle=None, mode="En présentiel"):
	try:
		period = _resolve_period(half_day)
		day_date = parse_date(day_of_week)
		teaching_unit = course.get_single_teaching_unit(cours, academic_year)
		unit_info = _unit_info(teaching_unit.name)
		faculty = frappe.db.get_value("Field of study", unit_info["levels"][0].filiere, "faculte") if unit_info["levels"] else None
		scope = planning_permission.assert_can_plan(
			academic_year,
			faculty,
			unit_info["levels"][0].filiere if unit_info["levels"] else None,
			unit_info["levels"][0].niveau if unit_info["levels"] else None,
			teaching_unit.name,
		)
		if not unit_info["teachers"]:
			_throw("Le cours « {0} » n'a pas d'enseignant assigné.".format(unit_info["intitule"]))
		_check_conflicts(unit_info, day_date, period, salle)
		with planning_permission.as_coordinator(scope):
			planning = frappe.get_doc({
				"doctype": "Planning Item",
				"cours": teaching_unit.name,
				"type": course_type,
				"date": day_date,
				"period": period,
				"academic_year": academic_year,
				"batiment": batiment,
				"salle": salle,
				"mode": mode,
			})
			planning.insert(ignore_permissions=True)
		return {"status": True, "data": planning.as_dict()}
	except (frappe.ValidationError, frappe.PermissionError):
		raise
	except Exception:
		_log()
		_throw("Erreur lors de la création du planning.")


@frappe.whitelist()
def update_planning(planning_item_name, academic_year, cours, course_type, day_of_week, half_day, batiment=None, salle=None, mode="En présentiel"):
	try:
		planning_item = frappe.get_doc("Planning Item", planning_item_name)
		period = _resolve_period(half_day)
		day_date = parse_date(day_of_week)
		teaching_unit = course.get_single_teaching_unit(cours, academic_year)
		unit_info = _unit_info(teaching_unit.name)
		faculty = frappe.db.get_value("Field of study", unit_info["levels"][0].filiere, "faculte") if unit_info["levels"] else None
		scope = planning_permission.assert_can_plan(
			academic_year,
			faculty,
			unit_info["levels"][0].filiere if unit_info["levels"] else None,
			unit_info["levels"][0].niveau if unit_info["levels"] else None,
			teaching_unit.name,
		)
		if not unit_info["teachers"]:
			_throw("Le cours « {0} » n'a pas d'enseignant assigné.".format(unit_info["intitule"]))
		_check_conflicts(unit_info, day_date, period, salle, planning_item_name)
		planning_item.cours = teaching_unit.name
		planning_item.type = course_type
		planning_item.date = day_date
		planning_item.period = period
		planning_item.academic_year = academic_year
		planning_item.mode = mode
		planning_item.batiment = batiment
		planning_item.salle = salle
		with planning_permission.as_coordinator(scope):
			planning_item.save(ignore_permissions=True)
		return {"status": True, "data": planning_item.as_dict()}
	except (frappe.ValidationError, frappe.PermissionError):
		raise
	except Exception:
		_log()
		_throw("Erreur lors de la modification du planning.")


@frappe.whitelist()
def delete_planning(planning_name):
	try:
		planning = frappe.get_doc("Planning Item", planning_name)
		unit = frappe.db.get_value("Teaching Unit", planning.cours, "name")
		levels = frappe.get_all(
			"Course Field of study level item",
			filters={"parent": unit},
			fields=["filiere", "niveau"],
		) if unit else []
		faculty = frappe.db.get_value("Field of study", levels[0].filiere, "faculte") if levels else None
		scope = planning_permission.assert_can_plan(
			planning.academic_year,
			faculty,
			levels[0].filiere if levels else None,
			levels[0].niveau if levels else None,
			unit,
		)
		with planning_permission.as_coordinator(scope):
			planning.delete(ignore_permissions=True)
		return True
	except (frappe.ValidationError, frappe.PermissionError):
		raise
	except Exception:
		_log()
		_throw("Erreur lors de la suppression du planning.")


@frappe.whitelist()
def get_planning_type(field_of_study_level, week_start, academic_year):
	try:
		filiere = (
			frappe.db.get_value("Field of study Level", field_of_study_level, "parent")
			if field_of_study_level else None
		)
		faculty = frappe.db.get_value("Field of study", filiere, "faculte") if filiere else None
		planning_permission.assert_can_view_planning(academic_year, faculty, filiere, field_of_study_level or None)
		if not field_of_study_level:
			return "Cours"
		week_start_date = parse_date(week_start)
		session_exam = frappe.get_all(
			"Session Examen",
			filters=[
				["academic_year", "=", academic_year],
				["date_debut", "<=", week_start_date],
				["date_de_fin", ">=", week_start_date],
				["Session Examen Field of study Level", "niveau", "=", field_of_study_level],
			],
			fields=["name"],
			distinct=True,
		)
		return "Examen" if session_exam else "Cours"
	except (frappe.ValidationError, frappe.PermissionError):
		raise
	except Exception:
		_log()
		_throw("Erreur lors de la détermination du type de planning.")
