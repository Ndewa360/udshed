import frappe
from frappe import _
from datetime import datetime,timedelta
import udshed.api.course as course
import udshed.api.statistic_course as statistic_course
import udshed.api.planning as planning
from functools import reduce

@frappe.whitelist()
def statistic_year(academic_year, semestre=None):
    """Statistique global des finances de l'année"""
    try:
        return _statistic_year_impl(academic_year, semestre)
    except Exception:
        frappe.log_error(" statistic_course_finance statistic_year")
        frappe.throw(_("Erreur lors du calcul des statistiques financières."))


def _statistic_year_impl(academic_year, semestre=None):
    teaching_units = course.get_teaching_unit_by_year(academic_year=academic_year,semestre=None)
    teaching_units_key = teaching_units.keys()
    planning_items = planning.get_all_planning_item_by_filter(academic_year,semestre=semestre)
    planing_filtred_key = []
    # print("Planning Items ", teaching_units)

    for item_key in planning_items.keys():
        if item_key in teaching_units_key:
            planing_filtred_key.append(item_key)

    #Preparation de l'ensemble des kpis
    result = {
        "global":{
            "consume_price":0,
            "total_hours": statistic_course.get_total_hours_of_teaching_unit_in_dict(teaching_units),
            "total_price":get_total_price_of_teaching_unit_list(list(teaching_units.values())),
            "done_hours":0,
            "rate_moyenne":get_default_taux(),
            "completion_finance":0,
            "sessions":0,
            "default_currency":frappe.defaults.get_user_default("currency"),
            "default_finance_by_grade":get_default_finance_config()
        },
        "faculte":[]
    }    

     #Preparation des kpis de facultes
    faculty_list = list(set([ unit["faculte"] for key,unit in teaching_units.items()]))
    faculty_list_dict = {}
    for faculty in faculty_list:
        faculty_list_dict[faculty] = {
            "faculty":frappe.get_doc("Faculty",faculty),
            "sessions":0,
            "done_hours":0,
            "total_hours":statistic_course.get_total_hours_of_teaching_unit_in_list([x for x in list(teaching_units.values()) if x["faculte"]==faculty]),
            "total_price":get_total_price_of_teaching_unit_list([x for x in list(teaching_units.values()) if x["faculte"]==faculty]),
            "completion_finance":0,
            "filiere": frappe.db.count("Field of study",{"faculte":faculty}),
            "consume_price":0,
        }
    
    #Pour chaque teaching unit
    for plan_key in planing_filtred_key:
        planning_items_by_course = planning_items[plan_key]
        result["global"]["sessions"]+=len(planning_items_by_course["planning"])
        hours_done=0
        consume_price = 0
        for plan in planning_items_by_course["planning"]:
            period = frappe.get_doc("Planning Period",plan["period"])
            current_hours = datetime.strptime(str(period.heure_de_fin), "%H:%M:%S") - datetime.strptime(str(period.heure_de_debut), "%H:%M:%S")
            hours_done = hours_done +  int(current_hours.total_seconds()/60)
            faculty_list_dict[planning_items_by_course["faculte"]]["sessions"] += 1                
            consume_price += get_price_of_teacher_list_by_donehours(teaching_units[plan_key]["enseignant"],int(current_hours.total_seconds()/3600),plan["type"]) 
        
        # print("Cunsume price ",teaching_units[plan_key]["enseignant"],int(current_hours.total_seconds()/3600),plan["type"],consume_price)
        
        faculty_list_dict[planning_items_by_course["faculte"]]["consume_price"] +=consume_price
        faculty_list_dict[planning_items_by_course["faculte"]]["done_hours"] += hours_done            
        result["global"]["consume_price"] += consume_price
        result["global"]["done_hours"] += hours_done
    result["global"]["completion_finance"] = "{:.2f}".format((result["global"]["consume_price"] / (result["global"]["total_price"] if result["global"]["total_price"]>0 else 1 )) * 100)
    result["global"]["done_hours"] =  int(result["global"]["done_hours"] / 60)
    for f in faculty_list_dict.values():
        total_price = f["total_price"] if f["total_price"] >0 else 1
        result["faculte"].append({
            **f,
            "done_hours":int(f["done_hours"] / 60),
            "completion_finance": "{:.2f}".format((int(f["consume_price"]) /total_price)*100), 
            "completion_color": statistic_course.get_completion_color((int(f["consume_price"]) /total_price)*100)
        })

    return result
    



