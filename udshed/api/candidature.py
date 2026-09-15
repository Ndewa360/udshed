# -*- coding: utf-8 -*-
import frappe


@frappe.whitelist(allow_guest=True)
def get_niveaux_filiere(filiere=None):
    """Retourne les niveaux disponibles pour la filière sélectionnée.

    Utilisé par le web form de candidature (section « Choix du candidat ») :
    quand le candidat choisit une filière, les niveaux proposés sont ceux
    configurés sur cette filière (Field of study Level du Field of study).
    """
    if not filiere:
        return []

    niveaux = frappe.get_all(
        "Field of study Level",
        filters={"parent": filiere},
        fields=["level", "order"],
        order_by="order asc, level asc",
        ignore_permissions=True,
    )
    return [n.get("level") for n in niveaux if n.get("level")]


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


@frappe.whitelist(allow_guest=True)
def telecharger_fiche_pdf(dossier=None):
    """Génère et télécharge la fiche de candidature PDF du candidat.

    Appelé depuis la page de confirmation (`/candidature-success`) après la
    soumission : bouton « Télécharger ma fiche PDF ».

    La photo d'identité est convertie en data-URI (base64) car elle peut être
    stockée dans `/private/files/`, inaccessible par wkhtmltopdf sans session
    (échec ContentAccessDenied). Les fichiers non-images (ex. .MP4) sont
    simplement ignorés.

    La génération PDF utilise maintenant WeasyPrint (library Python incluse),
    ce qui dispense d'installer wkhtmltopdf sur la machine.
    """
    from frappe.utils import cint
    from weasyprint import HTML

    if not dossier:
        frappe.throw("Numéro de dossier manquant.")

    doc = frappe.get_doc("Session Inscription Candidate", dossier)

    photo_data_uri = ""
    fichier_id_photo = doc.get("id_photo")
    if fichier_id_photo and fichier_id_photo.startswith("/private/files/"):
        ext = fichier_id_photo.rsplit(".", 1)[-1].lower() if "." in fichier_id_photo else ""
        if ext in ("jpg", "jpeg", "png"):
            chemin = _chemin_fichier(fichier_id_photo)
            import base64 as _base64
            mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
            try:
                with open(chemin, "rb") as f:
                    contenu = f.read()
                photo_data_uri = f"data:{mime};base64,{_base64.b64encode(contenu).decode('utf-8')}"
            except OSError:
                photo_data_uri = ""

    from udshed.api.school_setting import get_school_data

    school_name, school_logo = get_school_data()
    logo_url = school_logo or "/assets/udshed/images/logo.png"
    if logo_url.startswith("/"):
        logo_url = frappe.utils.get_url(logo_url)

    html = frappe.render_template(
        "templates/print/fiche_candidature.html",
        {
            "doc": doc,
            "photo_data_uri": photo_data_uri,
            "school_name": school_name or "UNIVERSITÉ DIGITALE UDSHED",
            "logo_url": logo_url,
        },
    )
    pdf = HTML(string=html, base_url=frappe.local.site).write_pdf()

    frappe.response["filename"] = f"Fiche-Candidature-{doc.name}.pdf"
    frappe.response["filecontent"] = pdf
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/pdf; charset=utf-8"


def _chemin_fichier(file_url):
    """Convertit une URL de fichier (/private/files/...) en chemin complet sur disque."""
    import os
    from frappe.utils import get_site_path
    parts = file_url.split("/", 3)
    if len(parts) == 4 and parts[1] == "private":
        base = os.path.join(frappe.local.site_path, "private", "files")
        nom = parts[3]
    elif len(parts) == 4:
        base = os.path.join(frappe.local.site_path, "public", "files")
        nom = parts[3]
    else:
        base = None
        nom = None
    if base and nom:
        return os.path.join(base, nom)
    return None
