import frappe
from frappe import _
from frappe.query_builder import DocType
from datetime import date, datetime, time, timedelta

import udshed.api.course as course
import udshed.api.planning_permission as planning_permission

PROGRESS_TYPES = {
	"Cours Magistral (CM)",
	"Traveaux Pratiques (TP)",
	"Traveaux Dirigés (TD)",
	"Travaux Pratique (TP)",
	"Travaux Dirigés (TD)",
}


def parse_date(value):
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	texte = str(value).strip()
	if "T" in texte:
		texte = texte.split("T", 1)[0]
	elif " " in texte:
		texte = texte.split(" ", 1)[0]
	return datetime.strptime(texte[:10], "%Y-%m-%d").date()


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


def _minutes(value):
	if isinstance(value, timedelta):
		return int(value.total_seconds() // 60)
	if isinstance(value, time):
		return value.hour * 60 + value.minute
	texte = str(value or "").strip()
	if "T" in texte:
		texte = texte.split("T", 1)[1]
	parties = texte.split(":")
	if len(parties) >= 2 and parties[0].strip().isdigit() and parties[1].strip().isdigit():
		return int(parties[0]) * 60 + int(parties[1])
	return 0


def _period_hours(period, cache):
	if not period:
		return 0.0
	if period not in cache:
		row = frappe.db.get_value(
			"Planning Period", period, ["heure_de_debut", "heure_de_fin"], as_dict=True
		)
		cache[period] = max(0, _minutes(row.heure_de_fin) - _minutes(row.heure_de_debut)) / 60 if row else 0.0
	return cache[period]


def _period_start(period, cache):
	if not period:
		return 0
	if period not in cache:
		row = frappe.db.get_value("Planning Period", period, "heure_de_debut")
		cache[period] = _minutes(row)
	return cache[period]


def _format_hours(value):
	if not value:
		return "0"
	if float(value).is_integer():
		return str(int(value))
	return ("{0:.2f}".format(float(value)).rstrip("0").rstrip(".")).replace(".", ",")


def _attach_progress(rows):
	"""Avancement horaire de chaque séance (heures faites / volume prévu).

	Les cours liés sont un seul enseignement : les heures se cumulent sur tout
	le groupe ; le volume de référence est celui du cours affiché (celui de la
	grille consultée).
	"""
	from udshed.utils.planning_conflits import groupe_du_cours

	if not rows:
		return
	affiches = sorted({str(row.get("cours_affiche") or row.cours) for row in rows if row.cours})
	years = sorted({str(row.academic_year) for row in rows if row.academic_year})
	if not affiches or not years:
		return

	groupe_de = {}
	for nom in {str(row.cours) for row in rows if row.cours} | set(affiches):
		membres = groupe_du_cours(nom)
		cle = min(membres)
		for m in membres:
			groupe_de[m] = cle
	unites = sorted(groupe_de)

	totals = {}
	for unit in frappe.get_all(
		"Teaching Unit",
		filters={"name": ["in", affiches]},
		fields=["name", "nombre_dheure_cm", "nombre_dheure_td", "nombre_dheure_tp"],
	):
		totals[unit.name] = sum(
			frappe.utils.flt(unit.get(field) or 0)
			for field in ("nombre_dheure_cm", "nombre_dheure_td", "nombre_dheure_tp")
		)

	all_items = frappe.get_all(
		"Planning Item",
		filters={
			"cours": ["in", unites],
			"academic_year": ["in", years],
			"type": ["in", sorted(PROGRESS_TYPES)],
			"status": ["!=", "Annulée"],
		},
		fields=["name", "cours", "academic_year", "date", "period", "creation"],
	)
	duration_cache = {}
	start_cache = {}
	all_items.sort(
		key=lambda item: (
			parse_date(item.date) if item.date else date.min,
			_period_start(item.period, start_cache),
			item.creation or "",
		)
	)

	cumulative = {}
	heures_par_item = {}
	for item in all_items:
		key = (groupe_de.get(item.cours, item.cours), item.academic_year)
		previous = cumulative.get(key, 0.0)
		current = previous + _period_hours(item.period, duration_cache)
		cumulative[key] = current
		heures_par_item[item.name] = (previous, current)

	for row in rows:
		if row.name not in heures_par_item:
			continue
		previous, current = heures_par_item[row.name]
		total = totals.get(str(row.get("cours_affiche") or row.cours), 0.0)
		state = "normal"
		is_last = False
		extra = 0.0
		if total:
			if current > total:
				state = "depassement"
				extra = current - total
			elif previous < total <= current:
				state = "termine"
				is_last = True
			elif current >= total:
				state = "termine"
		row.update({
			"progress_done_hours": current,
			"progress_total_hours": total,
			"progress_label": (
				"{0}/{1} h".format(_format_hours(current), _format_hours(total))
				if total
				else "{0} h/—".format(_format_hours(current))
			),
			"progress_state": state,
			"progress_is_last": is_last,
			"progress_extra_hours": extra,
			"progress_extra_label": _format_hours(extra),
			"progress_pct": min(100.0, round(current / total * 100, 1)) if total else 0.0,
		})


@frappe.whitelist()
def get_week_planning(academic_year, week_start, filiere=None, niveau=None, teacher=None, faculty=None):
	try:
		scope = planning_permission.assert_can_view_planning(academic_year, faculty, filiere, niveau, teacher)
		filters = scope["filters"]
		academic_year = filters["academic_year"]
		faculty = filters["faculty"]
		filiere = filters["filiere"]
		niveau = filters["niveau"]
		teacher = filters["teacher"]
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
			.left_join(Course)
			.on(TeachingUnit.course == Course.name)
			.left_join(CourseNiveauFiliere)
			.on(CourseNiveauFiliere.parent == TeachingUnit.name)
			.left_join(FieldOfStudy)
			.on(FieldOfStudy.name == CourseNiveauFiliere.filiere)
			.left_join(CourseEnseignant)
			.on(CourseEnseignant.parent == TeachingUnit.name)
			.select(
				TeachingUnit.course,
				Course.intitule.as_("course_label"),
				TeachingUnit.intitule_cours.as_("intitule_label"),
				PlanningItem.salle,
				PlanningItem.batiment,
				PlanningItem.name,
				PlanningItem.type,
				PlanningItem.cours,
				PlanningItem.date,
				PlanningItem.period,
				PlanningItem.mode,
				PlanningItem.status,
				PlanningItem.academic_year,
				CourseNiveauFiliere.niveau,
				CourseNiveauFiliere.filiere,
				FieldOfStudy.faculte.as_("faculty"),
				CourseEnseignant.enseignant,
			)
			.where(
				(PlanningItem.academic_year == academic_year)
				& (PlanningItem.date >= date_week_start)
				& (PlanningItem.date < frappe.utils.add_days(date_week_start, 6))
			)
			.distinct()
		)
		condition_classe = None
		if faculty:
			condition_classe = FieldOfStudy.faculte == faculty
		if filiere:
			c = CourseNiveauFiliere.filiere == filiere
			condition_classe = c if condition_classe is None else condition_classe & c
		if niveau:
			c = CourseNiveauFiliere.niveau == niveau
			condition_classe = c if condition_classe is None else condition_classe & c
		if condition_classe is not None:
			# Séances des cours liés (même cours, autre intitulé, autre grille) :
			# elles occupent aussi cette classe et doivent y apparaître.
			lies = _cours_lies_a_la_classe(academic_year, filiere, niveau) if (filiere and niveau) else []
			query = query.where(condition_classe | PlanningItem.cours.isin(lies) if lies else condition_classe)
		if teacher:
			# Toutes les séances de l'enseignant, dans toutes ses classes, y
			# compris celles d'un cours lié (cours commun planifié via une
			# autre grille) : c'est le même enseignement, comme pour les conflits.
			cours_enseignant = _cours_de_lenseignant(academic_year, teacher)
			if not cours_enseignant:
				return []
			query = query.where(PlanningItem.cours.isin(cours_enseignant))

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
		classes_cache = {}
		for doc in seen.values():
			doc["teacher_ids"] = [t for t in (doc._teachers or []) if t]
			doc["teachers"] = [_format_teacher(t, teacher_cache) for t in doc["teacher_ids"]]
			doc["enseignant"] = doc["teachers"][0] if doc["teachers"] else ""
			del doc["_teachers"]
			doc["niveau_label"] = _level_label(doc.niveau)
			doc["salle_name"] = doc.salle or ""
			doc["batiment_name"] = doc.batiment or ""
			doc["salle"] = _room_code(doc.salle, room_cache)
			doc["batiment"] = _batiment_code(doc.batiment, room_cache)
			doc["cours_affiche"] = doc.cours
			# Toutes les classes qui suivent la séance (tronc commun, cours
			# liés) : une ligne par séance ne porte qu'UNE classe dans `niveau`.
			doc["classes"] = _classes_label(doc.cours, classes_cache)
		rows = list(seen.values())
		# Statut fixé à la main (pointage) : affiché et repris dans la fenêtre de modification.
		if rows and frappe.db.has_column("Planning Item", "pointage_manuel"):
			manuels = set(frappe.get_all(
				"Planning Item",
				filters={"name": ["in", [r.name for r in rows]], "pointage_manuel": 1},
				pluck="name",
			))
			for row in rows:
				row["pointage_manuel"] = 1 if row.name in manuels else 0
		if filiere and niveau:
			_afficher_selon_la_grille(rows, academic_year, filiere, niveau)
		_attach_progress(rows)
		return rows
	except (frappe.ValidationError, frappe.PermissionError):
		raise
	except Exception:
		_log()
		_throw("Erreur lors du chargement du planning.")


