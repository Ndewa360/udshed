import frappe
import json
from datetime import date
import udshed.api.course as course
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count
from datetime import datetime
import udshed.utils.time_utils as time_utils

@frappe.whitelist()
def get_week_planning(academic_year,week_start,filiere=None, niveau=None,teacher=None):
    PlanningItem = DocType("Planning Item")
    TeachingUnit = DocType("Teaching Unit")
    CourseNiveauFiliere = DocType("Course Field of study level item")
    CourseEnseignant = DocType("Course Teacher Item")
    date_week_start = frappe.utils.getdate(week_start)

    query = (
        frappe.qb.from_(PlanningItem)
        .join(TeachingUnit)
        .on(PlanningItem.cours == TeachingUnit.name)
        .join(CourseNiveauFiliere)
        .on(CourseNiveauFiliere.parent == TeachingUnit.name)
        .join(CourseEnseignant)
        .on(CourseEnseignant.parent == TeachingUnit.name)
        .select(
            TeachingUnit.course,
            PlanningItem.salle,
            PlanningItem.batiment,
            PlanningItem.name,
            PlanningItem.type,
            PlanningItem.cours,
            PlanningItem.date,
            PlanningItem.period,
            PlanningItem.mode,
            CourseNiveauFiliere.niveau,
            CourseNiveauFiliere.filiere,
            CourseEnseignant.enseignant,
        )
        .where(
            (PlanningItem.academic_year == academic_year) &
            (PlanningItem.date >= date_week_start) &
            (PlanningItem.date < frappe.utils.add_days(date_week_start, 7))
        )
    )
    if filiere:
        query = query.where(CourseNiveauFiliere.filiere == filiere)
    if niveau:
        query = query.where(CourseNiveauFiliere.niveau == niveau)
    
    if teacher:
        query = query.where(CourseEnseignant.enseignant == teacher)

    data = query.run(as_dict=True)

    # Déduplication : le JOIN avec les deux tables enfants (CourseNiveauFiliere
    # et CourseEnseignant) crée un produit cartésien. On regroupe par Planning
    # Item et on collecte les enseignants uniques.
    seen = {}
    for row in data:
        pid = row.name
        if pid not in seen:
            row._teachers = [row.enseignant] if row.enseignant else []
            seen[pid] = row
        else:
            if row.enseignant and row.enseignant not in seen[pid]._teachers:
                seen[pid]._teachers.append(row.enseignant)

    data = list(seen.values())

    teacher_cache = {}
    def _format_teacher(t_name):
        if not t_name:
            return ""
        if t_name not in teacher_cache:
            try:
                t_doc = frappe.get_doc("Teacher", {"name": t_name})
                teacher_cache[t_name] = (
                    f"{t_doc.grade} {t_doc.first_name} {t_doc.last_name}"
                )
            except Exception:
                teacher_cache[t_name] = t_name
        return teacher_cache[t_name]

    teacher_doc = None
    if teacher:
        teacher_doc = frappe.get_doc("Teacher", {"name": teacher})
        teacher_cache[teacher] = (
            f"{teacher_doc.grade} {teacher_doc.first_name} {teacher_doc.last_name}"
        )

    for doc in data:
        doc["teachers"] = [_format_teacher(t) for t in (doc._teachers or [])]
        doc["enseignant"] = doc["teachers"][0] if doc["teachers"] else ""
        del doc["_teachers"]

        cours = frappe.get_doc("Course", doc.course)
        doc["cours_label"] = cours.intitule

        niveau_doc = frappe.get_doc("Field of study Level", doc.niveau)
        doc["niveau_label"] = niveau_doc.level

        if doc.salle:
            doc["salle"] = (frappe.get_doc("Room", doc.salle)).code
        if doc.batiment:
            doc["batiment"] = (frappe.get_doc("Building", doc.batiment)).code

    return data