@frappe.whitelist()
def statistic_cours_faculte(academic_year,faculty,course_type=None,semestre=None):
    """ Statistique de la faculté pour une année"""
    try:
        return _statistic_cours_faculte_impl(academic_year,faculty,course_type,semestre)
    except Exception:
        frappe.log_error(" statistic_course_finance statistic_cours_faculte")
        frappe.throw(_("Erreur lors du calcul des statistiques financières faculté."))


def _statistic_cours_faculte_impl(academic_year,faculty,course_type=None,semestre=None):
    teaching_units = course.get_teaching_unit_by_year(academic_year=academic_year,faculty=faculty,semestre=None)
    teaching_units_key = teaching_units.keys()
    planning_items = planning.get_all_planning_item_by_filter(academic_year=academic_year,faculty=faculty,semestre=semestre)
    planing_filtred_key = []
    # print("Planning Items ", teaching_units)

    for item_key in planning_items.keys():
        if item_key in teaching_units_key:
            planing_filtred_key.append(item_key)

    #Preparation de l'ensemble des kpis
    result = {
        "global":{
            "consume_price":0,
            "total_hours": statistic_course.get_total_hours_of_teaching_unit_in_dict(teaching_units),
            "total_price":get_total_price_of_teaching_unit_list(list(teaching_units.values())),
            "done_hours":0,
            "rate_moyenne":get_default_taux(),
            "completion_finance":0,
            "sessions":0,
            "default_currency":frappe.defaults.get_user_default("currency"),
            "default_finance_by_grade":get_default_finance_config(),
            "filiere_count":0
        },
        "filiere":[],
    }   

     #Preparation des kpis de facultes
    filiere_list_dict = {}    
    for value in teaching_units.values():
        for niveau in value["niveau"]:
            if niveau["filiere"] not in filiere_list_dict.keys():
                filiere_found =frappe.get_doc("Field of study",niveau["filiere"])
                filiere_list_dict[niveau["filiere"]] = {
                    "filiere":filiere_found,
                    "sessions":0,
                    "done_hours":0,
                    "total_hours":0,
                    "total_price":0,
                    "completion_finance":0,
                    "consume_price":0,
                    "completion":0,
                    "teaching_unit":[value],
                    "niveau_count":frappe.db.count("Field of study Level",{"parent":filiere_found.name})
                }
                result["global"]["filiere_count"] +=1
            else:
                filiere_list_dict[niveau["filiere"]]["teaching_unit"].append(value)
    
    #Pour chaque teaching unit
    for plan_key in planing_filtred_key:
        planning_items_by_course = planning_items[plan_key]
        result["global"]["sessions"]+=len(planning_items_by_course["planning"])
        hours_done=0
        consume_price = 0
        filiere_found = list(set([x["filiere"] for x in planning_items_by_course["niveau"]]))
        for plan in planning_items_by_course["planning"]:
            period = frappe.get_doc("Planning Period",plan["period"])
            current_hours = datetime.strptime(str(period.heure_de_fin), "%H:%M:%S") - datetime.strptime(str(period.heure_de_debut), "%H:%M:%S")
            consume_price_item = get_price_of_teacher_list_by_donehours(teaching_units[plan_key]["enseignant"],int(current_hours.total_seconds()/3600),plan["type"]) 

            hours_done = hours_done +  int(current_hours.total_seconds()/60)
            for f in filiere_found:
                filiere_list_dict[f]["sessions"] += 1
                filiere_list_dict[f]["consume_price"] +=consume_price_item
            consume_price += consume_price_item

        for f in filiere_found:
            filiere_list_dict[f]["done_hours"] += hours_done
            
        result["global"]["done_hours"] += hours_done
        result["global"]["consume_price"] += consume_price

    result["global"]["completion_finance"] = "{:.2f}".format((result["global"]["consume_price"] / (result["global"]["total_price"] if result["global"]["total_price"]>0 else 1)) * 100)
    result["global"]["done_hours"] =  int(result["global"]["done_hours"] / 60)

    for f in filiere_list_dict.values():
        total_price = get_total_price_of_teaching_unit_list(f["teaching_unit"])
        total_price = total_price if total_price >0 else 1
        f.pop("teaching_unit")

        result["filiere"].append({
            **f,
            "total_price":total_price,
            "done_hours":int(f["done_hours"] / 60),
            "completion": "{:.2f}".format((int(f["consume_price"]) / total_price)*100), 
            "completion_color": statistic_course.get_completion_color((int(f["consume_price"] / 60) / total_price)*100),
        })

    return result




