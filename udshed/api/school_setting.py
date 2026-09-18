import frappe

def get_school_setting():
    return frappe.get_single("Udshed Setting")

def get_school_name():
    setting  = get_school_setting()
    if setting.school_name:
        return setting.school_name
    return ""

def get_school_logo():
    setting  = get_school_setting()
    if setting.school_logo:
        return setting.school_logo
    return ""

def get_school_data():
    return get_school_name(), get_school_logo()


def _chemin_fichier_logo():
    """Résout le chemin disque du logo d'école (Udshed Setting.school_logo),
    avec repli sur le logo par défaut de l'app."""
    import os

    valeur = (get_school_logo() or "").strip()
    if valeur.startswith("/"):
        basename = valeur.rsplit("/", 1)[-1]
        if valeur.startswith("/assets/udshed/images/"):
            chemin = frappe.get_app_path("udshed", "public", "images", basename)
        elif valeur.startswith("/private/files/"):
            chemin = frappe.utils.get_site_path("private", "files", basename)
        elif valeur.startswith("/files/"):
            chemin = frappe.utils.get_site_path("public", "files", basename)
        else:
            chemin = ""
        if chemin and os.path.exists(chemin):
            return chemin
    return frappe.get_app_path("udshed", "public", "images", "logo1.png")


def get_logo_data_uri():
    """Data-URI base64 du logo d'école.

    Sert pour les images embarquées dans les impressions PDF : le rendu se
    fait côté serveur et ne doit dépendre d'aucune URL réseau (hosts/DNS,
    ports). Le logo est embarqué directement dans le HTML.
    """
    import base64
    import os

    mimes = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "svg": "image/svg+xml",
    }
    chemin = _chemin_fichier_logo()
    ext = chemin.rsplit(".", 1)[-1].lower() if "." in chemin else "png"
    mime = mimes.get(ext, "image/png")
    try:
        cle = (
            "udshed:logo_data_uri:{mime}:{mt:.0f}:{taille}".format(
                mime=mime, mt=os.path.getmtime(chemin), taille=os.path.getsize(chemin)
            )
        )
    except OSError:
        cle = "udshed:logo_data_uri:default"

    valeur = frappe.cache.get_value(cle)
    if valeur:
        return valeur
    try:
        with open(chemin, "rb") as f:
            contenu = f.read()
    except OSError:
        return ""

    valeur = "data:%s;base64,%s" % (mime, base64.b64encode(contenu).decode("utf-8"))
    frappe.cache.set_value(cle, valeur, expires_in_sec=6 * 3600)
    return valeur