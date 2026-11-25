# -*- coding: utf-8 -*-
import re

import frappe
from frappe import _

from udshed.utils import securite

_EMOJI_INDIQUES = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"  # drapeaux (regional indicator symbols 🇨🇲)
    "\U0001F300-\U0001F5FF"  # symboles èmoticônes divers
    "\U0001F900-\U0001F9FF"
    "\U00002600-\U000026FF"
    "\U0001F000-\U0001F02F"
    "]+"
)


def get_school_logo_url():
    """Retourne l'URL absolue du logo configuré (Udshed Setting → school_logo).

    Retourne une chaîne vide si aucun logo n'est configuré.
    """
    setting = frappe.get_single("Udshed Setting")
    logo = getattr(setting, "school_logo", None) or ""
    if not logo:
        return ""
    try:
        if logo.startswith(("http://", "https://")):
            return logo
        return frappe.utils.get_url(logo)
    except Exception:
        return ""


def _nettoyer_telephone(valeur, indicatif_defaut="+237"):
    """Retire drapeaux/emojis/espaces d'un numéro et garantit un indicatif.

    Retourne le numéro au format « +23769845621 » (chiffres seuls, sans
    drapeau ni séparateur). Si aucun indicatif (absence de « + »), on le
    préfixe avec l'indicatif par défaut du Cameroun.
    """
    if not valeur:
        return ""
    texte = _EMOJI_INDIQUES.sub("", str(valeur))
    signe = ""
    if texte.lstrip().startswith("+"):
        signe = "+"
    chiffres = "".join(caractere for caractere in texte if caractere.isdigit())
    if not chiffres:
        return ""
    if signe:
        return signe + chiffres
    return indicatif_defaut + chiffres


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


COOKIE_FICHE = "udshed_fiche_candidature"


def jeton_fiche_candidature(dossier):
    """Jeton permanent autorisant le téléchargement de la fiche de `dossier`.

    Remis uniquement au candidat : cookie posé à la soumission et lien de
    l'email d'accusé de réception.
    """
    return securite.signer("fiche-candidature", dossier)


def poser_cookie_fiche(dossier):
    """Mémorise dans le navigateur du candidat le droit de télécharger sa fiche.

    Utilisé juste après la soumission (formulaire web ou page de dépôt) : la
    page /candidature-success ne reçoit que le numéro de dossier dans l'URL.
    """
    cookie_manager = getattr(frappe.local, "cookie_manager", None)
    if not cookie_manager or not dossier:
        return
    cookie_manager.set_cookie(
        COOKIE_FICHE,
        f"{dossier}:{jeton_fiche_candidature(dossier)}",
        max_age=7 * 24 * 60 * 60,
        httponly=True,
    )


def _jeton_depuis_cookie(dossier):
    valeur = (frappe.request.cookies.get(COOKIE_FICHE) if frappe.request else None) or ""
    nom, _sep, jeton = valeur.partition(":")
    return jeton if nom == dossier else None


def _verifier_acces_fiche_candidature(doc, jeton=None):
    """Personnel habilité, ou candidat porteur du jeton (paramètre ou cookie)."""
    if frappe.session.user != "Guest" and frappe.has_permission(
        "Session Inscription Candidate", "read", doc=doc
    ):
        return
    for candidat in (jeton, _jeton_depuis_cookie(doc.name)):
        if candidat and securite.verifier_signature(candidat, "fiche-candidature", doc.name):
            return
    frappe.throw(_("Lien de téléchargement invalide."), frappe.PermissionError)


@frappe.whitelist(allow_guest=True)
def get_filieres():
    """Filières proposées dans le formulaire public de candidature.

    Données publiques (code + libellé). Remplace `frappe.client.get_list`,
    refusé aux invités qui n'ont pas de permission sur « Field of study ».
    """
    return frappe.get_all(
        "Field of study",
        fields=["name", "name_of_field"],
        order_by="name_of_field asc",
        limit_page_length=0,
    )


@frappe.whitelist(allow_guest=True)
def telecharger_fiche_pdf(dossier=None, jeton=None):
    """Génère et télécharge la fiche de candidature PDF du candidat.

    Appelé depuis la page de confirmation (`/candidature-success`) après la
    soumission : bouton « Télécharger ma fiche PDF ».

    La photo d'identité est convertie en data-URI (base64) car elle peut être
    stockée dans `/private/files/`, inaccessible par wkhtmltopdf sans session
    (échec ContentAccessDenied). Les fichiers non-images (ex. .MP4) sont
    simplement ignorés.
    """
    from frappe.utils import cint

    if not dossier or dossier.lower() in ("undefined", "null"):
        frappe.throw("Numéro de dossier manquant.")

    if not frappe.db.exists("Session Inscription Candidate", dossier):
        frappe.throw(_("Lien de téléchargement invalide."), frappe.PermissionError)
    doc = frappe.get_doc("Session Inscription Candidate", dossier)
    _verifier_acces_fiche_candidature(doc, jeton)

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

    from udshed.api.school_setting import get_logo_data_uri
    from udshed.utils.campagne import annee_cible
    from udshed.utils.etablissement import etablissement

    # Logo embarqué (data-URI) : le rendu PDF ne dépend d'aucune URL, et un
    # logo en fichier privé reste lisible.
    html = frappe.render_template(
        "templates/print/fiche_candidature.html",
        {
            "doc": doc,
            "photo_data_uri": photo_data_uri,
            "school_name": etablissement().nom,
            "logo_url": get_logo_data_uri(),
            "annee": annee_cible(doc),
        },
    )

    from weasyprint import HTML
    pdf_bytes = HTML(string=html, base_url=frappe.utils.get_url()).write_pdf()

    frappe.response["filename"] = f"Fiche-Candidature-{doc.name}.pdf"
    frappe.response["filecontent"] = pdf_bytes
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
