import frappe


def execute():
    """Dépublie l'ancien Web Form « reinscription-etudiant ».

    Ses fichiers ont été supprimés du code (commit ddfd3ec, remplacé par la
    page Desk « reinscription_etudiant »), mais l'enregistrement restait
    publié, sans connexion obligatoire, et insérait des Academic
    Reregistration avec ignore_permissions. Le document est conservé
    (simple dépublication).
    """
    if frappe.db.exists("Web Form", "reinscription-etudiant"):
        frappe.db.set_value("Web Form", "reinscription-etudiant", {"published": 0, "login_required": 1})
