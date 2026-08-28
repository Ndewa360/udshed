# -*- coding: utf-8 -*-
import frappe


@frappe.whitelist(allow_guest=True)
def creer_candidature(donnees=None):
    """Crée une nouvelle candidature Session Inscription Candidate depuis le formulaire public.

    La création déclenche automatiquement l'envoi d'emails
    (accusé de réception au candidat + notification au coordonnateur).
    """
    if isinstance(donnees, str):
        donnees = frappe.parse_json(donnees)
    donnees = donnees or {}

    first_name = (donnees.get("first_name") or "").strip()
    last_name = (donnees.get("last_name") or "").strip()
    email = (donnees.get("email") or "").strip()

    if not first_name or not last_name or not email:
        frappe.throw("Veuillez remplir les champs obligatoires (Prénom, Nom, Email).")

    full_name = f"{first_name} {last_name}".strip()

    doc = frappe.get_doc({
        "doctype": "Session Inscription Candidate",
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "email": email,
        "phone": donnees.get("phone"),
        "sexe": donnees.get("sexe"),
        "birthdate": donnees.get("birthdate"),
        "birth_place": donnees.get("birth_place"),
        "home_city": donnees.get("home_city"),
        "nationality": donnees.get("nationality") or "CM",
        "religion": donnees.get("religion"),
        "marital_status": donnees.get("marital_status"),
        "employment_status": donnees.get("employment_status"),
        "language": donnees.get("language") or "FR",
        "handicap": donnees.get("handicap") or "NON",
        "filiere": donnees.get("filiere"),
        "niveau": donnees.get("niveau"),
        "examination_centre": donnees.get("examination_centre"),
        "last_establishment": donnees.get("last_establishment"),
        "entry_diploma": donnees.get("entry_diploma"),
        "diploma_matricule": donnees.get("diploma_matricule"),
        "father_name": donnees.get("father_name"),
        "father_phone": donnees.get("father_phone"),
        "father_profession": donnees.get("father_profession"),
        "father_email": donnees.get("father_email"),
        "father_city": donnees.get("father_city"),
        "father_country": donnees.get("father_country") or "CM",
        "mother_name": donnees.get("mother_name"),
        "mother_phone": donnees.get("mother_phone"),
        "mother_profession": donnees.get("mother_profession"),
        "mother_email": donnees.get("mother_email"),
        "mother_city": donnees.get("mother_city"),
        "mother_country": donnees.get("mother_country") or "CM",
        "sponsor_name": donnees.get("sponsor_name"),
        "sponsor_phone": donnees.get("sponsor_phone"),
        "sponsor_profession": donnees.get("sponsor_profession"),
        "sponsor_email": donnees.get("sponsor_email"),
        "sponsor_city": donnees.get("sponsor_city"),
        "sponsor_country": donnees.get("sponsor_country") or "CM",
        "sports_activities": donnees.get("sports_activities"),
        "associative_activities": donnees.get("associative_activities"),
        "cultural_activities": donnees.get("cultural_activities"),
        "it_knowledge": donnees.get("it_knowledge"),
        "candidature_status": "En attente",
    })

    try:
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(
            message=str(e),
            title=f"Échec création candidature {full_name}",
        )
        frappe.throw("Une erreur est survenue lors de la soumission de votre candidature. Veuillez réessayer.")

    return {
        "status": "success",
        "numero_dossier": doc.name,
        "nom_complet": doc.full_name,
    }