@frappe.whitelist()
def statistic_fieldofstudy(academic_year,faculty,filiere,semestre=None,course_type=None):
    """Statistic progression financier pour filiére"""
    try:
        return _statistic_fieldofstudy_impl(academic_year,faculty,filiere,semestre,course_type)
    except Exception:
        frappe.log_error(" statistic_course_finance statistic_fieldofstudy")
        frappe.throw(_("Erreur lors du calcul des statistiques financières filière."))


def _statistic_fieldofstudy_impl(academic_year,faculty,filiere,semestre=None,course_type=None):
    teaching_units = course.get_teaching_unit_by_year(academic_year=academic_year,faculty=faculty,field_of_study=filiere,semestre=semestre)
    teaching_units_key = teaching_units.keys()
    planning_items = planning.get_all_planning_item_by_filter(academic_year=academic_year,faculty=faculty,field_of_study=filiere,semestre=semestre ,course_type=course_type)

    planing_filtred_key = []

    #On se rassure qu'on ne travail qu'avec les cours dont on a les items de planning    
    for item_key in planning_items.keys():
        if item_key in teaching_units_key:
            planing_filtred_key.append(item_key)

    result = {
        "global":{
            "consume_price":0,
            "sessions":0,
            "done_hours":0,
            "total_hours": statistic_course.get_total_hours_of_teaching_unit_in_dict(teaching_units),
            "total_price":get_total_price_of_teaching_unit_list(list(teaching_units.values())),
            "completion":0,
            "rate_moyenne":get_default_taux(),
            "completion_finance":0,
            "default_currency":frappe.defaults.get_user_default("currency"),
            "default_finance_by_grade":get_default_finance_config(),
            "level_count":0
        },
        "level":[],
    } 

    #Preparation des kpis de filiere
    level_list_dict = {}

    for value in teaching_units.values():
        for niveau in value["niveau"]:
            if niveau["niveau"] not in level_list_dict.keys():
                level_list_dict[niveau["niveau"]] = {
                    "level":frappe.get_doc("Field of study Level",niveau["niveau"]),
                    "sessions":0,
                    "done_hours":0,
                    "total_hours":0,
                    "consume_price":0,
                    "total_price":0,
                    "completion":0,
                    "count_teaching_unit":len(course.get_teaching_unit_by_level(None,None,None,None,None,{"filiere":filiere,"niveau":niveau["niveau"],"academic_year":academic_year})),
                    "teaching_unit":[value]
                }
                result["global"]["level_count"] +=1
            else:
                level_list_dict[niveau["niveau"]]["teaching_unit"].append(value)
    
    #Pour chaque teaching unit
    for plan_key in planing_filtred_key:
        planning_items_by_course = planning_items[plan_key]
        result["global"]["sessions"]+=len(planning_items_by_course["planning"])
        hours_done=0
        consume_price = 0
        level_found = list(set([x["niveau"] for x in planning_items_by_course["niveau"]]))
        for plan in planning_items_by_course["planning"]:
            period = frappe.get_doc("Planning Period",plan["period"])
            current_hours = datetime.strptime(str(period.heure_de_fin), "%H:%M:%S") - datetime.strptime(str(period.heure_de_debut), "%H:%M:%S")
            hours_done = hours_done +  int(current_hours.total_seconds()/60)
            consume_price += get_price_of_teacher_list_by_donehours(teaching_units[plan_key]["enseignant"],int(current_hours.total_seconds()/3600),plan["type"]) 

            for n in level_found:
                level_list_dict[n]["sessions"] += 1


        for n in level_found:
            level_list_dict[n]["done_hours"] += hours_done
            level_list_dict[n]["consume_price"] +=consume_price
            
        result["global"]["done_hours"] += hours_done
        result["global"]["consume_price"] += consume_price

    
    result["global"]["done_hours"] =  int(result["global"]["done_hours"] / 60)
    result["global"]["completion_finance"] = "{:.2f}".format((result["global"]["consume_price"] / (result["global"]["total_price"] if result["global"]["total_price"] >0 else 1)) * 100)
    for l in level_list_dict.values():
        total_price = get_total_price_of_teaching_unit_list(l["teaching_unit"])
        total_price = total_price if total_price >0 else 1
        l.pop("teaching_unit")

        result["level"].append({
            **l,
            "total_price":total_price,
            "done_hours":int(l["done_hours"] / 60),
            "completion": "{:.2f}".format((int(l["consume_price"]) / total_price)*100), 
            "completion_color": statistic_course.get_completion_color((int(l["consume_price"] / 60) / total_price)*100),
        })

    return result