def _cours_de_lenseignant(academic_year, teacher):
	"""Cours (Teaching Unit) de l'année où l'enseignant intervient, élargis aux
	cours qui leur sont liés (groupe de cours commun)."""
	from udshed.utils.planning_conflits import groupe_du_cours

	propres = frappe.db.sql_list(
		"""
		SELECT DISTINCT tu.name FROM `tabTeaching Unit` tu
		INNER JOIN `tabCourse Teacher Item` ct ON ct.parent = tu.name AND ct.parenttype = 'Teaching Unit'
		WHERE tu.academic_year = %s AND ct.enseignant = %s
		""",
		(academic_year, teacher),
	)
	cours = set()
	for name in propres:
		cours |= groupe_du_cours(name)
	return sorted(cours)


def _classes_label(teaching_unit, cache):
	"""Libellés « Filière Niveau » de toutes les classes d'un cours (cours liés compris)."""
	if teaching_unit not in cache:
		from udshed.utils.planning_conflits import classes_du_cours

		cache[teaching_unit] = sorted(
			"{0} {1}".format(filiere, _level_label(niveau) or niveau).strip()
			for filiere, niveau in classes_du_cours(teaching_unit)
		)
	return list(cache[teaching_unit])


def _afficher_selon_la_grille(rows, academic_year, filiere, niveau):
	"""Séance d'un cours lié planifiée via une autre grille : on l'affiche avec
	le cours de LA grille consultée (code, intitulé), pas celui de l'autre classe.

	`cours` reste le cours réellement planifié (modification / suppression) ;
	`cours_affiche` est le cours de la classe consultée.
	"""
	from udshed.utils.planning_conflits import groupe_du_cours

	propres = set(
		frappe.db.sql_list(
			"""
			SELECT DISTINCT tu.name FROM `tabTeaching Unit` tu
			INNER JOIN `tabCourse Field of study level item` l ON l.parent = tu.name AND l.parenttype = 'Teaching Unit'
			WHERE tu.academic_year = %s AND l.filiere = %s AND l.niveau = %s
			""",
			(academic_year, filiere, niveau),
		)
	)
	label = _level_label(niveau)
	for row in rows:
		if row.cours in propres:
			continue
		equivalents = sorted(groupe_du_cours(row.cours) & propres)
		if not equivalents:
			continue
		tu = frappe.db.get_value("Teaching Unit", equivalents[0], ["name", "course", "intitule_cours"], as_dict=True)
		row["cours_affiche"] = tu.name
		row["cours_lie"] = 1
		row["cours_planifie_label"] = row.get("intitule_label") or row.cours
		row["course"] = tu.course
		row["intitule_label"] = tu.intitule_cours or tu.name
		row["course_label"] = frappe.db.get_value("Course", tu.course, "intitule") or tu.intitule_cours
		row["filiere"] = filiere
		row["niveau"] = niveau
		row["niveau_label"] = label


