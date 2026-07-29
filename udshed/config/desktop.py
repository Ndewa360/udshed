from frappe import _

def get_data():
    return [
        {
            "module_name": "Udshed",
            "type": "module",
            "label": _("UDShed"),
            "color": "blue",
            "icon": "octicon octicon-calendar",
            "items": [
                {
                    "type": "page",
                    "name": "planning-academique",
                    "label": _("Planning académique"),
                    "icon": "octicon octicon-calendar",
                    "description": _("Gestion du planning académique")
                }
            ]
        }
    ]
