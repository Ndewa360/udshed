import frappe, json, os
import udshed.utils.time_utils as time_utils

def create_default_data():
    default_acadamic_year = time_utils.get_default_academic_year()
    create_default_calendar_period()
    create_default_config_setting()

def create_default_calendar_period():
    if not frappe.db.exists("Calendar Planing","Default"):
        default_calendar = frappe.get_doc({
            "doctype":"Calendar Planing",
            "nom_du_planing":"Defaut",
            "fuseau_horaire":"GMT +1"
        })
        default_calendar.append("heure_planification",{
            "doctype":"Planning Period",
            "heure_de_debut":"08:00:00",
            "heure_de_fin":"12:00:00",
            "libelle":"Matin",
        })
        default_calendar.append("heure_planification",{
            "doctype":"Planning Period",
            "heure_de_debut":"13:30:00",
            "heure_de_fin":"16:45:00",
            "libelle":"Soir",
        })

        default_calendar.insert()
        frappe.db.commit()

def create_default_config_setting():
    udshed_setting = frappe.get_single("Udshed Setting")
    grade_list = {
        "Professionnel de Classe A":5000,
        "Professionnel de Classe B":5000,
        "Professionnel de Classe C":5000,
        "Professionnel de Classe D":5000,
        "ATER":2500,
        "Assistant":7000,
        "Chargé de Cours":7500,
        "Docteur":8000,
        "Maitre de Conférences":10000,
        "Professeur":12000
    }
    for titre, prix in grade_list.items():
        udshed_setting.append("configuration_des_paiements_par_grade",{
            "grade":titre,
            "prix_heure":prix
        })
    udshed_setting.save(ignore_permissions=True)

def load_json(doctype, path):
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not frappe.db.exists(doctype, data.get("name") or data.get("title")):
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True)

def load_workspace():
    path = os.path.join(
        frappe.get_app_path("udshed"),
        "udshed", "data", "workspaces", "udshed.json"
    )
    load_json("Workspace", path)

def create_releve_notes_pf():
    from udshed.scripts.create_print_format import create_releve_notes_print_format
    create_releve_notes_print_format()

def load_sidebar():
    path = os.path.join(
        frappe.get_app_path("udshed"),
        "udshed", "data", "workspace_sidebar", "udshed_sidebar.json"
    )
    load_json("Workspace Sidebar", path)
    
def after_install():
    create_default_data()
    create_releve_notes_pf()
    # load_workspace()
    # load_sidebar()