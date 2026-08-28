import frappe
from frappe import _
from frappe.utils import cint
from frappe.query_builder import DocType
from frappe.query_builder.functions import Concat


@frappe.whitelist()
def get_room_by_building( building):
    try:
        Room = DocType("Room")
        Building = DocType("Building")

        query = (
            frappe.qb.from_(Room)
            .join(Building)
            .on(Room.parent == Building.name)
            .select(
                Room.name.as_("value"),
                Concat(Room.code,'  ',Room.etage).as_("label") 
            )
            .where(
                (Building.name == building) 
            )
        )

        data = query.run(as_dict=True)
        return data
    except Exception:
        frappe.log_error(" building get_room_by_building")
        frappe.throw(_("Erreur lors du chargement des salles."))