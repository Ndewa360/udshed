import frappe
import os
import base64
from frappe import _
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
import udshed.utils.file_utils as file_utils
import udshed.api.school_setting as school_setting
from datetime import datetime
from io import BytesIO

def load_template(template_file, from_file_db=True):
    if from_file_db:
        file_name = frappe.db.get_value("File", {"file_url": template_file}, "name")
        template_file = frappe.get_doc("File", file_name)
        return DocxTemplate(template_file.get_full_path())
    
    temp_path = os.path.join(
        frappe.get_app_path("udshed"),"templates","words",template_file
    )
    return  DocxTemplate(temp_path)

@frappe.whitelist()
def download_contract_to_signed():
    try:
        tpl = load_template("teacher_contract_tpl.docx",False)

        connected_user = frappe.get_doc("User",frappe.session.user)
        obj = {
            "full_name":connected_user.name,
            "email":connected_user.email,
            "titre":"",
            "grade":"",
            "phone":connected_user.phone
        }
        if frappe.db.exists("Teacher",{"email":connected_user.email}):
            teacher_data = frappe.get_doc("Teacher",{"email":connected_user.email})
            obj = {
                **obj,
                "full_name":teacher_data.name,
                "titre":teacher_data.titre,
                "grade":teacher_data.grade,
            }

        tpl.render(obj)

        output = BytesIO()
        tpl.save(output)
        output.seek(0)

        file_content = output.getvalue()
        return base64.b64encode(file_content).decode()
    except Exception:
        frappe.log_error(" generate_teacher_doc download_contract_to_signed")
        frappe.throw(_("Erreur lors de la génération du contrat."))

@frappe.whitelist()
def download_signed_contract(url_file):
    try:
        doc = load_template(url_file,True)
        doc.render({})

        output = BytesIO()
        doc.save(output)
        output.seek(0)

        file_content = output.getvalue()
        return base64.b64encode(file_content).decode()
    except Exception:
        frappe.log_error(" generate_teacher_doc download_signed_contract")
        frappe.throw(_("Erreur lors du téléchargement du contrat signé."))


@frappe.whitelist()
def download_progression_cours(teaching_unit,teacher,nbre_heure,total_heure):
    try:
        doc = load_template("fiche_progression_cours.docx",False)
        teacher_obj = frappe.get_doc("Teacher",teacher)

        teaching_unit_obj = frappe.get_doc("Teaching Unit",teaching_unit)
        class_list = ""

        for c_level in teaching_unit_obj.course_levels:
            filiere = c_level.filiere
            level = frappe.get_doc("Field of study Level",c_level.niveau)
            class_list += f"{filiere} {level.level},"
        
        if len(class_list)>1:
            class_list = class_list[:len(class_list)-1]
        data_to_render ={
            "teacher_name":teacher_obj.name,
            "teacher_grade":teacher_obj.titre if teacher_obj.titre else "",
            "classes_list":class_list,
            "nbre_heure":f"{nbre_heure}/{total_heure} Heures",
            "cours_intitule":teaching_unit_obj.intitule_cours,
            "today_date": datetime.now().strftime("%d/%m/%Y"),
            "created_date":datetime.now().strftime("%d/%m/%Y")
        }

        if frappe.db.exists("File",{"file_url": school_setting.get_school_logo()}):
            logo_path = frappe.get_doc("File", {"file_url": school_setting.get_school_logo()}).get_full_path()
            logo_school = InlineImage(doc, logo_path, width=Mm(40))
            data_to_render = {
                **data_to_render,
                "logo_compagny":logo_school
            }

        doc.render(data_to_render)

        output = BytesIO()
        doc.save(output)
        output.seek(0)

        file_content = output.getvalue()
        return base64.b64encode(file_content).decode()
    except Exception:
        frappe.log_error(" generate_teacher_doc download_progression_cours")
        frappe.throw(_("Erreur lors de la génération de la fiche de progression."))
