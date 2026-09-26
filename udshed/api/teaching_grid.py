import frappe
from frappe import _
import pandas as pd
import os
import unicodedata
from frappe.query_builder import DocType
from frappe.utils import get_site_path
import udshed.utils.file_utils as file_utils
import udshed.api.course as cours_api


def _cle_alphabetique(texte):
    """Clé de tri : insensible à la casse et aux accents (ordinal alphabétique)."""
    norm = unicodedata.normalize("NFD", str(texte or "")).encode("ascii", "ignore").decode()
    return norm.lower()

#Todo 
# 1 - Rétirer les teaching units non utilisé d'une année  

@frappe.whitelist()
def get_academic_teaching_unit(academic_year,faculty,filiere,niveau,semestre):
    try:
        return _get_academic_teaching_unit_impl(academic_year,faculty,filiere,niveau,semestre)
    except Exception:
        frappe.log_error(" teaching_grid get_academic_teaching_unit")
        frappe.throw(_("Erreur lors du chargement de la grille pédagogique."))


def _get_academic_teaching_unit_impl(academic_year,faculty,filiere,niveau,semestre):
    if not (academic_year and filiere and niveau and semestre):
        return {
            "stats": {"ue_count": 0, "course_count": 0, "total_credits": 0, "total_hours": 0},
            "grid": [],
        }
    TeachingUnit = DocType("Teaching Unit")
    TeachingUnitValue = DocType("Teaching Unit Value")
    Course = DocType("Course")
    CourseTeacherItem = DocType("Course Teacher Item")
    CourseFieldOfStudyLevelItem = DocType("Course Field of study level item")
    CourseFieldOfStudy = DocType("Field of study")


    query = (
        frappe.qb.from_(TeachingUnit)
        .join(Course)
        .on(TeachingUnit.course==Course.name)
        .left_join(CourseTeacherItem)
        .on(CourseTeacherItem.parent == TeachingUnit.name)
        .join(CourseFieldOfStudyLevelItem)
        .on(CourseFieldOfStudyLevelItem.parent == TeachingUnit.name)
        .join(CourseFieldOfStudy)
        .on(CourseFieldOfStudy.name==CourseFieldOfStudyLevelItem.filiere)
        .left_join(TeachingUnitValue)
        .on(TeachingUnitValue.name == TeachingUnit.unite_de_valeur)
        .select(
            TeachingUnit.name,
            TeachingUnit.nombre_dheure_cm,
            TeachingUnit.nombre_dheure_tp,
            TeachingUnit.nombre_dheure_td,
            TeachingUnit.nombre_dheure_tpe,
            TeachingUnit.intitule_cours,
            TeachingUnit.course.as_("course_name"),
            TeachingUnit.semestre,
            CourseTeacherItem.enseignant,
            CourseTeacherItem.type_de_cours,
            CourseFieldOfStudyLevelItem.filiere,
            CourseFieldOfStudyLevelItem.niveau,
            CourseFieldOfStudyLevelItem.course_poid,
            CourseFieldOfStudy.faculte,
            TeachingUnitValue.code.as_("ue_code"),
            TeachingUnitValue.intitule.as_("ue_intitule")
        )
        .where(
            (TeachingUnit.academic_year == academic_year) &
            (CourseFieldOfStudy.faculte == faculty) &
            (CourseFieldOfStudyLevelItem.filiere==filiere) &
            ( TeachingUnit.semestre == semestre ) &
            ( CourseFieldOfStudyLevelItem.niveau == niveau )
        )	
    )
    result = {}
    filiere = frappe.get_doc("Field of study",filiere)

    stat_result = {
        'ue_count': 0,
        'course_count': 0,
        'total_credits': 0,
        'total_hours': 0
    }
    data = query.run(as_dict=True)
    for doc in data:
        ue_code = doc.ue_code

        if doc.ue_code in result:
            found_course = False
            for cours in result[ue_code]["courses"]:
                if cours["code"] == doc.course_name:
                    found_course=True
                    if doc.enseignant:
                        cours["teacher"].append({
                            "teacher":doc.enseignant,
                            "type_cours":doc.type_de_cours
                        })                
            if not found_course:
                result[ue_code]["courses"].append({
                    "code":doc.course_name,
                    "title": doc.intitule_cours,
                    "credits": doc.course_poid,
                    "type":"ENS",
                    "nombre_dheure_cm": doc.nombre_dheure_cm,
                    "nombre_dheure_td": doc.nombre_dheure_td,
                    "nombre_dheure_tp": doc.nombre_dheure_tp,
                    "nombre_dheure_tpe": doc.nombre_dheure_tpe,
                    "total_hours": int(doc.nombre_dheure_cm) + int(doc.nombre_dheure_td) + int(doc.nombre_dheure_tp) + int(doc.nombre_dheure_tpe),
                    "type_cours": doc.type_de_cours,
                    "filiere": doc.filiere,
                    "niveau": doc.niveau,
                    "ue_intitule": doc.ue_intitule,
                    "teaching_unit":doc.name,
                    "teacher":[]
                })
                if doc.enseignant:
                    result[ue_code]["courses"][len(result[ue_code]["courses"])-1]["teacher"].append({
                        "teacher":doc.enseignant,
                        "type_cours":doc.type_de_cours
                    })
                result[ue_code]["ue_credits"] += float(doc.course_poid) 
                stat_result["course_count"] +=1
                stat_result["total_credits"] +=float(doc.course_poid) 
                stat_result["total_hours"] +=int(doc.nombre_dheure_cm) + int(doc.nombre_dheure_td) + int(doc.nombre_dheure_tp) + int(doc.nombre_dheure_tpe)
        else:
            result[doc.ue_code] = {
                "ue_code":doc.ue_code,
                "ue_title":doc.ue_intitule,
                "ue_credits":float(doc.course_poid),
                "courses":[
                    {
                        "code":doc.course_name,
                        "title": doc.intitule_cours,
                        "credits": doc.course_poid,
                        "type":"ENS",
                        "nombre_dheure_cm": doc.nombre_dheure_cm,
                        "nombre_dheure_td": doc.nombre_dheure_td,
                        "nombre_dheure_tp": doc.nombre_dheure_tp,
                        "nombre_dheure_tpe": doc.nombre_dheure_tpe,
                        "total_hours": int(doc.nombre_dheure_cm) + int(doc.nombre_dheure_td) + int(doc.nombre_dheure_tp) + int(doc.nombre_dheure_tpe),
                        "type_cours": doc.type_de_cours,
                        "filiere": doc.filiere,
                        "niveau": doc.niveau,
                        "ue_intitule": doc.ue_intitule,
                        "teaching_unit":doc.name,
                        "teacher":[]
                    }
                ],
            }

            if doc.enseignant:
                result[ue_code]["courses"][len(result[ue_code]["courses"])-1]["teacher"].append({
                    "teacher":doc.enseignant,
                    "type_cours":doc.type_de_cours
                })
            stat_result["ue_count"] +=1
            stat_result["course_count"] +=1
            stat_result["total_credits"] +=float(doc.course_poid) 
            stat_result["total_hours"] +=int(doc.nombre_dheure_cm) + int(doc.nombre_dheure_td) + int(doc.nombre_dheure_tp) + int(doc.nombre_dheure_tpe)

    
    for ue in result.keys():
        result[ue]["courses"] = sorted(
            result[ue]["courses"], key=lambda course: (_cle_alphabetique(course["title"]), course["code"])
        )

    return {"stats":stat_result,"grid":dict(sorted(result.items())).values()}







