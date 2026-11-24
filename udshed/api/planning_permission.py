from contextlib import contextmanager

import frappe
from frappe import _

ADMIN_ROLES = {"Administrator", "System Manager"}
PLANNING_ROLES = {"Planning Manager", "Coordonateur"}
TEACHER_ROLES = {"Teacher"}
DOCTYPES_WITH_PLANNING_PERMISSION = ("Planning Item", "Teaching Unit")


def _teacher_name(user):
	return frappe.db.get_value("Teacher", {"email": user}, "name")


def _add_unique(target, value):
	value = str(value) if value is not None else None
	if value and value not in target:
		target.append(value)


def _current_academic_year():
	return frappe.db.get_single_value("Udshed Setting", "current_year")


@contextmanager
def as_coordinator(scope):
	"""Conservé pour compatibilité : n'usurpe plus aucune identité.

	L'ancienne version appelait `frappe.set_user(coordinateur)` en pleine
	requête : Frappe réinitialise alors `session.sid`, `session.data`,
	`form_dict` et le cache, et la « restauration » ne rétablissait ni le vrai
	sid ni la session. L'historique (owner / modified_by) attribuait en plus
	l'action au coordinateur au lieu de son auteur réel. Les écritures se font
	désormais au nom de l'utilisateur connecté (déjà autorisé par assert_can_plan).
	"""
	yield


def ensure_planning_manager_role(teacher_name):
	if not teacher_name:
		return False
	email = frappe.db.get_value("Teacher", teacher_name, "email")
	if not email:
		return False
	user = frappe.db.get_value("User", {"email": email}, "name")
	if not user:
		return False
	user_doc = frappe.get_doc("User", user)
	if any(row.role == "Planning Manager" for row in user_doc.roles):
		return False
	user_doc.append("roles", {"role": "Planning Manager"})
	user_doc.save(ignore_permissions=True)
	return True


def sync_role_permissions():
	added = []
	for doctype_name in DOCTYPES_WITH_PLANNING_PERMISSION:
		doc = frappe.get_doc("DocType", doctype_name)
		if any(row.role == "Planning Manager" for row in doc.permissions):
			continue
		template = next((row for row in doc.permissions if row.role == "Coordonateur"), None)
		if not template:
			continue
		new_row = doc.append("permissions", {
			"role": "Planning Manager",
			"read": template.read,
			"write": template.write,
			"create": template.create,
			"delete": template.delete,
			"submit": template.submit,
			"cancel": template.cancel,
			"amend": template.amend,
			"email": template.email,
			"export": template.export,
			"print": template.print,
			"report": template.report,
			"share": template.share,
			"permlevel": template.permlevel or 0,
		})
		doc.save(ignore_permissions=True)
		added.append("{0}:{1}".format(doctype_name, new_row.name))
	for teacher_name in frappe.get_all(
		"Field of study Level",
		filters={"gestionnaire_de_planning": ["is", "set"]},
		pluck="gestionnaire_de_planning",
		distinct=True,
	):
		if ensure_planning_manager_role(teacher_name):
			added.append("role:{0}".format(teacher_name))
	return added


def get_scope(user=None):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	teacher_name = _teacher_name(user)
	academic_years = frappe.get_all("Academic Year", pluck="name") if user == "Administrator" or roles & ADMIN_ROLES else []
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
		"teachers": [],
		"filters": {},
	}

	if scope["is_admin"]:
		return scope

	if roles & PLANNING_ROLES:
		if not teacher_name:
			scope["can_plan"] = False
			return scope
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
		if not rows:
			scope["can_plan"] = False
		for row in rows:
			_add_unique(scope["faculties"], row.faculty)
			_add_unique(scope["filieres"], row.filiere)
			_add_unique(scope["niveaux"], row.niveau)
			_add_unique(scope["level_labels"], row.level_label)
		if scope["filieres"] and scope["niveaux"]:
			parents = frappe.get_all(
				"Course Field of study level item",
				filters={"filiere": ["in", scope["filieres"]], "niveau": ["in", scope["niveaux"]]},
				pluck="parent",
				distinct=True,
			)
			for unit in parents:
				_add_unique(scope["teaching_units"], unit)
			if scope["teaching_units"]:
				for year in frappe.get_all(
					"Teaching Unit",
					filters={"name": ["in", scope["teaching_units"]]},
					pluck="academic_year",
					distinct=True,
				):
					_add_unique(scope["academic_years"], year)
				for name in frappe.get_all(
					"Course Teacher Item",
					filters={"parent": ["in", scope["teaching_units"]]},
					pluck="enseignant",
					distinct=True,
				):
					_add_unique(scope["teachers"], name)
		if not scope["academic_years"]:
			_add_unique(scope["academic_years"], _current_academic_year())
		return scope

	if teacher_name:
		units = frappe.get_all(
			"Course Teacher Item",
			filters={"enseignant": teacher_name},
			pluck="parent",
			distinct=True,
		)
		# Cours liés (même enseignement sous un autre intitulé) : l'enseignant
		# assure la séance commune pour les classes de ces cours aussi.
		from udshed.utils.planning_conflits import groupe_du_cours

		units = sorted({u for unit in units for u in groupe_du_cours(unit)})
		scope["teaching_units"] = units
		scope["teachers"] = [teacher_name]
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
		if not scope["academic_years"]:
			_add_unique(scope["academic_years"], _current_academic_year())
		return scope

	return scope


