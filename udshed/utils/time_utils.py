import frappe
from datetime import date
from datetime import datetime

def get_default_academic_year():
    default_academic_year =frappe.db.get_single_value('Udshed Setting', 'current_year')
    today = date.today()
    past_year = today.year
    current_year = today.year
    current_month = today.month
    if current_month >= 9:  # Si nous sommes en septembre ou après, l'année académique commence cette année
        current_year += 1
    else: 
        past_year -= 1  # Sinon, l'année académique a commencé l'année précédente

    if default_academic_year:
        # Déjà configurée : c'est un nom (str), rien à créer.
        return default_academic_year

    nouvelle_annee = frappe.get_doc({
        "doctype": "Academic Year",
        "start_month": "Septembre",
        "end_month": "Juin",
        "start_year": past_year,
        "end_year": current_year,

    }).insert(ignore_permissions=True)
    frappe.db.set_single_value('Udshed Setting', 'current_year', nouvelle_annee.name)
    return nouvelle_annee.name