@frappe.whitelist()
def import_grid(file_url,academic_year,faculty,filiere,niveau,semestre):
    """Importer une grille depuis Excel"""
    #a supposer c'est dans une matrice comme dans le test
    data_grid = file_utils.read_frappe_excel(file_url)
    try:
        frappe.db.begin()
        

        #Rétirer tous cours à cette salle de classe
        TeachingUnit = DocType("Teaching Unit")
        FieldOfStudyLevelItem = DocType("Course Field of study level item")

        query_delete = (
            frappe.qb.from_(FieldOfStudyLevelItem)
            .join(TeachingUnit)
            .on(TeachingUnit.name == FieldOfStudyLevelItem.parent)
            .select(
                FieldOfStudyLevelItem.name
            )
            .where( 
                (TeachingUnit.semestre == semestre) &
                (FieldOfStudyLevelItem.filiere == filiere) &
                (FieldOfStudyLevelItem.niveau == niveau) &
                (TeachingUnit.academic_year == academic_year)
            )
        )
        data_to_delete = query_delete.run(as_dict = True)
        for d_del in data_to_delete:
            frappe.delete_doc("Course Field of study level item",d_del.name)

        # frappe.db.delete("Course Field of study level item",filters={"filiere":filiere, "niveau":niveau})

        record_stat = {
            "ues_created":0,
            "ues_updated":0,
            "ues_deleted":0,
            "courses_created":0,
            "courses_deleted":0,
            "courses_updated":0
        }
        teaching_unit_in_grid = []

        academic_year_obj = frappe.get_doc("Academic Year",academic_year)
        proceed_ue = []
        proceed_ens = []
        filiere_doc = frappe.get_doc("Field of study",filiere)

        if not filiere_doc.has_uv_in_grid:
            if not frappe.db.exists("Teaching Unit Value","UNKNOW"):
                worked_ue = frappe.get_doc({
                    "doctype":"Teaching Unit Value",
                    "code":"UNKNOW",
                    "semestre":semestre,
                    "academic_year":academic_year_obj.name
                })
                proceed_ue.append("UNKNOW")
        else:
            worked_ue = None
        for data in data_grid:
            print("Data teaching unit ",data[0],data[4])
            if data[0] and data[4]=="UE":
                proceed_ue.append(data[0])
                if frappe.db.exists({ 'doctype': 'Teaching Unit Value', 'code': data[0],"academic_year":academic_year}):
                    #si UE existe (module) on le met juste à jour
                    worked_ue = frappe.get_doc("Teaching Unit Value",{"code":data[0]})
                    worked_ue.intitule=data[2]
                    worked_ue.semestre=semestre
                    worked_ue.academic_year=academic_year_obj.name
                    worked_ue.save()
                    record_stat["ues_updated"] +=1
                else:
                    worked_ue=frappe.get_doc({
                        "doctype":"Teaching Unit Value",
                        "code":data[0],
                        "intitule":data[2],
                        "semestre":semestre,
                        "academic_year":academic_year_obj.name
                    })
                    record_stat["ues_created"] +=1
                    worked_ue.insert( ignore_permissions=True)
            else:
                if not worked_ue:
                    frappe.throw("Veuillez d'abord spécifier une UE")                    
                proceed_ens.append(data[1])
                if frappe.db.exists({'doctype':"Teaching Unit","course":data[1],"academic_year":academic_year}):
                    #si le cours existe deja on le met à jour
                    teachingUnit = frappe.get_doc("Teaching Unit",{"course":data[1],"academic_year":academic_year})
                    teachingUnit.intitule_cours=data[2]
                    teachingUnit.unite_de_valeur=worked_ue.name
                    teachingUnit.semestre = semestre
                    teachingUnit.credits=int(data[3])
                    teachingUnit.nombre_dheure_cm=int(data[5])
                    teachingUnit.nombre_dheure_td=int(data[6])
                    teachingUnit.nombre_dheure_tp=int(data[7])
                    teachingUnit.nombre_dheure_tpe=int(data[8])
                    #les enseignants
                    #On supprime d'abord ce qui etait présent
                    frappe.db.delete("Course Teacher Item",filters={"parent":teachingUnit.name})
                    record_stat["courses_updated"] +=1
                    is_new=False                
                else:
                    if not frappe.db.exists("Course",data[1]):
                        course = frappe.get_doc({
                            "doctype":"Course",
                            "code":data[1],
                            "intitule":data[2],
                            "semestre":semestre,
                            "nombre_dheure_cm":int(data[5]),
                            "nombre_dheure_td":int(data[6]),
                            "nombre_dheure_tp":int(data[7]),
                            "nombre_dheure_tpe":int(data[8]),
                        })
                        course.insert(ignore_permissions=True)
                    else:
                        course = frappe.get_doc("Course", data[1])

                    teachingUnit = frappe.get_doc({
                        "doctype":"Teaching Unit",
                        "course":course.name,
                        "intitule_cours":data[2],
                        "unite_de_valeur":worked_ue.name,
                        "semestre":semestre,
                        "academic_year":academic_year_obj.name,
                        "credits":int(data[3]),
                        "nombre_dheure_cm":int(data[5]),
                        "nombre_dheure_td":int(data[6]),
                        "nombre_dheure_tp":int(data[7]),
                        "nombre_dheure_tpe":int(data[8]),
                        "table_enseignant":[],
                        "field_of_study":[]
                    })
                    record_stat["courses_created"] +=1
                    is_new = True
                    
                print("Teachers ",data[9],data)
                
                #les enseignants
                if len(data)>=10 and data[9]:
                    teachers_email = data[9].split(",")
                    for teacher_email in teachers_email:
                        if not frappe.db.exists({"doctype":"User", "email":teacher_email}):
                            print("Enseigant innexistant")
                            frappe.throw(f"Erreur l'ors de l'importation. \n\n L'enseignant {teacher_email} introuvable. Renseignez l'addresse email correspondat et réessayez")
                        teacher = frappe.get_doc("Teacher", {"email":teacher_email})
                        teachingUnit.append("table_enseignant", {
                            "enseignant":teacher.name,
                            "type_de_cours":"Cours Magistral (CM)"
                        })
                if len(data)>=11 and data[10]:
                    teachers_email = data[10].split(",")
                    for teacher_email in teachers_email:
                        if not frappe.db.exists({"doctype":"User", "email":teacher_email}):
                            frappe.throw(f"Erreur l'ors de l'importation. \n\n L'enseignant {teacher_email} introuvable. Renseignez l'addresse email correspondat et réessayez")
                        teacher = frappe.get_doc("Teacher", {"email":teacher_email})
                        teachingUnit.append("table_enseignant", {
                            "enseignant":teacher.name,
                            "type_de_cours":"Travaux Dirigés (TD)"
                        })
                if len(data)>=12 and data[11]:
                    teachers_email = data[11].split(",")
                    for teacher_email in teachers_email:
                        if not frappe.db.exists({"doctype":"User", "email":teacher_email}):
                            frappe.throw(f"Erreur l'ors de l'importation. \n\n L'enseignant {teacher_email} introuvable. Renseignez l'addresse email correspondat et réessayez")
                        teacher = frappe.get_doc("Teacher", {"email":teacher_email})
                        teachingUnit.append("table_enseignant", {
                            "enseignant":teacher.name,
                            "type_de_cours":"Travaux Pratique (TP)"
                        })

                #Pour la classe,(faculté, filiere et niveau) on ajoute
                teachingUnit.append("course_levels", {
                    "filiere":filiere,
                    "niveau":niveau,
                    "course_poid":float(data[3])
                })            
                teaching_unit_in_grid.append(teachingUnit.name)

                if is_new:
                    teachingUnit.insert(ignore_permissions=True)
                else:
                    teachingUnit.save()

        cours_api.clean_course_and_ue_by_acaemic_year(academic_year,faculty,filiere,niveau,semestre,proceed_ens,proceed_ue)

        frappe.db.commit()
        # frappe.db.rollback()

        return {
            "status":True,
            "data":record_stat
        }
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"{str(e)}")
        return {
            "status":False,
            "message":str(e)
        }
        # frappe.throw(e)

        # frappe.throw("Erreur d'importation. Réessayez plus tard!")
        
        