@frappe.whitelist()
def statistic_level(academic_year,faculty,filiere,niveau,semestre=None,course_type=None):
    try:
        return _statistic_level_impl(academic_year,faculty,filiere,niveau,semestre,course_type)
    except Exception:
        frappe.log_error(" statistic_course_finance statistic_level")
        frappe.throw(_("Erreur lors du calcul des statistiques financières niveau."))


def _statistic_level_impl(academic_year,faculty,filiere,niveau,semestre=None,course_type=None):
    teaching_units = course.get_teaching_unit_by_year(academic_year=academic_year,faculty=faculty,field_of_study=filiere,level=niveau,semestre=semestre)
    teaching_units_key = teaching_units.keys()
    planning_items = planning.get_all_planning_item_by_filter(academic_year=academic_year,faculty=faculty,field_of_study=filiere,level=niveau,semestre=semestre ,course_type=course_type)

    planing_filtred_key = []

    #On se rassure qu'on ne travail qu'avec les cours dont on a les items de planning    
    for item_key in planning_items.keys():
        if item_key in teaching_units_key:
            planing_filtred_key.append(item_key)
    level = frappe.get_doc("Field of study Level",niveau)
    result = {
        "global":{
            "sessions":0,
            "consume_price":0,
            "done_hours":0,
            "total_hours": statistic_course.get_total_hours_of_teaching_unit_in_dict(teaching_units),
            "total_price":get_total_price_of_teaching_unit_list(list(teaching_units.values())),
            "completion_finance":0,
            "default_currency":frappe.defaults.get_user_default("currency"),
            "completion":0,
            "level": f"{level.level}"
        },
        "teaching_unit":[],
    } 
    list_teaching_unit_dict = {}
    for t in teaching_units.values():
        list_teaching_unit_dict[t["name"]] = {
            "teaching_unit":frappe.get_doc("Teaching Unit",t["name"]),
            "sessions":0,
            "consume_price":0,
            "total_price":0,
            "completion":0,
            "completion_price":0,
            "done_hours":0,
            "total_hours":0,
            "sessions_map":{
                "Cours Magistral (CM)":0,
                "Traveaux Pratiques (TP)":0,
                "Traveaux Dirigés (TD)":0,
                "Controlle Continue (CC)":0,
                "Examen de session normal":0,
                "Examen de rattrapage":0
            },
            "teaching_units":[t]
        }

    #Pour chaque teaching unit
    for plan_key in planing_filtred_key:
        planning_items_by_course = planning_items[plan_key]
        result["global"]["sessions"]+=len(planning_items_by_course["planning"])
        hours_done=0
        consume_price = 0

        for plan in planning_items_by_course["planning"]:            
            period = frappe.get_doc("Planning Period",plan["period"])
            current_hours = datetime.strptime(str(period.heure_de_fin), "%H:%M:%S") - datetime.strptime(str(period.heure_de_debut), "%H:%M:%S")

            hours_done = hours_done +  int(current_hours.total_seconds()/60)
            consume_price_item= get_price_of_teacher_list_by_donehours(teaching_units[plan_key]["enseignant"],int(current_hours.total_seconds()/3600),plan["type"]) 

            list_teaching_unit_dict[plan_key]["sessions"] += 1
            list_teaching_unit_dict[plan_key]["consume_price"] += consume_price_item
            consume_price += consume_price_item
            list_teaching_unit_dict[plan_key]["sessions_map"][plan["type"]] +=1

        list_teaching_unit_dict[plan_key]["done_hours"] += hours_done
        hours_to_done = (
            (teaching_units[plan_key]["nombre_dheure_cm"] if teaching_units[plan_key]["nombre_dheure_cm"] else 0) +
            (teaching_units[plan_key]["nombre_dheure_td"] if teaching_units[plan_key]["nombre_dheure_td"] else 0) + 
            (teaching_units[plan_key]["nombre_dheure_tp"] if teaching_units[plan_key]["nombre_dheure_tp"] else 0)
        )
        list_teaching_unit_dict[plan_key]["total_hours"] = hours_to_done
        result["global"]["consume_price"] += consume_price
        result["global"]["done_hours"] += hours_done

    result["global"]["done_hours"] =  int(result["global"]["done_hours"] / 60)
    result["global"]["completion"] = "{:.2f}".format((result["global"]["done_hours"] / (result["global"]["total_hours"] if result["global"]["total_hours"] >0 else 1)) * 100)
    result["global"]["completion_finance"] = "{:.2f}".format((result["global"]["consume_price"] / (result["global"]["total_price"] if result["global"]["total_price"] >0 else 1)) * 100)     
    
    for l in list_teaching_unit_dict.values():
        total_hours = statistic_course.get_total_hours_of_teaching_unit_in_list(l["teaching_units"])

        total_price = get_total_price_of_teaching_unit(teaching_units[l["teaching_unit"].name])
        total_price = total_price if total_price >0 else 1
        result["teaching_unit"].append({
            **l,
            "total_price":total_price,
            "total_hours":total_hours,
            "done_hours":int(l["done_hours"] / 60),
            "completion": "{:.2f}".format((int(l["done_hours"] / 60) / total_hours)*100), 
            "completion_finance": "{:.2f}".format((int(l["consume_price"]) / total_price)*100), 
            "completion_color": statistic_course.get_completion_color((int(l["consume_price"] / 60) / total_price)*100),
        })

    return result

