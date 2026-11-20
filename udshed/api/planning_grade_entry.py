import frappe
from frappe import _
import json

import udshed.api.planning_permission as planning_permission


def _session_type(planning_type):
	planning_type = planning_type or ""
	if "CC" in planning_type or "Controlle Continue" in planning_type:
		return "Controlle Continue (CC)"
	if "rattrapage" in planning_type.lower():
		return "Examen de rattrapage"
	if "Examen de session normal" in planning_type:
		return "Examen de session normal"
	return None


def _find_session(planning_name):
	if not frappe.db.has_column("Session Examen", "planning"):
		return None
	return frappe.db.sql(
		"select name from `tabSession Examen` where planning = %s limit 1",
		(planning_name,),
		as_dict=True,
	)


def _link_session(planning_name, session_name):
	if frappe.db.has_column("Session Examen", "planning"):
		frappe.db.sql(
			"update `tabSession Examen` set planning = %s where name = %s",
			(planning_name, session_name),
		)


def _existing_cc(note):
	for row in note.get("notes_cc") or []:
		if row.note_cc is not None:
			return row.note_cc
	return None


@frappe.whitelist()
def get_students_for_grade_entry(planning_item_name):
	try:
		planning = frappe.get_doc("Planning Item", planning_item_name)
		tu = frappe.get_doc("Teaching Unit", planning.cours)
		planning_permission.assert_can_manage_notes(tu.name)
		students = frappe.db.sql(
			"""
			SELECT DISTINCT s.name AS student, s.matricule, s.nom, s.prenom
			FROM `tabAcademic Reregistration` ar
			INNER JOIN `tabReregistration Course Item` rci
				ON rci.parent = ar.name AND rci.parenttype = 'Academic Reregistration'
			INNER JOIN `tabStudent` s ON s.name = ar.student
			WHERE ar.academic_year = %(academic_year)s
				AND ar.statut = 'Validée'
				AND rci.teaching_unit = %(teaching_unit)s
			ORDER BY s.nom, s.prenom
			""",
			{"academic_year": planning.academic_year, "teaching_unit": tu.name},
			as_dict=True,
		)
		session_rows = _find_session(planning_item_name)
		session_name = session_rows[0].name if session_rows else None
		existing_notes = {}
		if session_name:
			for note in frappe.get_all(
				"Session Examen Note",
				{"session_examen": session_name, "teaching_unit": tu.name},
				["name", "student", "note_cc_moyenne", "note_examen", "note_examen_rattrapage"],
			):
				note["note_cc"] = _existing_cc(note)
				existing_notes[note.student] = note
		result = []
		for student in students:
			entry = {
				"student": student.student,
				"matricule": student.matricule,
				"nom": "{0} {1}".format(student.nom or "", student.prenom or "").strip(),
				"credits": tu.credits,
				"note_entry_name": None,
				"note_cc": None,
				"note_examen": None,
				"note_examen_rattrapage": None,
			}
			existing = existing_notes.get(student.student)
			if existing:
				entry.update({
					"note_entry_name": existing.name,
					"note_cc": existing.note_cc,
					"note_examen": existing.note_examen,
					"note_examen_rattrapage": existing.note_examen_rattrapage,
				})
			result.append(entry)
		return {
			"planning": {
				"name": planning.name,
				"type": planning.type,
				"teaching_unit": tu.name,
				"intitule_cours": tu.intitule_cours or tu.name,
				"academic_year": planning.academic_year,
				"credits": tu.credits,
				"semestre": tu.semestre,
				"session_type": _session_type(planning.type),
			},
			"students": result,
			"existing_session": session_name,
		}
	except (frappe.ValidationError, frappe.PermissionError):
		raise
	except Exception:
		frappe.log_error(title="planning_grade_entry get_students", message=frappe.get_traceback())
		frappe.throw(_("Erreur lors du chargement des étudiants pour la saisie des notes."))


