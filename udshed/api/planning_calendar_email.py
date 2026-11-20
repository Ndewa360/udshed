import frappe
from frappe import _
from datetime import datetime

import udshed.api.planning_calendar as planning_calendar
import udshed.api.planning_calendar_pdf as planning_calendar_pdf
import udshed.api.school_setting as school_setting
import udshed.api.planning_permission as planning_permission
import udshed.utils.email_utils as email_utils
import udshed.utils.file_utils as file_utils


def _teacher_doc(name):
	if not name:
		return None
	return frappe.db.get_value(
		"Teacher", name, ["name", "email", "grade", "first_name", "last_name"], as_dict=True
	)


def _teacher_label(teacher):
	return " ".join(
		part for part in [teacher.grade or "", teacher.first_name or "", teacher.last_name or ""] if part
	).strip() or teacher.name


def _recipient_from_user(user):
	email = frappe.db.get_value("User", user, "email")
	if not email:
		frappe.throw(_("Adresse email introuvable pour l'utilisateur courant."), frappe.ValidationError)
	return {"name": user, "email": email, "label": user}


def send_planning_to_teacher_email(filters, teacher, school_name, school_logo, pdf, planning_name, start_date, end_date):
	frappe.sendmail(
		recipients=[teacher.email],
		sender=email_utils.get_formatted_sender(),
		subject="UdM: {0}".format(planning_name.replace(".pdf", "")),
		message=email_html_template(school_name, school_logo, teacher.get("label") or _teacher_label(teacher), start_date, end_date),
		attachments=[{"fname": planning_name, "fcontent": pdf}],
		delayed=False,
	)


@frappe.whitelist()
def send_planning_to_mail(filters, to_all_teacher=None, to_teacher=None, to_me=None):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	if not isinstance(filters, dict):
		frappe.throw(_("Filtres invalides."), frappe.ValidationError)
	academic_year = filters.get("academic_year")
	week_start = filters.get("week_start")
	if not academic_year or not week_start:
		frappe.throw(_("Année académique et semaine sont requises."), frappe.ValidationError)
	planning_permission.assert_can_view_planning(
		academic_year,
		filters.get("faculty"),
		filters.get("filiere"),
		filters.get("niveau"),
		filters.get("teacher"),
	)

	school_name, school_logo = school_setting.get_school_data()
	_, _, items, _, _ = planning_calendar_pdf.generate_planning_pdf(filters)
	start_date = planning_calendar.parse_date(week_start)
	end_date = frappe.utils.add_days(start_date, 6)

	recipients = {}

	def add_recipient(teacher, recipient_filters):
		if not teacher or not teacher.get("email"):
			return
		email = str(teacher["email"]).strip()
		if not email:
			return
		if email in recipients:
			for key, value in recipient_filters.items():
				recipients[email]["filters"].setdefault(key, value)
			return
		copy_filters = dict(filters)
		copy_filters.update(recipient_filters)
		recipients[email] = {"teacher": teacher, "filters": copy_filters}

	if to_teacher and filters.get("teacher"):
		teacher = _teacher_doc(filters.get("teacher"))
		if teacher:
			entry = dict(teacher)
			entry["label"] = _teacher_label(teacher)
			add_recipient(entry, {"teacher": teacher.name})

	if to_all_teacher:
		ids = {name for item in items for name in (item.get("teacher_ids") or [])}
		if filters.get("teacher"):
			ids.add(filters.get("teacher"))
		for name in ids:
			teacher = _teacher_doc(name)
			if teacher:
				entry = dict(teacher)
				entry["label"] = _teacher_label(teacher)
				add_recipient(entry, {"teacher": teacher.name})

	if to_me:
		teacher_name = planning_permission._teacher_name(frappe.session.user)
		if teacher_name:
			teacher = _teacher_doc(teacher_name)
			if teacher:
				entry = dict(teacher)
				entry["label"] = _teacher_label(teacher)
				add_recipient(entry, {"teacher": teacher.name})
		else:
			add_recipient(_recipient_from_user(frappe.session.user), {})

	if not recipients:
		frappe.throw(_("Aucun destinataire sélectionné."), frappe.ValidationError)

	frappe.publish_progress(50, title=_("Préparation des destinataires"))
	errors = []
	for email, entry in recipients.items():
		try:
			recipient_filters = entry["filters"]
			planning_permission.assert_can_view_planning(
				recipient_filters.get("academic_year"),
				recipient_filters.get("faculty"),
				recipient_filters.get("filiere"),
				recipient_filters.get("niveau"),
				recipient_filters.get("teacher"),
			)
			pdf, planning_name, _, _, _ = planning_calendar_pdf.generate_planning_pdf(recipient_filters)
			send_planning_to_teacher_email(
				recipient_filters,
				entry["teacher"],
				school_name,
				school_logo,
				pdf,
				planning_name,
				start_date,
				end_date,
			)
		except Exception as exc:
			frappe.log_error(title="planning_calendar_email envoi", message=frappe.get_traceback())
			errors.append("{0}: {1}".format(email, str(exc)))

	frappe.publish_progress(100, title=_("Envoi terminé"))
	if len(errors) == len(recipients):
		frappe.throw(_("Échec de l'envoi : {0}").format("; ".join(errors)), frappe.ValidationError)
	return {
		"sent": len(recipients) - len(errors),
		"failed": len(errors),
		"errors": errors,
	}


