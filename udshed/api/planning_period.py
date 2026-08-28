from datetime import datetime, timedelta
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


def _get_period_impl(field_of_study_level,week_start,academic_year):
    session_exam = []
    print("Field of study level:", field_of_study_level)
    week_start_date = datetime.strptime(week_start, "%Y-%m-%d")
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

    if len(session_exam) > 0:
        for session in session_exam:  
            session_f = frappe.get_doc("Session Examen", session.name)
            print("Session:", session_f, session_f.classes_concernees)              
            calendar_name = session.calendar
            calendar = frappe.get_doc("Calendar Planing",{"name":calendar_name})
            periods.extend(frappe.db.get_all('Planning Period', filters={"parent":calendar_name},fields=["name","libelle","heure_de_debut","heure_de_fin"]))
        # 
    else:
        calendar_name = frappe.get_doc("Field of study Level",field_of_study_level).calendrier
        calendar = frappe.get_doc("Calendar Planing",{"name":calendar_name})
        periods = frappe.db.get_all('Planning Period', filters={"parent":calendar_name},fields=["name","libelle","heure_de_debut","heure_de_fin"])
    
    return get_unique_sorted_period([{"name":p.name,"libelle": p.libelle,"fuseau_horaire":calendar.fuseau_horaire,"heure_de_debut":p.heure_de_debut,"heure_de_fin":p.heure_de_fin} for p in periods])

@frappe.whitelist()
def get_all_periods():
    try:
        periods = frappe.db.get_all('Planning Period',fields=["name","libelle","heure_de_debut","heure_de_fin"])
        result_periods = []
        calendar_list = {}
        for period in periods:
            if period.name not in calendar_list:
                calendar_list[period.name] = frappe.get_doc("Calendar Planing", period.name)
            result_periods.append({"name":period.name, "libelle": period.libelle, "fuseau_horaire":calendar_list[period.name].fuseau_horaire,"heure_de_debut":period.heure_de_debut,"heure_de_fin":period.heure_de_fin})
        return get_unique_sorted_period(result_periods)
    except Exception:
        frappe.log_error(" planning_period get_all_periods")
        frappe.throw(_("Erreur lors du chargement de toutes les périodes."))


@frappe.whitelist()
def get_default_period():
    try:
        calendar = frappe.get_doc("Calendar Planing", "Defaut")
        periods = frappe.get_all('Planning Period', filters={"parent":calendar.name},fields=["name","libelle","heure_de_debut","heure_de_fin"])
        return  get_unique_sorted_period([{"name":p.name,"libelle": p.libelle,"fuseau_horaire":calendar.fuseau_horaire,"heure_de_debut":p.heure_de_debut,"heure_de_fin":p.heure_de_fin} for p in periods])
    except Exception:
        frappe.log_error(" planning_period get_default_period")
        frappe.throw(_("Erreur lors du chargement de la période par défaut."))
