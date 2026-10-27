import frappe
import os
from datetime import datetime, timedelta
from frappe import _
import udshed.api.school_setting as school_setting
import udshed.api.planning_period as planning_period
import udshed.api.planning_calendar as planning_calendar
import udshed.utils.file_utils as file_utils
from frappe.utils import getdate, add_days
from frappe.utils.pdf import get_pdf
from frappe.utils import get_url


def _date_debut(valeur):
    """Date du lundi de la semaine demandee, quel que soit le type recu.

    Le filtre `week_start` arrive normalement en chaîne « AAAA-MM-JJ » depuis
    l'écran, mais peut aussi être un `date`/`datetime` (export, appel
    programmatique). `strptime` sur un `datetime` levait « unconverted data
    remains: T00:00:00 ».
    """
    from datetime import date as _date, datetime as _dt

    if isinstance(valeur, _dt):
        return valeur.date()
    if isinstance(valeur, _date):
        return valeur
    if isinstance(valeur, str) and "T" in valeur:
        return _dt.fromisoformat(valeur).date()
    return datetime.strptime(str(valeur).strip(), "%Y-%m-%d")


def _hhmm(valeur):
    """Formate une heure de créneau en « HH:MM », quel que soit son stockage.

    `Planning Period.heure_de_debut` / `heure_de_fin` sont des champs Time :
    Frappe les renvoie soit en `datetime.time`, soit en `datetime.timedelta`
    dont `str()` vaut « 8:00:00 » (non.Zero-padé). Un simple
    `strptime(..., "%H:%M:%S")` echouait donc sur « unconverted data
    remains: T00:00:00 ».
    """
    from datetime import datetime as _dt, time as _time, timedelta as _td

    if valeur is None or valeur == "":
        return ""
    if isinstance(valeur, _td):
        total = int(valeur.total_seconds())
        return "{:02d}:{:02d}".format(total // 3600, (total % 3600) // 60)
    if isinstance(valeur, _time):
        return "{:02d}:{:02d}".format(valeur.hour, valeur.minute)
    if isinstance(valeur, _dt):
        return "{:02d}:{:02d}".format(valeur.hour, valeur.minute)

    texte = str(valeur).strip()
    # « 8:00:00 », « 08:00:00 », « 8:00 », éventuellement suffixe « T00:00:00 »
    if "T" in texte:
        texte = texte.split("T", 1)[1]
    parties = texte.split(":")
    if len(parties) >= 2 and parties[0].strip().isdigit() and parties[1].strip().isdigit():
        return "{:02d}:{:02d}".format(int(parties[0]), int(parties[1]))
    return texte


def _pdf_weasyprint(html):
    """Rendu PDF via WeasyPrint (moteur CSS, deja installe dans l'env).

    Le gabarit `planning_pdf.html` porte sa propre regle `@page`
    (`size: A4 landscape`, `margin: 10mm 12mm`) : elle est reprise a
    l'identique de la section `styles` de `get_pdf`.
    """
    from weasyprint import HTML

    return HTML(string=html, base_url=frappe.utils.get_url()).write_pdf()


def _pdf(html):
    """Produit le PDF avec WeasyPrint, ou repli sur `get_pdf` (wkhtmltopdf).

    WeasyPrint est pure Python et deja utilise par les PV, releves et
    fiches : il rend donc le planning independant de l'installation systeme
    de `wkhtmltopdf`, absent de la plupart des postes. On tente d'abord
    `get_pdf` pour conserver le rendu historique quand le binaire est
    present, puis on bascule sur WeasyPrint si `wkhtmltopdf` manque.
    """
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
        frappe.logger().info(
            "planning_calendar_pdf: wkhtmltopdf indisponible, repli WeasyPrint"
        )
        return _pdf_weasyprint(html)

def get_valid_period(periods,items):
    periods_to_valid = {}
    for period in periods:
        periods_to_valid[period["name"]] = False
    for item in items:
         period= item["period"]
         if period not in periods_to_valid:
             continue
         periods_to_valid[period] = True
    return [p for p in periods if periods_to_valid[p["name"]]]


@frappe.whitelist(allow_guest=False)
def generate_planning_pdf(filters):
    app_logo = file_utils.get_app_logo()

    filiere = None
    niveau_filiere = None
    teacher = None

    if filters["filiere"]:
        filiere_filter = filters["filiere"]
        filiere = frappe.get_doc("Field of study", filiere_filter)
    else:
        filiere_filter = None

    if "niveau" in filters and  filters["niveau"]:
        niveau_filter = filters["niveau"]
        niveau_filiere = frappe.get_doc("Field of study Level",filters["niveau"])
    else:
        niveau_filter = None

    if filters["teacher"]:
        teacher = frappe.get_doc("Teacher", {"name": filters["teacher"]})
        teacher_filter = filters["teacher"]
    else:
        teacher_filter = None

    school_name, school_logo = school_setting.get_school_data()
    school_logo = file_utils.load_school_logo(school_logo)
    
    items = frappe.call(
        "udshed.api.planning_calendar.get_week_planning",
        academic_year=filters["academic_year"],
        filiere=filiere_filter,
        niveau=niveau_filter,
        teacher=teacher_filter,
        week_start=filters["week_start"],
    )

    # Chaine de resolution des periodes : on garde l'ordre de preference
    # (periodes du niveau -> periodes reellement utilisees -> toutes -> Defaut)
    # et on ne s'arrete que sur une liste non vide. Un calendrier vide ne doit
    # pas empecher l'edition du planning.
    if niveau_filiere:
        try:
            periodes_niveau = planning_period.get_period(
                niveau_filiere.name, filters["week_start"], filters["academic_year"]
            )
        except Exception:
            periodes_niveau = []
        if periodes_niveau:
            period = get_valid_period(periodes_niveau, items) or periodes_niveau
        else:
            period = get_valid_period(planning_period.get_all_periods(), items)
    else:
        period = get_valid_period(planning_period.get_all_periods(), items)

    if not period:
        try:
            period = planning_period.get_default_period()
        except Exception:
            period = []

    if not period:
        # Aucun créneau nulle part : on edition quand même le planning
        # (entête, logo, titre), sans grille horaire.
        frappe.msgprint(
            _("Aucun créneau horaire n'est défini pour cette classe : le planning est édité sans grille.")
        )
        period = []

    grid = {
        "Monday": {},
        "Tuesday":{},
        "Wednesday":{},
        "Thursday":{},
        "Friday":{},
        "Saturday":{}
    }

    for it in items:
        day = it["date"].strftime("%A")
        half = it["period"]
        css = {
            "Cours":"cm",
            "Traveaux Pratiques (TP)":"tp",
            "Traveaux Dirigés (TD)":"td",
            "Controlle Continue (CC)":"cc",
            "Examen de session normal":"exam",
            "Examen de rattrapage":"exam"
        }.get(it["type"],"cm")

        grid[day][half] = {
            "subject": it["course"],
            "cours_label": it["cours_label"],
            "type": it["type"],
            "batiment": it["batiment"],
            "salle": it["salle"],
            "teachers": [it["enseignant"]],
            "mode":it["mode"],
            "filiere":it["filiere"],
            "niveau_label":it["niveau_label"],
            "css": css
        }

    start = _date_debut(filters["week_start"])
    end = start + timedelta(days=6)
    data_to_print = {
            "grid":grid,
            "filters":filters,
            "week_start": start.strftime("%d %B %Y"),
            "week_end": end.strftime("%d %B %Y"),
            "school_name": school_name,
            "school_logo": school_logo,
            "app_logo": app_logo,
            "generated_on": datetime.now().strftime("%d/%m/%Y à %H:%M"),
            "type_planning": planning_calendar.get_planning_type(
                niveau_filiere.name if niveau_filiere else None,
                filters["week_start"],
                filters["academic_year"],
            ),
            "period":[
                {
                    **p,
                    "heure_de_debut": _hhmm(p["heure_de_debut"]),
                    "heure_de_fin": _hhmm(p["heure_de_fin"]),
                } for p in period
            ]
        }
    if teacher:
        data_to_print["teacher"] = f"{teacher.grade}. {teacher.first_name} {teacher.last_name}"
    if filiere:
        data_to_print["filiere"]=filiere.name_of_field
        
    if  niveau_filiere:
        data_to_print["coordinator"] =  niveau_filiere.coordonateur
        data_to_print["niveau"]=niveau_filiere.level
    html = frappe.render_template(
        "udshed/www/planning_pdf.html",
        data_to_print
    )
    pdf = _pdf(html)
    planning_name = "Planning"
    if filiere:
        planning_name += f" {filiere.field_of_study_code}"
    if niveau_filiere:
        planning_name += f" {niveau_filiere.level}"
    if teacher_filter:
        planning_name += f" {teacher.first_name} {teacher.last_name}"
    
    planning_name += f" du {start.strftime('%d %B')}  au {end.strftime('%d %B')} {filters['academic_year']}.pdf"
    return pdf,planning_name,items,start,end