@frappe.whitelist()
def save_bulk_grades(planning_item_name, grades):
	if isinstance(grades, str):
		grades = frappe.parse_json(grades)
	if not isinstance(grades, list):
		frappe.throw(_("Données de notes invalides."), frappe.ValidationError)
	try:
		planning = frappe.get_doc("Planning Item", planning_item_name)
		tu = frappe.get_doc("Teaching Unit", planning.cours)
		planning_permission.assert_can_manage_notes(tu.name)
		session_type = _session_type(planning.type)
		if not session_type:
			frappe.throw(
				_("Le type « {0} » ne correspond pas à une session de notes. Choisissez une CC ou un examen.").format(
					planning.type
				)
			)
		session_rows = _find_session(planning_item_name)
		session_name = session_rows[0].name if session_rows else _create_session_examen(planning, tu, session_type)
		_link_session(planning_item_name, session_name)
		has_tp = any("TP" in (row.type_de_cours or "") for row in (tu.table_enseignant or []))
		type_ue = "Avec TP" if has_tp else "Sans TP"
		created_notes = []
		errors = []
		for grade in grades:
			student = grade.get("student")
			raw_value = grade.get("note")
			if raw_value in (None, ""):
				continue
			try:
				value = float(raw_value)
				if value < 0 or value > 20:
					errors.append("{0}: note {1} invalide (0-20)".format(student, value))
					continue
				note_doc = None
				if grade.get("note_entry_name"):
					note_doc = frappe.get_doc("Session Examen Note", grade.get("note_entry_name"))
				else:
					existing = frappe.db.get_value(
						"Session Examen Note",
						{"session_examen": session_name, "student": student, "teaching_unit": tu.name},
						"name",
					)
					if existing:
						note_doc = frappe.get_doc("Session Examen Note", existing)
				if not note_doc:
					note_doc = frappe.new_doc("Session Examen Note")
					note_doc.session_examen = session_name
					note_doc.student = student
					note_doc.teaching_unit = tu.name
					note_doc.filiere = frappe.db.get_value(
						"Course Field of study level item", {"parent": tu.name}, "filiere"
					)
					note_doc.niveau = frappe.db.get_value(
						"Field of study Level",
						frappe.db.get_value("Course Field of study level item", {"parent": tu.name}, "niveau"),
						"level",
					)
				note_doc.type_ue = type_ue
				note_doc.statut = "Saisi"
				note_doc.set("notes_cc", [])
				if session_type == "Controlle Continue (CC)":
					note_doc.append("notes_cc", {"cc_label": "CC", "cc_weight": 100, "note_cc": value})
				elif session_type == "Examen de rattrapage":
					note_doc.note_examen_rattrapage = value
				else:
					note_doc.note_examen = value
				note_doc.save(ignore_permissions=True)
				created_notes.append({
					"name": note_doc.name,
					"student": student,
					"note_finale": note_doc.note_finale,
					"note_pct": note_doc.note_pct,
					"grade": note_doc.grade,
					"mention": note_doc.mention,
					"statut": note_doc.statut,
				})
			except Exception as exc:
				errors.append("{0}: {1}".format(student, str(exc)))
		return {
			"status": "success" if not errors else "partial",
			"session_examen": session_name,
			"created_notes": created_notes,
			"errors": errors,
		}
	except (frappe.ValidationError, frappe.PermissionError):
		raise
	except Exception:
		frappe.log_error(title="planning_grade_entry save_bulk", message=frappe.get_traceback())
		frappe.throw(_("Erreur lors de la sauvegarde des notes en bloc."))


def _create_session_examen(planning, tu, session_type):
	calendar_name = None
	for row in tu.course_levels:
		if row.niveau:
			calendar_name = frappe.db.get_value("Field of study Level", row.niveau, "calendrier")
			if calendar_name:
				break
	if not calendar_name:
		calendar_name = frappe.db.get_value("Calendar Planing", {}, "name")
	session = frappe.new_doc("Session Examen")
	session.academic_year = planning.academic_year
	session.calendar = calendar_name
	session.type_dexamen = session_type
	session.date_debut = planning.date
	session.date_de_fin = planning.date
	session.semestre = tu.semestre
	session.statut = "Brouillon"
	seen = set()
	for row in tu.course_levels:
		key = (row.filiere, row.niveau)
		if key in seen:
			continue
		seen.add(key)
		session.append("classes_concernees", {"filiere": row.filiere, "niveau": row.niveau})
	session.insert(ignore_permissions=True)
	_link_session(planning.name, session.name)
	return session.name