@frappe.whitelist()
def create_planning(academic_year, cours, course_type,day_of_week, half_day,batiment=None,salle=None,mode="En présentiel"):
    try:
        teaching_unit = course.get_single_teaching_unit(cours,academic_year)
        cours_teachers = list(map(lambda x: x.enseignant, teaching_unit.table_enseignant))
        concerned_field_of_study_level = list(map(lambda x: {"filiere":x.filiere,"niveau":x.niveau,"name":x.name},teaching_unit.course_levels))
        
        if len(cours_teachers)==0:
            frappe.throw(f"Le cours <b>{teaching_unit.intitule_cours}</b><br/> n'a pas d'enseignant assigné. veuillez assigner un enseignant puis recommencer")

        date_week_start = frappe.utils.getdate(day_of_week)
        
        planning_days = frappe.get_all("Planning Item",{"date":date_week_start, "period":half_day},["name","cours","type","date","period","salle","batiment"])
        for plan in planning_days:
            doc = course.get_single_teaching_unit(plan.cours,academic_year)
            cours_teachers_existing = list(map(lambda x: x.enseignant, doc.table_enseignant))
            used_field_of_study_level = list(map(lambda x: {"filiere":x.filiere,"niveau":x.niveau,"name":x.name},doc.course_levels))

            common_field_of_study_level_existing = set([x["niveau"] for x in concerned_field_of_study_level]).intersection(set([x["niveau"] for x in used_field_of_study_level]))

            if common_field_of_study_level_existing:
                found_field_of_study = []
                for l in common_field_of_study_level_existing:
                    for c in concerned_field_of_study_level:
                        if c["niveau"]==l:
                            current_level = frappe.get_doc("Field of study Level",c["niveau"])
                            found_field_of_study.append(f"{c["filiere"]} {current_level.level}")
                frappe.throw(f"Conflit de plannig détecté <br>Les classes <b>{', '.join(found_field_of_study)}</b> aussi concerné(es) par ce cours déjà occupé(s) avec le cours <b>{doc.intitule_cours}</b> de <b>{', '.join(cours_teachers_existing)}</b> durant cette plage horraire")

            # Check for common teachers
            common_teachers = set(cours_teachers).intersection(set(cours_teachers_existing))
            if common_teachers:
                niveau_filiere_intersect = list(map(lambda x: {"filiere":x.filiere,"niveau":frappe.get_doc("Field of study Level",x.niveau)}, doc.course_levels))
                frappe.throw(f"Conflit de planning détecté avec le cours <b>{doc.intitule_cours}</b> pour les enseignants: <b>{', '.join(common_teachers)}</b>.<br/>Enseignants déjà programmés dans les classes: <b>{', '.join([f"{x["filiere"]} {x["niveau"].level}" for x in niveau_filiere_intersect])}</b>")
            
            if salle and plan.salle == salle:
                niveau_filiere_intersect = list(map(lambda x: {"filiere":x.filiere,"niveau":frappe.get_doc("Field of study Level",x.niveau)}, doc.course_levels))
                frappe.throw(f"Conflit de salle détecté avec la salle <b>{plan.salle}</b><br/>Salle déjà utilisé pour le cours de <b>{doc.intitule_cours}</b> par les classes: <b>{', '.join([f"{x["filiere"]} {x["niveau"].level}" for x in niveau_filiere_intersect])}</b>")
            

        planning_data = {
            "doctype":"Planning Item",
            "cours":teaching_unit.name,
            "type":course_type,
            "date":date_week_start,
            "period":half_day,
            "academic_year":academic_year,
            "mode":mode
        }

        if salle:
            planning_data["salle"] = salle
        if batiment:
            planning_data["batiment"] = batiment
        
        planning = frappe.get_doc(planning_data)

        planning.insert(ignore_permissions = True)
        frappe.db.commit()
        return {
            "status":True,
            "data":planning
        }
    except Exception as e:
        frappe.log_error(f"{str(e)}")
        return {
            "status":False,
            "message":str(e)
        }


