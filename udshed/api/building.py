import frappe
from frappe import _
from frappe.utils import cint, getdate
from frappe.query_builder import DocType
from frappe.query_builder.functions import Concat

import udshed.api.planning_permission as planning_permission


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


@frappe.whitelist()
def get_available_rooms(date, period, building=None):
    planning_permission.assert_can_view_planning(require_filters=False)
    day_date = getdate(date)
    if not period or not frappe.db.exists("Planning Period", period):
        frappe.throw(_("Créneau horaire introuvable."))

    buildings = frappe.get_all(
        "Building",
        filters={"name": building} if building else None,
        fields=["name", "batiment", "code", "campus"],
        order_by="batiment asc, name asc",
        ignore_permissions=True,
    )
    result = {
        "date": str(day_date),
        "period": period,
        "buildings": [],
    }
    if not buildings:
        return result

    building_names = [row.name for row in buildings]
    rooms = frappe.get_all(
        "Room",
        filters={"parent": ["in", building_names]},
        fields=["name", "parent", "code", "etage", "type_de_salle"],
        order_by="parent asc, code asc",
        ignore_permissions=True,
    )
    room_names = [row.name for row in rooms]
    occupied = {}
    if room_names:
        planning_items = frappe.get_all(
            "Planning Item",
            filters={
                "date": str(day_date),
                "period": period,
                "salle": ["in", room_names],
            },
            fields=["salle", "cours"],
            ignore_permissions=True,
        )
        for item in planning_items:
            label = frappe.get_cached_value("Teaching Unit", item.cours, "intitule_cours") if item.cours else None
            occupied[item.salle] = label or item.cours or _("Occupée")

    for building_row in buildings:
        building_rooms = []
        for room in rooms:
            if room.parent != building_row.name:
                continue
            label = "  ".join(part for part in [room.code, room.etage] if part)
            building_rooms.append({
                "value": room.name,
                "label": label or room.name,
                "type": room.type_de_salle,
                "available": room.name not in occupied,
                "occupant": occupied.get(room.name),
            })
        result["buildings"].append({
            "name": building_row.name,
            "label": building_row.batiment or building_row.name,
            "code": building_row.code,
            "campus": building_row.campus,
            "total": len(building_rooms),
            "available_count": sum(1 for room in building_rooms if room["available"]),
            "rooms": building_rooms,
        })
    return result