def email_html_template(school_name, school_logo, teacher_name, start_date, end_date):
	school_data_logo = file_utils.load_school_logo(school_logo)
	app_logo = file_utils.get_app_logo()
	return f"""
        <div style="font-family: Arial, sans-serif; background:#f4f6f9; padding:30px;">
            <div style="max-width:700px; margin:auto; background:#ffffff; border-radius:10px; overflow:hidden; box-shadow:0 6px 18px rgba(0,0,0,0.08);">
                <div style="background:#1f3c88; padding:25px; text-align:center; color:white;">
                    <div style="margin-bottom:15px;">
                        <img src="{school_data_logo}" style="height:70px;">
                    </div>
                    <div style="font-size:20px; font-weight:bold; letter-spacing:0.5px;">
                        {school_name}
                    </div>
                    <div style="font-size:13px; opacity:0.85; margin-top:5px;">
                        Gestion des emplois du temps via UDSHED
                    </div>
                </div>
                <div style="padding:35px; color:#333;">
                    <h2 style="margin-top:0; color:#1f3c88;">
                        Transmission du planning hebdomadaire
                    </h2>
                    <p>Bonjour <strong>{teacher_name}</strong>,</p>
                    <p>
                        Nous vous prions de bien vouloir trouver en pièce jointe
                        votre planning académique pour la période suivante :
                    </p>
                    <div style="background:#eef2ff; padding:18px; border-radius:8px; margin:20px 0; text-align:center; font-size:16px;">
                        <strong>Du {start_date.strftime('%d %B %Y')} au {end_date.strftime('%d %B %Y')}</strong>
                    </div>
                    <p>
                        Ce document a été généré automatiquement le
                        <strong>{datetime.now().strftime('%d/%m/%Y à %H:%M')}</strong>.
                    </p>
                    <p>Pour toute question relative à ce planning, merci de contacter l’administration académique.</p>
                    <p style="margin-top:30px;">
                        Cordialement,<br>
                        <strong>Administration académique</strong><br>
                        {school_name}
                    </p>
                </div>
                <div style="background:#f1f1f1; padding:20px; text-align:center; font-size:12px; color:#666;">
                    <div style="margin-bottom:10px;">
                        <img src="{app_logo}" style="height:40px;">
                    </div>
                    <div>
                        Email généré par <strong>UDSHED</strong> — Système intelligent de gestion des emplois du temps
                    </div>
                    <div style="margin-top:5px; font-size:11px; opacity:0.8;">
                        © {datetime.now().year} Udshed. Tous droits réservés.
                    </div>
                </div>
            </div>
        </div>
        """