@frappe.whitelist()
def export_grid(academic_year,faculty,filiere,niveau,semestre):
    """exporter au format excel la grille d'un semestre"""
    try:        
        grid_to_export = get_academic_teaching_unit(academic_year,faculty,filiere,niveau,semestre)
        exel_grid = []
        headers = [
                'Code UE', 'Code Cours', 'Intitulés', 'Crédits', 'TYPE', 
                'CM', 'TD', 'TP', 'TPE',"Total", 'Email Enseignant (CM)', 'Email Enseignant (TD)', 'Email Enseignant (TP)'
        ]
        exel_grid.append(headers)
        for ue in grid_to_export["grid"]:
            exel_grid.append([
                ue["ue_code"],"",ue["ue_title"],ue["ue_credits"],"UE","","","","","","",""
            ])
            for course in ue["courses"]:
                exel_grid.append([
                    "",course["code"],course["title"],course["credits"],course["type"],
                    course["nombre_dheure_cm"],course["nombre_dheure_td"],course["nombre_dheure_tp"],course["nombre_dheure_tpe"],course["total_hours"],
                    ", ".join([t["teacher"] for t in course["teacher"] if t["type_cours"]=="Cours Magistral (CM)"]),
                    ", ".join([t["teacher"] for t in course["teacher"] if t["type_cours"]=="Travaux Dirigés (TD)"]),
                    ", ".join([t["teacher"] for t in course["teacher"] if t["type_cours"]=="Travaux Pratique (TP)"])
                ])
        exel_grid.append([])
        exel_grid.append([])
        exel_grid.append([
            "Total UE",grid_to_export["stats"]["ue_count"],"","","","","","","","","","",""
        ])
        exel_grid.append([
            "Total Cours",grid_to_export["stats"]["course_count"],"","","","","","","","","","",""
        ])
        exel_grid.append([
            "Total Crédits",grid_to_export["stats"]["total_credits"],"","","","","","","","","","",""
        ])
        exel_grid.append([
            "Total Heures",grid_to_export["stats"]["total_hours"],"","","","","","","","","","",""
        ])
        
        # Créer le DataFrame
        df = pd.DataFrame(exel_grid)
        
        # Générer le nom du fichier
        filename = f"grille_{filiere}_{niveau}_{semestre}-{faculty}-{academic_year}.xlsx"
        file_path = get_site_path('public', 'files', 'templates', filename)
        
        # Créer le dossier s'il n'existe pas
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Sauvegarder le fichier
        df.to_excel(file_path, index=False, header=False)
        
        # Retourner l'URL
        return {
            'success': True,
            'file_url': f'/files/templates/{filename}'
        }
        
    except Exception as e:
        frappe.log_error(f"Erreur download_template: {str(e)}")
        # frappe.throw(e)
        return {
            'success': False,
            'error': str(e)
        }
    

