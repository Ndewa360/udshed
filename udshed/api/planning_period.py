from datetime import datetime, date, timedelta
import frappe
from frappe import _

def get_unique_sorted_period(periods):
    set_period = {}
    unique = []
    for d in periods:
        if d["name"] not in set_period:
            set_period[d["name"]]=d["name"]
            data_to_set = {
                "name": d["name"],
                "label": set_period[d["name"]],
                "libelle":d["libelle"],
                "heure_de_debut":d["heure_de_debut"],
                "heure_de_fin":d["heure_de_fin"]
            }
            if "fuseau_horaire" in d:
                data_to_set["fuseau_horaire"] = d["fuseau_horaire"]
            unique.append(data_to_set)
    return sorted(unique,key = lambda x: f"{datetime.strptime(str(x["heure_de_debut"]), "%H:%M:%S").strftime('%H:%M')}-{datetime.strptime(str(x["heure_de_fin"]), "%H:%M:%S").strftime('%H:%M')}")


@frappe.whitelist()
def get_period(field_of_study_level,week_start,academic_year):
    try:
        return _get_period_impl(field_of_study_level,week_start,academic_year)
    except Exception:
        frappe.log_error(" planning_period get_period")
        frappe.throw(_("Erreur lors du chargement des périodes."))


def _date_debut(valeur):
    """Date demandee, qu'elle arrive en chaine, en `date` ou en `datetime`."""
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    if isinstance(valeur, str) and "T" in valeur:
        return datetime.fromisoformat(valeur).date()
    return datetime.strptime(str(valeur).strip(), "%Y-%m-%d").date()


def _periodes_dun_calendrier(calendar_name):
    """Lignes `Planning Period` d'un calendrier + son fuseau horaire.

    Retourne un tuple vide quand le calendrier n'existe pas ou n'a aucune
    periode : un calendrier vide ne doit pas faire echouer le planning, il
    doit pouvoir ceder la place au suivant.
    """
    if not calendar_name or not frappe.db.exists("Calendar Planing", calendar_name):
        return [], None
    calendar = frappe.get_doc("Calendar Planing", calendar_name)
    periodes = frappe.db.get_all(
        "Planning Period",
        filters={"parent": calendar_name},
        fields=["name", "libelle", "heure_de_debut", "heure_de_fin"],
    )
    return periodes, calendar


def _calendriers_candidats(field_of_study_level, session_exam):
    """Calendriers a essayer, du plus pertinent au plus general.

    Les calendriers de session d'examen d'abord, puis le calendrier du
    niveau, puis `Defaut`. Plusieurs calendriers de la meme famille
    (« Master en ligne », « Master en Alternance »…) sont vides sur certains
    sites : sans ce repli, le planning de la semaine echouait.
    """
    vus = set()
    for session in session_exam or []:
        if session.get("calendar"):
            vus.add(session.calendar)
    niveau = frappe.db.get_value("Field of study Level", field_of_study_level, "calendrier")
    for nom in (niveau, "Defaut"):
        if nom:
            vus.add(nom)
    return list(vus)


def _get_period_impl(field_of_study_level,week_start,academic_year):
    session_exam = []
    week_start_date = _date_debut(week_start)
    if academic_year and week_start:
        session_exam = frappe.get_all("Session Examen", filters=[
                ["academic_year", "=", academic_year], 
                ["date_debut", "<=",    week_start_date], 
                ["date_de_fin", ">=", week_start_date],
                ["Session Examen Field of study Level", "niveau", "=", field_of_study_level]
            ],
            fields = ["name", "calendar"],
            distinct = True,
        )

    periods = []
    fuseau = None
    for calendar_name in _calendriers_candidats(field_of_study_level, session_exam):
        periodes, calendar = _periodes_dun_calendrier(calendar_name)
        if periodes:
            # Premier calendrier_NON vide : ses periodes font foi.
            periods = periodes
            fuseau = calendar.fuseau_horaire
            break
        if fuseau is None and calendar is not None:
            fuseau = calendar.fuseau_horaire

    if not periods:
        return []

    return get_unique_sorted_period(
        [
            {
                "name": p.name,
                "libelle": p.libelle,
                "fuseau_horaire": fuseau,
                "heure_de_debut": p.heure_de_debut,
                "heure_de_fin": p.heure_de_fin,
            }
            for p in periods
        ]
    )

@frappe.whitelist()
def get_all_periods():
    try:
        periods = frappe.db.get_all(
            "Planning Period",
            fields=["name", "parent", "libelle", "heure_de_debut", "heure_de_fin"],
        )
        result_periods = []
        calendar_list = {}
        for period in periods:
            # `Planning Period` est une ligne enfant : `name` vaut
            # « 08:00:00-12:00:00-001 », pas le nom du calendrier. C'est
            # `parent` (« Defaut », « Examen », …) qui identifie le
            # `Calendar Planing` : chercher par `name` levait
            # DoesNotExistError et faisait échouer le PDF du planning.
            calendar_name = period.parent
            if calendar_name and calendar_name not in calendar_list:
                if not frappe.db.exists("Calendar Planing", calendar_name):
                    continue
                calendar_list[calendar_name] = frappe.get_doc("Calendar Planing", calendar_name)
            fuseau = calendar_list.get(calendar_name)
            if fuseau is None:
                continue
            result_periods.append(
                {
                    "name": period.name,
                    "libelle": period.libelle,
                    "fuseau_horaire": fuseau.fuseau_horaire,
                    "heure_de_debut": period.heure_de_debut,
                    "heure_de_fin": period.heure_de_fin,
                }
            )
        return get_unique_sorted_period(result_periods)
    except Exception:
        frappe.log_error(" planning_period get_all_periods")
        frappe.throw(_("Erreur lors du chargement de toutes les périodes."))


@frappe.whitelist()
def get_default_period():
    try:
        periods = []
        fuseau = None
        # Repli identique a `_calendriers_candidats` : si « Defaut » a été
        # supprimé ou est vide, le planning ne doit pas planter, il cède la
        # place au calendrier suivant.
        for calendar_name in ("Defaut", "Examen", "Master en ligne", "Master en Alternance"):
            periodes, calendar = _periodes_dun_calendrier(calendar_name)
            if periodes:
                periods = periodes
                fuseau = calendar.fuseau_horaire
                break
            if fuseau is None and calendar is not None:
                fuseau = calendar.fuseau_horaire

        if not periods:
            return []

        return get_unique_sorted_period(
            [
                {
                    "name": p.name,
                    "libelle": p.libelle,
                    "fuseau_horaire": fuseau,
                    "heure_de_debut": p.heure_de_debut,
                    "heure_de_fin": p.heure_de_fin,
                }
                for p in periods
            ]
        )
    except Exception:
        frappe.log_error(" planning_period get_default_period")
        frappe.throw(_("Erreur lors du chargement de la période par défaut."))
