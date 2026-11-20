import frappe
from frappe import _

ADMIN_ROLES = {"Administrator", "System Manager"}
PLANNING_ROLES = {"Planning Manager", "Coordonateur", "Coordinateur"}
TEACHER_ROLES = {"Teacher", "Enseignant"}


def _teacher_name(user):
	return frappe.db.get_value("Teacher", {"email": user}, "name")


def _add_unique(target, value):
	if value and value not in target:
		target.append(value)


def get_scope(user=None):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	teacher_name = _teacher_name(user)
	academic_years = frappe.get_all("Academic Year", pluck="name")
	scope = {
		"user": user,
		"roles": sorted(roles),
		"is_admin": user == "Administrator" or bool(roles & ADMIN_ROLES),
		"can_plan": bool(roles & PLANNING_ROLES) or user == "Administrator" or bool(roles & ADMIN_ROLES),
		"can_grade": bool(roles & PLANNING_ROLES) or bool(roles & TEACHER_ROLES) or user == "Administrator" or bool(roles & ADMIN_ROLES),
		"teacher": teacher_name,
		"academic_years": academic_years,
		"faculties": [],
		"filieres": [],
		"niveaux": [],
		"level_labels": [],
		"teaching_units": [],
	}

	if scope["is_admin"]:
		return scope

	if roles & PLANNING_ROLES and teacher_name:
		rows = frappe.db.sql(
			"""
			select fs.name as filiere, fs.faculte as faculty, fsl.name as niveau, fsl.level as level_label
			from `tabField of study Level` fsl
			inner join `tabField of study` fs on fs.name = fsl.parent
			where fsl.coordonateur = %(teacher)s or fsl.gestionnaire_de_planning = %(teacher)s
			""",
			{"teacher": teacher_name},
			as_dict=True,
		)
		for row in rows:
			_add_unique(scope["faculties"], row.faculty)
			_add_unique(scope["filieres"], row.filiere)
			_add_unique(scope["niveaux"], row.niveau)
			_add_unique(scope["level_labels"], row.level_label)
		return scope

	if teacher_name:
		units = frappe.get_all(
			"Course Teacher Item",
			filters={"enseignant": teacher_name},
			pluck="parent",
			distinct=True,
		)
		scope["teaching_units"] = units
		if units:
			for unit in frappe.get_all("Teaching Unit", filters={"name": ["in", units]}, fields=["academic_year"]):
				_add_unique(scope["academic_years"], unit.academic_year)
			for row in frappe.get_all(
				"Course Field of study level item",
				filters={"parent": ["in", units]},
				fields=["filiere", "niveau", "parent"],
			):
				_add_unique(scope["filieres"], row.filiere)
				_add_unique(scope["niveaux"], row.niveau)
				_add_unique(scope["teaching_units"], row.parent)
				faculty = frappe.db.get_value("Field of study", row.filiere, "faculte")
				_add_unique(scope["faculties"], faculty)
				level_label = frappe.db.get_value("Field of study Level", row.niveau, "level")
				_add_unique(scope["level_labels"], level_label)
		return scope

	return scope


def _check_value(label, value, allowed):
	if value and allowed and value not in allowed:
		frappe.throw(
			_("Accès refusé : {0} « {1} » n'est pas dans votre périmètre.").format(label, value),
			frappe.PermissionError,
		)


def assert_can_view_planning(academic_year=None, faculty=None, filiere=None, niveau=None, teacher=None, user=None):
	scope = get_scope(user)
	if scope["is_admin"]:
		return scope
	if not (scope["can_plan"] or scope["teacher"]):
		frappe.throw(_("Accès refusé : vous n'avez pas accès au planning."), frappe.PermissionError)
	_check_value(_("Année académique"), academic_year, scope["academic_years"])
	_check_value(_("Faculté"), faculty, scope["faculties"])
	_check_value(_("Filière"), filiere, scope["filieres"])
	_check_value(_("Niveau"), niveau, scope["niveaux"])
	if teacher and teacher != scope["teacher"] and not scope["can_plan"]:
		frappe.throw(_("Accès refusé : vous ne pouvez consulter que votre propre planning."), frappe.PermissionError)
	return scope


def assert_can_plan(academic_year=None, faculty=None, filiere=None, niveau=None, teaching_unit=None, user=None):
	scope = get_scope(user)
	if not scope["can_plan"]:
		frappe.throw(
			_("Accès refusé : seuls les coordinateurs et gestionnaires de planning peuvent modifier le planning."),
			frappe.PermissionError,
		)
	if scope["is_admin"]:
		return scope
	_check_value(_("Année académique"), academic_year, scope["academic_years"])
	_check_value(_("Faculté"), faculty, scope["faculties"])
	_check_value(_("Filière"), filiere, scope["filieres"])
	_check_value(_("Niveau"), niveau, scope["niveaux"])
	if teaching_unit:
		unit = frappe.db.get_value("Teaching Unit", teaching_unit, "name")
		if not unit:
			frappe.throw(_("Unité d'enseignement introuvable."), frappe.ValidationError)
		if unit not in scope["teaching_units"]:
			levels = frappe.get_all(
				"Course Field of study level item",
				filters={"parent": unit},
				fields=["filiere", "niveau"],
			)
			if not levels or any(
				row.filiere not in scope["filieres"] or row.niveau not in scope["niveaux"]
				for row in levels
			):
				frappe.throw(_("Accès refusé : cette unité d'enseignement est hors de votre périmètre."), frappe.PermissionError)
	return scope


def assert_can_manage_grid(academic_year=None, faculty=None, filiere=None, niveau=None, semestre=None, user=None):
	scope = assert_can_plan(academic_year, faculty, filiere, niveau, user=user)
	if semestre and not scope["is_admin"]:
		unit_semesters = frappe.get_all(
			"Teaching Unit",
			filters={"name": ["in", scope["teaching_units"]]},
			pluck="semestre",
			distinct=True,
		)
		if scope["teaching_units"] and unit_semesters and semestre not in unit_semesters:
			frappe.throw(_("Accès refusé : ce semestre est hors de votre périmètre."), frappe.PermissionError)
	return scope


def assert_can_manage_notes(teaching_unit=None, user=None):
	scope = get_scope(user)
	if not scope["can_grade"]:
		frappe.throw(_("Accès refusé : vous n'avez pas accès à la saisie des notes."), frappe.PermissionError)
	if scope["is_admin"] or scope["can_plan"]:
		return scope
	if teaching_unit and teaching_unit not in scope["teaching_units"]:
		frappe.throw(_("Accès refusé : cette unité d'enseignement est hors de votre périmètre."), frappe.PermissionError)
	return scope
