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


def _cell_texte(valeur):
    """Normalise une cellule Excel en texte propre.

    Pandas livre les cellules numériques en float : un code cours purement
    numerique (« 101 ») arrive en 101.0 et une cellule vide en NaN. Sans cette
    conversion, les codes partent avec « .0 » dans la base et les cellules
    vides passent le test de vérité.
    """
    if valeur is None:
        return ""
    if isinstance(valeur, float):
        if valeur != valeur:  # NaN
            return ""
        if valeur.is_integer():
            return str(int(valeur))
        return str(valeur)
    return str(valeur).strip()


def _cell_entier(valeur, defaut=0):
    """Entier tolérant aux cellules Excel vides ou décimales (« 25 », 25.0)."""
    texte = _cell_texte(valeur).replace(",", ".")
    if not texte:
        return defaut
    try:
        return int(float(texte))
    except ValueError:
        return defaut


def _colonnes_emails(data):
    """Index des colonnes emails (CM, TD, TP) selon le format du fichier.

    Le template d'import a 12 colonnes (emails en 9-11) ; l'export de grille
    ajoute une colonne « Total » en 9, ce qui décale les enseignants en 10-12.
    Lire toujours en 9-11 faisait tomber sur la colonne Total (un float) et
    plantait l'import avec « 'float' object has no attribute 'split' ».
    """
    if len(data) >= 13:
        total = _cell_texte(data[9])
        suite = [_cell_texte(c) for c in data[10:13]]
        if any("@" in c for c in suite) and "@" not in total:
            return [10, 11, 12]
        if not total and any(suite):
            return [10, 11, 12]
        if isinstance(data[9], (int, float)) and data[9] == data[9]:
            return [10, 11, 12]
    return [9, 10, 11]


def _emails_par_type(data):
    """Adresses par type de cours : [(type CM, cellule), (type TD, …), (type TP, …)].

    Les cellules vides gardent leur position : un email en colonne TD ne sera
    jamais attribué au CM parce que la colonne CM était vide.
    """
    types = ("Cours Magistral (CM)", "Travaux Dirigés (TD)", "Travaux Pratique (TP)")
    return [
        (types[i], _cell_texte(data[col]))
        for i, col in enumerate(_colonnes_emails(data))
        if col < len(data)
    ]