def _check_value(label, value, allowed):
	if value is None or value == "":
		return
	if not allowed or str(value) not in {str(item) for item in allowed}:
		frappe.throw(
			_("Accès refusé : {0} « {1} » n'est pas dans votre périmètre.").format(label, value),
			frappe.PermissionError,
		)


def _normalize_filters(scope, academic_year, faculty, filiere, niveau, teacher, require_filters=True):
	filters = {
		"academic_year": academic_year or None,
		"faculty": faculty or None,
		"filiere": filiere or None,
		"niveau": niveau or None,
		"teacher": teacher or None,
	}
	if scope["is_admin"]:
		scope["filters"] = filters
		return scope

	if filters["niveau"] and not filters["filiere"]:
		filters["filiere"] = frappe.db.get_value("Field of study Level", filters["niveau"], "parent")
	if filters["filiere"] and not filters["faculty"]:
		filters["faculty"] = frappe.db.get_value("Field of study", filters["filiere"], "faculte")
	if filters["filiere"] and filters["niveau"]:
		parent = frappe.db.get_value("Field of study Level", filters["niveau"], "parent")
		if parent and str(parent) != str(filters["filiere"]):
			frappe.throw(_("Accès refusé : ce niveau n'appartient pas à la filière sélectionnée."), frappe.PermissionError)

	if not scope["can_plan"]:
		if filters["teacher"] and filters["teacher"] != scope["teacher"]:
			frappe.throw(_("Accès refusé : vous ne pouvez consulter que votre propre planning."), frappe.PermissionError)
		if not filters["teacher"] and scope["teacher"]:
			filters["teacher"] = scope["teacher"]
	elif filters["teacher"] and scope["teachers"]:
		_check_value(_("Enseignant"), filters["teacher"], scope["teachers"])

	if require_filters:
		if not filters["academic_year"]:
			frappe.throw(_("Une année académique est requise pour consulter le planning."), frappe.ValidationError)
		if not (filters["teacher"] or (filters["filiere"] and filters["niveau"])):
			frappe.throw(
				_("Sélectionnez une filière et un niveau, ou un enseignant, pour consulter le planning."),
				frappe.ValidationError,
			)

	_check_value(_("Année académique"), filters["academic_year"], scope["academic_years"])
	_check_value(_("Faculté"), filters["faculty"], scope["faculties"])
	_check_value(_("Filière"), filters["filiere"], scope["filieres"])
	_check_value(_("Niveau"), filters["niveau"], scope["niveaux"])
	scope["filters"] = filters
	return scope


def assert_can_view_planning(academic_year=None, faculty=None, filiere=None, niveau=None, teacher=None, user=None, require_filters=True):
	scope = get_scope(user)
	if scope["is_admin"]:
		return _normalize_filters(scope, academic_year, faculty, filiere, niveau, teacher, require_filters)
	if not (scope["can_plan"] or scope["teacher"]):
		frappe.throw(_("Accès refusé : vous n'avez pas accès au planning."), frappe.PermissionError)
	return _normalize_filters(scope, academic_year, faculty, filiere, niveau, teacher, require_filters)


def assert_can_plan(academic_year=None, faculty=None, filiere=None, niveau=None, teaching_unit=None, user=None, require_filters=True):
	scope = get_scope(user)
	if not scope["can_plan"]:
		frappe.throw(
			_("Accès refusé : seuls les coordinateurs et gestionnaires de planning peuvent modifier le planning."),
			frappe.PermissionError,
		)
	if scope["is_admin"]:
		scope["acting_user"] = scope["user"]
		return _normalize_filters(scope, academic_year, faculty, filiere, niveau, None, require_filters)

	if teaching_unit:
		academic_year, filiere, niveau = _classe_planifiee(scope, teaching_unit, academic_year, filiere, niveau)

	_normalize_filters(scope, academic_year, faculty, filiere, niveau, None, require_filters)
	scope["acting_user"] = scope["user"]
	return scope


def _classe_planifiee(scope, teaching_unit, academic_year, filiere, niveau):
	"""Classe (filière, niveau) pour laquelle l'utilisateur agit sur ce cours.

	Un cours de tronc commun appartient à plusieurs classes, souvent gérées par
	des coordinateurs différents. Il suffit que la classe planifiée soit dans le
	périmètre de l'utilisateur et suive ce cours (cours liés compris) ;
	auparavant TOUTES les classes du cours devaient l'être, ce qui empêchait
	chaque coordinateur de planifier le tronc commun.
	"""
	from udshed.utils.planning_conflits import classes_du_cours

	unit = frappe.db.get_value("Teaching Unit", teaching_unit, ["name", "academic_year"], as_dict=True)
	if not unit:
		frappe.throw(_("Unité d'enseignement introuvable."), frappe.ValidationError)
	classes = classes_du_cours(teaching_unit)
	if not classes:
		frappe.throw(_("Ce cours n'est rattaché à aucune classe."), frappe.ValidationError)

	niveaux_perimetre = {str(n) for n in scope["niveaux"]}
	if niveau:
		if not any(str(n) == str(niveau) for _f, n in classes):
			frappe.throw(
				_("Ce cours n'est pas au programme de la classe sélectionnée."), frappe.ValidationError
			)
		filiere = filiere or next(f for f, n in classes if str(n) == str(niveau))
	else:
		dans_perimetre = sorted((f, n) for f, n in classes if n in niveaux_perimetre)
		if not dans_perimetre:
			frappe.throw(
				_("Accès refusé : ce cours n'est rattaché à aucune classe de votre périmètre."),
				frappe.PermissionError,
			)
		filiere, niveau = dans_perimetre[0]
	return academic_year or unit.academic_year, filiere, niveau


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
