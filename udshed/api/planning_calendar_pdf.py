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
				"margin-top": "8mm",
				"margin-bottom": "8mm",
				"margin-left": "8mm",
				"margin-right": "8mm",
			},
		)
	except Exception:
		frappe.logger().info("planning_calendar_pdf: repli WeasyPrint")
		return _pdf_weasyprint(html)


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

	scope = planning_permission.assert_can_view_planning(
		academic_year,
		filters.get("faculty"),
		filters.get("filiere"),
		filters.get("niveau"),
		filters.get("teacher"),
	)
	resolved = scope["filters"]
	filiere_filter = resolved["filiere"]
	niveau_filter = resolved["niveau"]
	teacher_filter = resolved["teacher"]

	items = planning_calendar.get_week_planning(
		academic_year=academic_year,
		week_start=week_start,
		filiere=filiere_filter,
		niveau=niveau_filter,
		teacher=teacher_filter,
		faculty=resolved["faculty"],
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

	period = []
	if niveau_filiere:
		try:
			period = planning_period.get_period(niveau_filiere.name, week_start, academic_year) or []
		except Exception:
			period = []
	if not period:
		try:
			period = planning_period.get_default_period() or []
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
	# Planning d'un enseignant : ses séances viennent de classes aux calendriers
	# différents. Un créneau absent du calendrier par défaut faisait disparaître
	# la séance du PDF : on ajoute les créneaux réellement utilisés.
	period = _completer_creneaux(period, items)
	days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
	grid = {day: {entry.get("name"): [] for entry in period} for day in days}
	for item in items:
		day = item.get("date")
		if isinstance(day, str):
			day = datetime.fromisoformat(day)
		# Indice du jour, indépendant de la locale du serveur (%A donnait
		# « lundi » sur un serveur en français et la séance était ignorée).
		day_name = days[day.weekday()] if hasattr(day, "weekday") and day.weekday() < 6 else None
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
			"classes": item.get("classes") or [],
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
	end = add_days(start, 5)
	max_items_per_cell = max(
		(len(cell_items) for day in grid.values() for cell_items in day.values()),
		default=0,
	)
	density = ""
	if len(period) > 6 or max_items_per_cell > 1:
		density = "dense"
	if len(period) > 8 or max_items_per_cell > 2:
		density = "dense compact"
	school_name, school_logo = school_setting.get_school_data()
	data_to_print = {
		"grid": grid,
		"density": density,
		"filters": {**filters, **resolved},
		"week_start": date_fr(start),
		"week_end": date_fr(end),
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
		date_fr(start, annee=False), date_fr(end, annee=False), academic_year
	)
	return pdf, planning_name, items, start, end


MOIS_FR = (
	"janvier", "février", "mars", "avril", "mai", "juin",
	"juillet", "août", "septembre", "octobre", "novembre", "décembre",
)
JOURS_FR = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")


def date_fr(valeur, annee=True, jour=False):
	"""« 24 novembre 2026 » (ou « Mardi 24 novembre »), sans dépendre de la locale."""
	d = _date_debut(valeur)
	texte = "{0} {1}".format(d.day, MOIS_FR[d.month - 1])
	if annee:
		texte += " {0}".format(d.year)
	if jour:
		texte = "{0} {1}".format(JOURS_FR[d.weekday()], texte)
	return texte


def _completer_creneaux(period, items):
	"""Ajoute aux créneaux affichés ceux utilisés par les séances et absents,
	puis trie par heure de début."""
	connus = {p.get("name") for p in period}
	manquants = sorted({i.get("period") for i in items if i.get("period") and i.get("period") not in connus})
	if not manquants:
		return period
	ajout = frappe.get_all(
		"Planning Period",
		filters={"name": ["in", manquants]},
		fields=["name", "libelle", "heure_de_debut", "heure_de_fin"],
	)
	tous = list(period) + [{**p, "label": p.name} for p in ajout]

	def cle(p):
		return (_hhmm(p.get("heure_de_debut")) or "99:99", _hhmm(p.get("heure_de_fin")) or "99:99")

	return sorted(tous, key=cle)
