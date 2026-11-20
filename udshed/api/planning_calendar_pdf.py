import frappe
from frappe import _
from datetime import date, datetime, timedelta

import udshed.api.planning_calendar as planning_calendar
import udshed.api.planning_permission as planning_permission
import udshed.api.planning_period as planning_period
import udshed.api.school_setting as school_setting
import udshed.utils.file_utils as file_utils
from frappe.utils import add_days
from frappe.utils.pdf import get_pdf


def _date_debut(valeur):
	if isinstance(valeur, datetime):
		return valeur.date()
	if isinstance(valeur, date):
		return valeur
	if isinstance(valeur, str) and "T" in valeur:
		return datetime.fromisoformat(valeur).date()
	return datetime.strptime(str(valeur).strip(), "%Y-%m-%d").date()


def _hhmm(valeur):
	from datetime import time as _time, timedelta as _td

	if valeur is None or valeur == "":
		return ""
	if isinstance(valeur, _td):
		total = int(valeur.total_seconds())
		return "{0:02d}:{1:02d}".format(total // 3600, (total % 3600) // 60)
	if isinstance(valeur, _time):
		return "{0:02d}:{1:02d}".format(valeur.hour, valeur.minute)
	if isinstance(valeur, datetime):
		return "{0:02d}:{1:02d}".format(valeur.hour, valeur.minute)
	texte = str(valeur).strip()
	if "T" in texte:
		texte = texte.split("T", 1)[1]
	parties = texte.split(":")
	if len(parties) >= 2 and parties[0].strip().isdigit() and parties[1].strip().isdigit():
		return "{0:02d}:{1:02d}".format(int(parties[0]), int(parties[1]))
	return texte


def _pdf_weasyprint(html):
	from weasyprint import HTML

	return HTML(string=html, base_url=frappe.utils.get_url()).write_pdf()


def _pdf(html):
	try:
		return get_pdf(
			html,
			{
				"orientation": "Landscape",
				"page-size": "A4",
				"margin-top": "10mm",
				"margin-bottom": "10mm",
				"margin-left": "12mm",
				"margin-right": "12mm",
			},
		)
	except Exception:
		frappe.logger().info("planning_calendar_pdf: repli WeasyPrint")
		return _pdf_weasyprint(html)


def get_valid_period(periods, items):
	used = {item.get("period") for item in items}
	return [period for period in periods if period.get("name") in used]


@frappe.whitelist(allow_guest=False)
def generate_planning_pdf(filters):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	if not isinstance(filters, dict):
		frappe.throw(_("Filtres invalides."), frappe.ValidationError)
	academic_year = filters.get("academic_year")
	week_start = filters.get("week_start")
	if not academic_year or not week_start:
		frappe.throw(_("Année académique et semaine sont requises."), frappe.ValidationError)

	filiere_filter = filters.get("filiere") or None
	niveau_filter = filters.get("niveau") or None
	teacher_filter = filters.get("teacher") or None
	faculty_filter = filters.get("faculty") or None
	if filiere_filter and not faculty_filter:
		faculty_filter = frappe.db.get_value("Field of study", filiere_filter, "faculte")

	planning_permission.assert_can_view_planning(
		academic_year, faculty_filter, filiere_filter, niveau_filter, teacher_filter
	)

	items = planning_calendar.get_week_planning(
		academic_year=academic_year,
		week_start=week_start,
		filiere=filiere_filter,
		niveau=niveau_filter,
		teacher=teacher_filter,
		faculty=faculty_filter,
	)

	filiere = frappe.db.get_value(
		"Field of study", filiere_filter, ["name", "name_of_field", "field_of_study_code", "faculte"], as_dict=True
	) if filiere_filter else None
	niveau_filiere = frappe.db.get_value(
		"Field of study Level", niveau_filter, ["name", "level", "coordonateur", "calendrier"], as_dict=True
	) if niveau_filter else None
	teacher = frappe.db.get_value(
		"Teacher", teacher_filter, ["name", "grade", "first_name", "last_name", "email"], as_dict=True
	) if teacher_filter else None

	if niveau_filiere:
		try:
			periodes_niveau = planning_period.get_period(niveau_filiere.name, week_start, academic_year)
		except Exception:
			periodes_niveau = []
		period = get_valid_period(periodes_niveau, items) or periodes_niveau or get_valid_period(
			planning_period.get_all_periods(), items
		)
	else:
		period = get_valid_period(planning_period.get_all_periods(), items)
	if not period:
		try:
			period = planning_period.get_default_period()
		except Exception:
			period = []

	css_by_type = {
		"Cours Magistral (CM)": "cm",
		"Cours": "cm",
		"Traveaux Pratiques (TP)": "tp",
		"Travaux Pratique (TP)": "tp",
		"Traveaux Dirigés (TD)": "td",
		"Travaux Dirigés (TD)": "td",
		"Controlle Continue (CC)": "cc",
		"Examen de session normal": "exam",
		"Examen de rattrapage": "exam",
	}
	days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
	grid = {day: {entry.get("period"): [] for entry in period} for day in days}
	for item in items:
		day = item.get("date")
		if isinstance(day, str):
			day = datetime.fromisoformat(day)
		day_name = day.strftime("%A") if hasattr(day, "strftime") else str(day)
		if day_name not in grid:
			continue
		grid[day_name].setdefault(item.get("period"), []).append({
			"subject": item.get("intitule_label") or item.get("course_label") or item.get("course"),
			"course_label": item.get("course_label"),
			"type": item.get("type"),
			"batiment": item.get("batiment"),
			"salle": item.get("salle"),
			"teachers": item.get("teachers") or [],
			"mode": item.get("mode"),
			"filiere": item.get("filiere"),
			"niveau_label": item.get("niveau_label"),
			"css": css_by_type.get(item.get("type"), "cm"),
			"progress_label": item.get("progress_label"),
			"progress_done_hours": item.get("progress_done_hours"),
			"progress_total_hours": item.get("progress_total_hours"),
			"progress_state": item.get("progress_state"),
			"progress_is_last": item.get("progress_is_last"),
			"progress_extra_hours": item.get("progress_extra_hours"),
			"progress_extra_label": item.get("progress_extra_label"),
			"progress_pct": item.get("progress_pct"),
		})

	start = _date_debut(week_start)
	end = add_days(start, 6)
	school_name, school_logo = school_setting.get_school_data()
	data_to_print = {
		"grid": grid,
		"filters": filters,
		"week_start": start.strftime("%d %B %Y"),
		"week_end": end.strftime("%d %B %Y"),
		"school_name": school_name,
		"school_logo": file_utils.load_school_logo(school_logo),
		"app_logo": file_utils.get_app_logo(),
		"generated_on": datetime.now().strftime("%d/%m/%Y à %H:%M"),
		"fuseau_horaire": (period[0].get("fuseau_horaire") if period else "") or "GMT +1",
		"type_planning": planning_calendar.get_planning_type(
			niveau_filiere.name if niveau_filiere else None, week_start, academic_year
		),
		"period": [
			{**entry, "heure_de_debut": _hhmm(entry.get("heure_de_debut")), "heure_de_fin": _hhmm(entry.get("heure_de_fin"))}
			for entry in period
		],
	}
	if teacher:
		data_to_print["teacher"] = " ".join(
			part for part in [teacher.grade or "", teacher.first_name or "", teacher.last_name or ""] if part
		).strip()
	if filiere:
		data_to_print["filiere"] = filiere.name_of_field
	if niveau_filiere:
		data_to_print["coordinator"] = niveau_filiere.coordonateur
		data_to_print["niveau"] = niveau_filiere.level

	html = frappe.render_template("udshed/www/planning_pdf.html", data_to_print)
	pdf = _pdf(html)
	planning_name = "Planning"
	if filiere:
		planning_name += " " + (filiere.field_of_study_code or filiere.name)
	if niveau_filiere:
		planning_name += " " + str(niveau_filiere.level)
	if teacher:
		planning_name += " " + " ".join([teacher.first_name or "", teacher.last_name or ""]).strip()
	planning_name += " du {0} au {1} {2}.pdf".format(
		start.strftime("%d %B"), end.strftime("%d %B"), academic_year
	)
	return pdf, planning_name, items, start, end