@frappe.whitelist()
def update_planning(planning_item_name,academic_year,cours,course_type, day_of_week, half_day,batiment=None,salle=None,mode="En présentiel"):
    try:

        planning_item = frappe.get_doc("Planning Item", planning_item_name)
        teaching_unit = course.get_single_teaching_unit(cours,academic_year)
    
        planning_item.cours = teaching_unit.name
        planning_item.type = course_type
        planning_item.mode = mode

        cours_teachers = list(map(lambda x: x.enseignant, teaching_unit.table_enseignant))
        concerned_field_of_study_level = list(map(lambda x: {"filiere":x.filiere,"niveau":x.niveau,"name":x.name},teaching_unit.course_levels))

        if len(cours_teachers)==0:
            frappe.throw(f"Le cours <b>{teaching_unit.intitule_cours}</b><br/> n'a pas d'enseignant assigné. veuillez assigner un enseignant puis recommencer")

        date_week_start = frappe.utils.getdate(day_of_week)
        
        planning_days = frappe.get_all("Planning Item",{"date":date_week_start, "period":half_day},["name","cours","type","date","period","salle","batiment"])
        for plan in planning_days:
            if plan.name == planning_item_name:
                continue
            doc = course.get_single_teaching_unit(plan.cours,academic_year)
            cours_teachers_existing = list(map(lambda x: x.enseignant, doc.table_enseignant))
            used_field_of_study_level = list(map(lambda x: {"filiere":x.filiere,"niveau":x.niveau,"name":x.name},doc.course_levels))

            #Check for common field_of level
            common_field_of_study_level_existing = set([x["niveau"] for x in concerned_field_of_study_level]).intersection(set([x["niveau"] for x in used_field_of_study_level]))
            if common_field_of_study_level_existing:
                found_field_of_study = []
                for l in common_field_of_study_level_existing:
                    for c in concerned_field_of_study_level:
                        if c["niveau"]==l:
                            current_level = frappe.get_doc("Field of study Level",c["niveau"])
                            found_field_of_study.append(f"{c["filiere"]} {current_level.level}")
                frappe.throw(f"Conflit de plannig détecté <br>Les classes <b>{', '.join(found_field_of_study)}</b> aussi concerné(es) par ce cours déjà occupé(s) avec le cours <b>{doc.intitule_cours}</b> de <b>{', '.join(cours_teachers_existing)}</b> durant cette plage horraire")


            # Check for common teachers
            common_teachers = set(cours_teachers).intersection(set(cours_teachers_existing))
            if common_teachers:
                niveau_filiere_intersect = list(map(lambda x: {"filiere":x.filiere,"niveau":frappe.get_doc("Field of study Level",x.niveau)}, doc.course_levels))
                frappe.throw(f"Conflit de planning détecté avec le cours <b>{doc.intitule_cours}</b> pour les enseignants: <b>{', '.join(common_teachers)}</b>.<br/>Enseignants déjà programmés dans les classes: <b>{', '.join([f"{x["filiere"]} {x["niveau"].level}" for x in niveau_filiere_intersect])}</b>")
            
            if salle and plan.salle == salle:
                niveau_filiere_intersect = list(map(lambda x: {"filiere":x.filiere,"niveau":frappe.get_doc("Field of study Level",x.niveau)}, doc.course_levels))
                frappe.throw(f"Conflit de salle détecté avec la salle <b>{plan.salle}</b><br/>Salle déjà utilisé pour le cours de <b>{doc.intitule_cours}</b> par les classes: <b>{', '.join([f"{x["filiere"]} {x["niveau"].level}" for x in niveau_filiere_intersect])}</b>")
        if salle:
            planning_item.salle = salle
        if batiment:
            planning_item.batiment = batiment
        
        planning_item.save()
        frappe.db.commit()

        return {
            "status":True,
            "data":planning_item
        }
    except Exception as e:
        frappe.log_error(f"{str(e)}")
        return {
            "status":False,
            "message":str(e)
        }


@frappe.whitelist()
def delete_planning(planning_name):
    frappe.delete_doc("Planning Item",planning_name)
    return True

@frappe.whitelist()
def get_planning_type(field_of_study_level,week_start,academic_year):
    week_start_date = datetime.strptime(week_start, "%Y-%m-%d")

    session_exam = frappe.get_all("Session Examen", filters=[
            ["academic_year", "=", academic_year], 
            ["date_debut", "<=",    week_start_date], 
            ["date_de_fin", ">=", week_start_date],
            ["Session Examen Field of study Level", "niveau", "=", field_of_study_level]
        ],
        fields = ["name", "calendar"],
        distinct = True,
    )

    if len(session_exam) > 0:
        return "Examen"
    return "Cours"