@frappe.whitelist()
def download_template():
    """Générer et télécharger un template Excel pour l'import"""
    try:        
        # Créer un template vide avec la structure attendue
        template_data = []
                
        headers = [
            'Code UE', 'Code Cours', 'Intitulés', 'Crédits', 'TYPE', 
            'CM', 'TD', 'TP', 'TPE', 'Email Enseignant (CM)', 'Email Enseignant (TD)', 'Email Enseignant (TP)'
        ]
        template_data.append(headers)
        
        # Exemple de ligne UE
        template_data.append([
            'IGL111', '', 'Outils Mathématiques I (exemple)', '6', 'UE',
            '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
        ])
        
        # Exemple de ligne cours
        template_data.append([
            '', 'IGL111a', 'Analyse Mathématiques I (exemple)', '3', 'ENS',
            '25', '15', '0', '40', 'enseignantcm@test.com', 'enseignanttd@test.com', 'enseignanttp@test.com', 
        ])
        
        # Ligne vide pour séparer
        template_data.append([])
        
       
        
        # Instructions
        template_data.append([])
        template_data.append(['=== INSTRUCTIONS ===', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['1. Supprimez ces instructions avant import', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['2. Ne modifiez pas la structure des colonnes', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['3. Les codes UE doivent être dans la colonne A (ex: IGL111)', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['4. Les codes cours doivent être dans la colonne B (ex: IGL111a)', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['5. Les lignes UE doivent avoir TYPE = UE', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['6. Les lignes cours doivent avoir TYPE = ENS', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['7. Remplissez les heures, crédits et emails enseignants', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['6. Si plusieurs enseignants donnes le même type (CM, TP, TD), séparrez leurs emails par des virgules', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        
        # Créer le DataFrame
        df = pd.DataFrame(template_data)
        
        # Générer le nom du fichier
        filename = f"teaching_grid_template.xlsx"
        file_path = get_site_path('public', 'files', 'templates', filename)
        
        # Créer le dossier s'il n'existe pas
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Sauvegarder le fichier
        df.to_excel(file_path, index=False, header=False)
        
        # Retourner l'URL
        return {
            'success': True,
            'file_url': f'/files/templates/{filename}'
        }
        
    except Exception as e:
        frappe.log_error(f"Erreur download_template: {str(e)}")
        # frappe.throw(e)
        return {
            'success': False,
            'error': str(e)
        }

            

                              



            
    