def _enseignant_depuis_cellule(entree):
    """Résout une cellule enseignant et retourne le nom du doc Teacher.

    Le template attend une adresse email (User + Teacher) ; l'export de grille
    écrit quant à lui le NOM du Teacher. On accepte les deux formes pour qu'un
    export puisse être réimporté tel quel.
    """
    if "@" in entree:
        if not frappe.db.exists({"doctype": "User", "email": entree}):
            frappe.throw(
                f"Erreur l'ors de l'importation. \n\n L'enseignant {entree} introuvable. "
                "Renseignez l'addresse email correspondat et réessayez"
            )
        teacher = frappe.db.get_value("Teacher", {"email": entree}, "name")
        if not teacher:
            frappe.throw(
                f"Erreur l'ors de l'importation. \n\n L'enseignant {entree} introuvable. "
                "Renseignez l'addresse email correspondat et réessayez"
            )
        return teacher

    teacher = frappe.db.exists("Teacher", entree) or frappe.db.get_value(
        "Teacher", {"full_name": entree}, "name"
    )
    if not teacher:
        frappe.throw(
            f"Erreur l'ors de l'importation. \n\n L'enseignant {entree} introuvable. "
            "Renseignez son adresse email ou son nom exact et réessayez"
        )
    return teacher

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

        worked_ue = None
        if not filiere_doc.has_uv_in_grid:
            # UE générique : réutilisée pour l'année académique en cours uniquement
            # (un même code peut exister sur plusieurs années académiques).
            unknow_ue = frappe.db.exists(
                "Teaching Unit Value", {"code": "UNKNOW", "academic_year": academic_year_obj.name}
            )
            if unknow_ue:
                worked_ue = frappe.get_doc("Teaching Unit Value", unknow_ue)
            else:
                worked_ue = frappe.get_doc({
                    "doctype":"Teaching Unit Value",
                    "code":"UNKNOW",
                    "semestre":semestre,
                    "academic_year":academic_year_obj.name
                })
                worked_ue.insert(ignore_permissions=True)
            proceed_ue.append("UNKNOW")
        for row_index, data in enumerate(data_grid):
            cellules = [_cell_texte(c) for c in data]
            # Lignes vides (séparateurs) et lignes de synthèse de l'export
            # (« Total UE », « Total Crédits »…) : ni UE ni cours.
            if not any(cellules):
                continue
            code_ue = cellules[0]
            code_cours = cellules[1] if len(cellules) > 1 else ""
            type_ligne = cellules[4] if len(cellules) > 4 else ""
            if code_ue.lower().startswith("total"):
                continue
            if len(cellules) < 9:
                frappe.throw(
                    _("Ligne de données {0}: au moins 9 colonnes sont attendues "
                      "(Code UE, Code Cours, Intitulés, Crédits, TYPE, CM, TD, TP, TPE).").format(
                        row_index + 1
                    )
                )
            # Une ligne est une UE dès qu'un code figure en colonne A et
            # qu'aucun code cours n'est en colonne B. Le TYPE (« UE ») est
            # souvent oublié dans les grilles préparées à la main : s'y fier
            # seule faisait perdre l'UE et bloquait l'import des cours suivants.
            est_ue = bool(code_ue) and (type_ligne.upper() == "UE" or not code_cours)
            if est_ue:
                proceed_ue.append(code_ue)
                existing_ue = frappe.db.exists(
                    "Teaching Unit Value", {"code": code_ue, "academic_year": academic_year}
                )
                if existing_ue:
                    #si UE existe (module) on le met juste à jour
                    worked_ue = frappe.get_doc("Teaching Unit Value", existing_ue)
                    worked_ue.intitule=cellules[2]
                    worked_ue.semestre=semestre
                    worked_ue.academic_year=academic_year_obj.name
                    worked_ue.save()
                    record_stat["ues_updated"] +=1
                else:
                    worked_ue=frappe.get_doc({
                        "doctype":"Teaching Unit Value",
                        "code":code_ue,
                        "intitule":cellules[2],
                        "semestre":semestre,
                        "academic_year":academic_year_obj.name
                    })
                    record_stat["ues_created"] +=1
                    worked_ue.insert( ignore_permissions=True)
            elif code_cours:
                if not worked_ue:
                    frappe.throw(
                        _("Ligne Excel {0} : le cours {1} n'a aucune UE au-dessus de lui. "
                          "Ajoutez une ligne UE (code en colonne A) avant ce cours.").format(
                            row_index + 2, code_cours
                        )
                    )
                proceed_ens.append(code_cours)
                if frappe.db.exists({'doctype':"Teaching Unit","course":code_cours,"academic_year":academic_year}):
                    #si le cours existe deja on le met à jour
                    teachingUnit = frappe.get_doc("Teaching Unit",{"course":code_cours,"academic_year":academic_year})
                    teachingUnit.intitule_cours=cellules[2]
                    teachingUnit.unite_de_valeur=worked_ue.name
                    teachingUnit.semestre = semestre
                    teachingUnit.credits=_cell_entier(data[3])
                    teachingUnit.nombre_dheure_cm=_cell_entier(data[5])
                    teachingUnit.nombre_dheure_td=_cell_entier(data[6])
                    teachingUnit.nombre_dheure_tp=_cell_entier(data[7])
                    teachingUnit.nombre_dheure_tpe=_cell_entier(data[8])
                    #les enseignants
                    #On supprime d'abord ce qui etait présent
                    frappe.db.delete("Course Teacher Item",filters={"parent":teachingUnit.name})
                    record_stat["courses_updated"] +=1
                    is_new=False
                else:
                    if not frappe.db.exists("Course",code_cours):
                        course = frappe.get_doc({
                            "doctype":"Course",
                            "code":code_cours,
                            "intitule":cellules[2],
                            "semestre":semestre,
                            "nombre_dheure_cm":_cell_entier(data[5]),
                            "nombre_dheure_td":_cell_entier(data[6]),
                            "nombre_dheure_tp":_cell_entier(data[7]),
                            "nombre_dheure_tpe":_cell_entier(data[8]),
                        })
                        course.insert(ignore_permissions=True)
                    else:
                        course = frappe.get_doc("Course", code_cours)

                    teachingUnit = frappe.get_doc({
                        "doctype":"Teaching Unit",
                        "course":course.name,
                        "intitule_cours":cellules[2],
                        "unite_de_valeur":worked_ue.name,
                        "semestre":semestre,
                        "academic_year":academic_year_obj.name,
                        "credits":_cell_entier(data[3]),
                        "nombre_dheure_cm":_cell_entier(data[5]),
                        "nombre_dheure_td":_cell_entier(data[6]),
                        "nombre_dheure_tp":_cell_entier(data[7]),
                        "nombre_dheure_tpe":_cell_entier(data[8]),
                        "table_enseignant":[],
                        "field_of_study":[]
                    })
                    record_stat["courses_created"] +=1
                    is_new = True

                #les enseignants (colonnes CM/TD/TP, adaptées au format du fichier)
                for type_cours, cellule_email in _emails_par_type(data):
                    for entree in [e.strip() for e in cellule_email.split(",") if e.strip()]:
                        teacher_name = _enseignant_depuis_cellule(entree)
                        teachingUnit.append("table_enseignant", {
                            "enseignant":teacher_name,
                            "type_de_cours":type_cours
                        })

                #Pour la classe,(faculté, filiere et niveau) on ajoute
                teachingUnit.append("course_levels", {
                    "filiere":filiere,
                    "niveau":niveau,
                    "course_poid":float(_cell_entier(data[3]))
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

            

                              



            
    