@frappe.whitelist()
def statistic_teacher(academic_year,teacher, faculty=None,filiere=None,niveau=None, semestre=None ):
    """Statistic finace for teacher"""
    try:
        return _statistic_teacher_impl(academic_year,teacher,faculty,filiere,niveau,semestre)
    except Exception:
        frappe.log_error(" statistic_course_finance statistic_teacher")
        frappe.throw(_("Erreur lors du calcul des statistiques financières enseignant."))


def _statistic_teacher_impl(academic_year,teacher, faculty=None,filiere=None,niveau=None, semestre=None ):
    planning_items = planning.get_all_planning_item_by_filter(academic_year=academic_year,faculty=faculty,field_of_study=filiere,level=niveau,semestre=semestre ,teacher=teacher)
    teaching_units = course.get_teaching_unit_by_year(academic_year=academic_year,faculty=faculty,field_of_study=filiere,level=niveau,semestre=semestre,teacher=teacher)
    teaching_units_key = teaching_units.keys()
    planing_filtred_key = []
    
    for item_key in planning_items.keys():
        if item_key in teaching_units_key:
            planing_filtred_key.append(item_key)

    result = {
        "global":{
            "consume_price":0,
            "sessions":0,
            "done_hours":0,
            "total_hours": statistic_course.get_total_hours_of_teaching_unit_in_dict(teaching_units),
            "total_price":get_total_price_of_teaching_unit_list(list(teaching_units.values())),
            "rate_moyenne":get_default_taux(),
            "completion_finance":0,
            "default_currency":frappe.defaults.get_user_default("currency"),
            "completion":0,
        },
        "niveau_filiere":[],
        "teaching_unit":[]
    } 
    list_niveau_filiere_dict = {}
    list_teaching_unit_dict = {}
    for t in teaching_units.values():
        list_teaching_unit_dict[t["name"]] = {
            "teaching_unit":frappe.get_doc("Teaching Unit",t["name"]),
            "sessions":0,
            "completion":0,
            "consume_price":0,
            "total_price":0,
            "completion_finance":0,
            "done_hours":0,
            "total_hours":0,
            "teaching_units":[t],
        }
        for n in t["niveau"]:
            if f"{n["filiere"]}_{n["niveau"]}" in list_niveau_filiere_dict:
                list_niveau_filiere_dict[f"{n["filiere"]}_{n["niveau"]}"]["teaching_units"].append(t)
            else:
                list_niveau_filiere_dict[f"{n["filiere"]}_{n["niveau"]}"]={
                    "filiere":frappe.get_doc("Field of study",n["filiere"]),
                    "niveau":n["niveau"],
                    "sessions":0,
                    "done_hours":0,
                    "total_hours": 0,
                    "completion":0,
                    "consume_price":0,
                    "total_price":0,
                    "completion_finance":0,
                    "teaching_units":[t],
                    "niveau_count":frappe.db.count("Field of study Level",{"parent":n["filiere"]})
                }

    #Pour chaque teaching unit
    for plan_key in planing_filtred_key:
        planning_items_by_course = planning_items[plan_key]
        result["global"]["sessions"]+=len(planning_items_by_course["planning"])
        hours_done=0
        consume_price = 0
        filiere_found = list(set([f"{x["filiere"]}_{x["niveau"]}" for x in planning_items_by_course["niveau"]]))

        for plan in planning_items_by_course["planning"]:
            period = frappe.get_doc("Planning Period",plan["period"])
            current_hours = datetime.strptime(str(period.heure_de_fin), "%H:%M:%S") - datetime.strptime(str(period.heure_de_debut), "%H:%M:%S")
            hours_done = hours_done +  int(current_hours.total_seconds()/60)
            consume_price += get_price_of_teacher_list_by_donehours(teaching_units[plan_key]["enseignant"],int(current_hours.total_seconds()/3600),plan["type"]) 

            list_teaching_unit_dict[plan_key]["sessions"] += 1
            for f in filiere_found:
                list_niveau_filiere_dict[f]["sessions"] +=1
              

        list_teaching_unit_dict[plan_key]["done_hours"] += hours_done
        list_teaching_unit_dict[plan_key]["consume_price"] += consume_price

        for f in filiere_found:
            list_niveau_filiere_dict[f]["done_hours"] +=hours_done
            list_niveau_filiere_dict[f]["consume_price"] +=consume_price

        hours_to_done = (
            (teaching_units[plan_key]["nombre_dheure_cm"] if teaching_units[plan_key]["nombre_dheure_cm"] else 0) +
            (teaching_units[plan_key]["nombre_dheure_td"] if teaching_units[plan_key]["nombre_dheure_td"] else 0) + 
            (teaching_units[plan_key]["nombre_dheure_tp"] if teaching_units[plan_key]["nombre_dheure_tp"] else 0)
        )

        list_teaching_unit_dict[plan_key]["total_hours"] = hours_to_done            
        result["global"]["done_hours"] += hours_done

    result["global"]["to_start_course"] = len(teaching_units) - len(planning_items)
    result["global"]["done_hours"] =  int(result["global"]["done_hours"] / 60)
    result["global"]["completion"] = "{:.2f}".format((result["global"]["done_hours"] / (result["global"]["total_hours"] if result["global"]["total_hours"] >0 else 1)) * 100)
    result["global"]["completion_finance"] = "{:.2f}".format((result["global"]["consume_price"] / (result["global"]["total_price"] if result["global"]["total_price"] >0 else 1)) * 100)

    for l in list_teaching_unit_dict.values():
        total_hours = statistic_course.get_total_hours_of_teaching_unit_in_list(l["teaching_units"])
        total_price = get_total_price_of_teaching_unit_list(l["teaching_units"])
        total_price = total_price if total_price >0 else 1
        result["teaching_unit"].append({
            **l,
            "total_hours":total_hours,
            "total_price":total_price,
            "done_hours":int(l["done_hours"] / 60),
            "completion": "{:.2f}".format((int(l["done_hours"]) / total_hours)*100), 
            "completion_finance": "{:.2f}".format((int(l["consume_price"] / 60) / total_price)*100), 
        })
    
    for f in list_niveau_filiere_dict.values():
        total_hours = statistic_course.get_total_hours_of_teaching_unit_in_list(f["teaching_units"])
        total_hours = total_hours if total_hours>0 else 1
        total_price = get_total_price_of_teaching_unit_list(f["teaching_units"])
        total_price = total_price if total_price >0 else 1
        # f.pop("teaching_unit")Cour
        result["niveau_filiere"].append({
            **f,
            "total_price":total_price,
            "total_hours":total_hours,
            "done_hours":int(f["done_hours"] / 60),
            "completion_finance": "{:.2f}".format((int(f["consume_price"] / 60) / total_price)*100), 
        })
            
    return result