def _cours_lies_a_la_classe(academic_year, filiere, niveau):
	"""Cours d'autres grilles liés (groupe de cours commun) à un cours de la classe."""
	if not frappe.get_meta("Teaching Unit").has_field("groupe_cours_commun"):
		return []
	groupes = frappe.db.sql_list(
		"""
		SELECT DISTINCT tu.groupe_cours_commun
		FROM `tabTeaching Unit` tu
		INNER JOIN `tabCourse Field of study level item` l ON l.parent = tu.name AND l.parenttype = 'Teaching Unit'
		WHERE tu.academic_year = %s AND l.filiere = %s AND l.niveau = %s
		  AND IFNULL(tu.groupe_cours_commun, '') != ''
		""",
		(academic_year, filiere, niveau),
	)
	if not groupes:
		return []
	return frappe.get_all("Teaching Unit", filters={"groupe_cours_commun": ["in", groupes]}, pluck="name")


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


def _verifier_droit_planifier(academic_year, teaching_unit, filiere=None, niveau=None):
	"""Contrôle d'accès pour la classe effectivement planifiée (tronc commun compris)."""
	faculty = frappe.db.get_value("Field of study", filiere, "faculte") if filiere else None
	return planning_permission.assert_can_plan(academic_year, faculty, filiere, niveau, teaching_unit)


