import frappe
from frappe.desk.desk_views import DeskViews

def exec():
    dv = DeskViews()
    print("restricted_pages:", sorted(dv.restricted_pages or []))