@frappe.whitelist()
def get_default_finance_config():
    """Get defaut Config finance by title"""
    udshed_config = frappe.doc = frappe.get_single('Udshed Setting')
    config_payement_list = {}
    for config_pay in udshed_config.configuration_des_paiements_par_grade:
        if config_pay.grade not in config_payement_list.keys():
            config_payement_list[config_pay.grade]= int(config_pay.prix_heure)
    return config_payement_list


#Calcul du taux par défaut

def get_default_taux():
    config_payment_list = get_default_finance_config()
    somme = sum(config_payment_list.values())
    return somme /( len(config_payment_list) if len(config_payment_list)>0 else 1)

def get_price_of_teacher_list_by_donehours(teacher_list, done_hours, type_planning):
    config_payment_list = get_default_finance_config()
    done_price= 0
    for t in teacher_list:
        if t["type_cours"] != type_planning:
            continue
        teacher = frappe.get_doc("Teacher",t["enseignant"])
        titre = teacher.titre
        if titre in config_payment_list.keys():
            done_price += config_payment_list[titre]*done_hours
        else:
            frappe.throw(f"Configuration manquante<br>Veuillez configurez les prix par haire pour le titre <b>{titre}</b> dans le paneau de configuration général et réessayez")
    
    return done_price

def get_total_price_of_teaching_unit_list(teachint_units):
    total_price = 0
    for t in teachint_units:
        total_price += get_total_price_of_teaching_unit(t)
    
    return total_price
        