@frappe.whitelist()
def create_planning(academic_year, cours, course_type, day_of_week, half_day, batiment=None, salle=None, mode="En présentiel", filiere=None, niveau=None):
	"""Crée une séance. `filiere` / `niveau` : classe affichée dans la page (celle
	que l'utilisateur planifie) ; les conflits sont contrôlés par Planning Item."""
	try:
		period = _resolve_period(half_day)
		day_date = parse_date(day_of_week)
		teaching_unit = course.get_single_teaching_unit(cours, academic_year)
		unit_info = _unit_info(teaching_unit.name)
		scope = _verifier_droit_planifier(academic_year, teaching_unit.name, filiere, niveau)
		if not unit_info["teachers"]:
			_throw("Le cours « {0} » n'a pas d'enseignant assigné.".format(unit_info["intitule"]))
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
def update_planning(planning_item_name, academic_year, cours, course_type, day_of_week, half_day, batiment=None, salle=None, mode="En présentiel", filiere=None, niveau=None, statut=None):
	try:
		planning_item = frappe.get_doc("Planning Item", planning_item_name)
		period = _resolve_period(half_day)
		day_date = parse_date(day_of_week)
		teaching_unit = course.get_single_teaching_unit(cours, academic_year)
		unit_info = _unit_info(teaching_unit.name)
		# Droit sur la séance existante ET sur le cours de remplacement.
		_verifier_droit_planifier(planning_item.academic_year, planning_item.cours, filiere, niveau)
		scope = _verifier_droit_planifier(academic_year, teaching_unit.name, filiere, niveau)
		if not unit_info["teachers"]:
			_throw("Le cours « {0} » n'a pas d'enseignant assigné.".format(unit_info["intitule"]))
		planning_item.cours = teaching_unit.name
		planning_item.type = course_type
		planning_item.date = day_date
		planning_item.period = period
		planning_item.academic_year = academic_year
		planning_item.mode = mode
		if statut:
			from udshed.utils import pointage

			if statut == pointage.STATUT_AUTO:
				# « Planifiée » : la séance redevient gérée par le pointage du dimanche.
				planning_item.flags.pointage_automatique = True
				planning_item.pointage_manuel = 0
				planning_item.status = pointage.statut_automatique(day_date)
			elif statut in pointage.STATUTS:
				if statut == "Fait" and day_date > frappe.utils.getdate():
					_throw("Une séance future ne peut pas être pointée « Fait ».")
				# Choix explicite (même « Non fait » déjà en place) : fixé à la main.
				planning_item.status = statut
				planning_item.pointage_manuel = 1
			else:
				_throw("Statut de séance invalide : {0}".format(statut))
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
def delete_planning(planning_name, filiere=None, niveau=None):
	try:
		planning = frappe.get_doc("Planning Item", planning_name)
		scope = _verifier_droit_planifier(planning.academic_year, planning.cours, filiere, niveau)
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
		planning_permission.assert_can_view_planning(
			academic_year, faculty, filiere, field_of_study_level or None, require_filters=False
		)
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
