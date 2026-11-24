import frappe

import udshed.utils.time_utils as time_utils

# Nom du calendrier par défaut : c'est aussi la valeur par défaut du champ
# « calendrier » des niveaux (voir udshed.api.reregistration.add_level).
CALENDRIER_DEFAUT = "Defaut"

TARIFS_PAR_GRADE = {
    "Professionnel de Classe A": 5000,
    "Professionnel de Classe B": 5000,
    "Professionnel de Classe C": 5000,
    "Professionnel de Classe D": 5000,
    "ATER": 2500,
    "Assistant": 7000,
    "Chargé de Cours": 7500,
    "Docteur": 8000,
    "Maitre de Conférences": 10000,
    "Professeur": 12000,
}


def create_default_data():
    # Crée l'année académique courante si aucune n'est configurée
    # (et la renseigne dans Udshed Setting.current_year).
    time_utils.get_default_academic_year()
    create_default_calendar_period()
    create_default_config_setting()


def create_default_calendar_period():
    # Le DocType est nommé par « nom_du_planing » : on teste ce même nom.
    if frappe.db.exists("Calendar Planing", CALENDRIER_DEFAUT):
        return

    default_calendar = frappe.get_doc({
        "doctype": "Calendar Planing",
        "nom_du_planing": CALENDRIER_DEFAUT,
        "fuseau_horaire": "GMT +1",
    })
    default_calendar.append("heure_planification", {
        "doctype": "Planning Period",
        "heure_de_debut": "08:00:00",
        "heure_de_fin": "12:00:00",
        "libelle": "Matin",
    })
    default_calendar.append("heure_planification", {
        "doctype": "Planning Period",
        "heure_de_debut": "13:30:00",
        "heure_de_fin": "16:45:00",
        "libelle": "Soir",
    })

    default_calendar.insert(ignore_permissions=True)
    frappe.db.commit()


def create_default_config_setting():
    """Ajoute les tarifs horaires par grade absents (idempotent : relançable
    sans créer de doublons ni écraser un tarif modifié par l'utilisateur)."""
    udshed_setting = frappe.get_single("Udshed Setting")
    grades_existants = {
        row.grade for row in udshed_setting.get("configuration_des_paiements_par_grade") or []
    }
    ajouts = 0
    for titre, prix in TARIFS_PAR_GRADE.items():
        if titre in grades_existants:
            continue
        udshed_setting.append("configuration_des_paiements_par_grade", {
            "grade": titre,
            "prix_heure": prix,
        })
        ajouts += 1
    if ajouts:
        udshed_setting.save(ignore_permissions=True)


def create_releve_notes_pf():
    from udshed.scripts.create_print_format import create_releve_notes_print_format

    create_releve_notes_print_format()


def after_install():
    # Workspaces et sidebars sont synchronisés par Frappe depuis les dossiers
    # standard de l'app (workspace/, workspace_sidebar/, desktop_icon/) :
    # aucun chargement manuel n'est nécessaire ici.
    create_default_data()
    create_releve_notes_pf()