def get_total_price_of_teaching_unit(teaching_unit):
    # teacher_list = list(map(lambda:x.enseignant,teaching_unit.table_enseignant))
    config_payment_list = get_default_finance_config()
    list_hours_by_type = {
        "Cours Magistral (CM)":teaching_unit["nombre_dheure_cm"],
        "Travaux Pratique (TP)":teaching_unit["nombre_dheure_tp"],
        "Travaux Dirigés (TD)":teaching_unit["nombre_dheure_td"],
        "Cours":teaching_unit["nombre_dheure_cm"],
    }
    total_price = 0
    for t in teaching_unit["enseignant"]:
        if not t["enseignant"]:
            continue
        teacher = frappe.get_doc("Teacher",t["enseignant"])
        titre = get_titre_of_teacher(teacher)
        
        if titre in config_payment_list.keys():
            total_price += config_payment_list[titre]*int(list_hours_by_type[t["type_cours"]])
        else:
            frappe.throw(f"Configuration manquante<br>Veuillez configurez les prix par heure pour le titre <b>{titre}</b> dans le paneau de configuration général et réessayez")
    
    return total_price+list_hours_by_type["Cours"]


def get_titre_of_teacher(teacher):
    titre  = teacher.titre
    if titre:
        return titre
    grade = teacher.grade
    if grade == "Pr":
        return "Professeur"
    elif grade == "Dr":
        return "Chargé de Cours"
    
    return "Professionnel de Classe D"
