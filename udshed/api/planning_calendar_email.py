import frappe,json

from datetime import datetime
import udshed.api.planning_calendar_pdf as planning_calendar_pdf
import udshed.utils.file_utils as file_utils
import udshed.utils.email_utils as email_utils
import udshed.api.school_setting as school_setting

def send_planning_to_teacher_email(filters,teacher,school_name,school_logo):
    try:
        pdf, planning_name,items, start_date,end_date = planning_calendar_pdf.generate_planning_pdf(filters)
        
        frappe.sendmail(
            recipients = [teacher.email],
            subject =  f"UdM: {planning_name}",
            message =  email_html_template(school_name,school_logo,teacher.name,start_date,end_date),
            attachments= [{
                "fname": planning_name + ".pdf",
                "fcontent": pdf
            }],
            delayed=False,
            sender = email_utils.get_formatted_sender()
        )
    except Exception:
        frappe.log_error(" planning_calendar_email send_planning_to_teacher_email")


@frappe.whitelist()
def send_planning_to_mail(filters,to_all_teacher=None,to_teacher=None,to_me=None):
    try:
        frappe.publish_progress(10, title="Préparation du planning")
        filters = json.loads(filters)
    except (json.JSONDecodeError, TypeError):
        frappe.throw("Filtres invalides.")
    try:
        school_name, school_logo = school_setting.get_school_data()
        pdf, planning_name,items, start_date,end_date = planning_calendar_pdf.generate_planning_pdf(filters)
    except Exception:
        frappe.log_error(" planning_calendar_email send_planning_to_mail generate")
        frappe.throw(_("Erreur lors de la génération du planning PDF."))
    if to_teacher and filters["teacher"]:
        teacher= frappe.get_doc("Teacher", {"name":filters["teacher"]}) 
        frappe.publish_progress(50, title="Préparation des recepteurs")
        frappe.sendmail(
            sender = email_utils.get_formatted_sender(),
            recipients = [teacher.email],
            subject =  f"UdM: {planning_name}",
            message =  email_html_template(school_name,school_logo,teacher.name,start_date,end_date),
            attachments= [{
                "fname": planning_name + ".pdf",
                "fcontent": pdf
            }],
            delayed=False,
        )   
    if to_all_teacher:
        teachers = []
        #Si on a déjà l'enseignant
        if(filters["teacher"]):
            teachers = [filters["teacher"]]

        for item in items:
            if not item["enseignant"] in teachers:
                teachers.append(item["enseignant"])
        for t in teachers:
            planning_teacher = frappe.get_doc("Teacher",{"name":t})
            filters["teacher"] = t

            send_planning_to_teacher_email(filters, planning_teacher,school_name, school_logo)


    if to_me:
        if frappe.db.exists("User", frappe.session.user):
            current_user = frappe.get_doc("User", {"name":frappe.session.user})
        else:

            current_user = frappe.get_doc("Teacher",frappe.session.user)
        frappe.sendmail(
            sender = email_utils.get_formatted_sender(),
            recipients = [current_user.email],
            subject =  f"UdM: {planning_name}",
            message =  email_html_template(school_name, school_logo, current_user.name, start_date, end_date),
            attachments= [{
                "fname": planning_name + ".pdf",
                "fcontent": pdf
            }],
            delayed=False,
        )   

                


def email_html_template(school_name,school_logo, teacher_name,start_date,end_date):
    school_data_logo = file_utils.load_school_logo(school_logo)
    app_logo = file_utils.get_app_logo()
    return f"""
        <div style="font-family: Arial, sans-serif; background:#f4f6f9; padding:30px;">
            <div style="max-width:700px; margin:auto; background:#ffffff; border-radius:10px; overflow:hidden; box-shadow:0 6px 18px rgba(0,0,0,0.08);">

                <!-- HEADER -->
                <div style="background:#1f3c88; padding:25px; text-align:center; color:white;">
                
                <!-- Logo Institution -->
                <div style="margin-bottom:15px;">
                    <img src="{school_data_logo}" style="height:70px;">
                </div>

                <!-- Nom Institution -->
                <div style="font-size:20px; font-weight:bold; letter-spacing:0.5px;">
                    {school_name}
                </div>

                <div style="font-size:13px; opacity:0.85; margin-top:5px;">
                    Gestion des emplois du temps via UDSHED
                </div>
                </div>

                <!-- CONTENU -->
                <div style="padding:35px; color:#333;">
                
                <h2 style="margin-top:0; color:#1f3c88;">
                    📅 Transmission du planning hebdomadaire
                </h2>

                <p>
                    Bonjour <strong>{teacher_name}</strong>,
                </p>

                <p>
                    Nous vous prions de bien vouloir trouver en pièce jointe 
                    votre planning académique pour la période suivante :
                </p>

                <div style="background:#eef2ff; padding:18px; border-radius:8px; 
                            margin:20px 0; text-align:center; font-size:16px;">
                    <strong>
                    Du {start_date.strftime('%d %B %Y')} au {end_date.strftime('%d %B %Y')}
                    </strong>
                </div>

                <p>
                    Ce document a été généré automatiquement le 
                    <strong>{datetime.now().strftime('%d/%m/%Y à %H:%M')}</strong>.
                </p>

                <p>
                    Pour toute question relative à ce planning, merci de contacter 
                    l’administration académique.
                </p>

                <p style="margin-top:30px;">
                    Cordialement,<br>
                    <strong>Administration académique</strong><br>
                    {school_name}
                </p>
                </div>

                <!-- FOOTER -->
                <div style="background:#f1f1f1; padding:20px; text-align:center; font-size:12px; color:#666;">
                
                <!-- Logo App -->
                <div style="margin-bottom:10px;">
                    <img src="{app_logo}" style="height:40px;">
                </div>

                <div>
                    Email généré par <strong>UDSHED</strong> — 
                    Système intelligent de gestion des emplois du temps
                </div>

                <div style="margin-top:5px; font-size:11px; opacity:0.8;">
                    © {datetime.now().year} Udshed. Tous droits réservés.
                </div>

                </div>

            </div>
        </div>
        """
