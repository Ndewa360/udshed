# -*- coding: utf-8 -*-
import frappe
import unicodedata
from frappe.model.naming import make_autoname

@frappe.whitelist(allow_guest=True)
def authentifier_et_inscrire(numero_dossier, nom_candidat):
    """
    Vérifie le dossier de candidature et prépare la deuxième étape du formulaire.
    """

    dossier = _get_dossier(numero_dossier, nom_candidat)

    if not dossier:
        frappe.throw("Authentification échouée. Numéro de dossier ou nom incorrect.")

    return {
        "status": "authenticated",
        "numero_dossier": dossier.name,
        "nom_prenom": dossier.full_name,
        "email": dossier.email,
        "filiere": dossier.filiere,
        "classe": dossier.niveau,
        "date_naissance": dossier.birthdate,
        "lieu_naissance": dossier.birth_place,
        "telephone": dossier.phone,
    }


@frappe.whitelist(allow_guest=True)
def enregistrer_inscription(numero_dossier, nom_candidat, donnees=None):
    """Enregistre le formulaire après une authentification réussie."""
    dossier = _get_dossier(numero_dossier, nom_candidat)
    if not dossier:
        frappe.throw("Session d'authentification invalide.")

    if isinstance(donnees, str):
        donnees = frappe.parse_json(donnees)
    donnees = donnees or {}

    deja_inscrit = frappe.db.get_value(
        "Inscription Academique",
        {"dossier_origine": dossier.name},
        ["name", "matricule"],
        as_dict=True,
    )
    if deja_inscrit:
        matricule = deja_inscrit.matricule
    else:
        matricule = make_autoname("25C.###")
        champs_autorises = {
            "annee_academique", "sexe", "nationalite", "region_origine", "langue",
            "religion", "handicape", "situation_matrimoniale", "situatio_emploi",
            "nom_prenom_pere", "pere_telephone", "pere_profession", "pere_ville",
            "nom_prenom_mere", "telephone_mere", "profession_mere", "mere_ville",
            "nom_prenom_sponsor", "telephone_sponsor", "profession_sponsor", "sponsor_ville",
            "dernier_etablissement", "diplome_entree", "matricule_diplome",
            "activites_sportives", "activites_associatives", "activites_culturelles",
            "connaissances_informatiques",
        }
        valeurs = {champ: donnees.get(champ) for champ in champs_autorises if donnees.get(champ) is not None}
        doc_inscription = frappe.get_doc({
            "doctype": "Inscription Academique",
            "matricule": matricule,
            "dossier_origine": dossier.name,
            "nom_prenom": dossier.full_name,
            "email": dossier.email,
            "filiere": dossier.filiere,
            "classe": dossier.niveau,
            "date_naissance": dossier.birthdate,
            "lieu_naissance": dossier.birth_place,
            "telephone": dossier.phone,
            **valeurs,
        })
        doc_inscription.insert(ignore_permissions=True)
        frappe.db.commit()

    return {
        "status": "success",
        "matricule": matricule,
        "pdf_url": _pdf_url(matricule),
    }


@frappe.whitelist()
def get_inscription_report(filiere=None, candidature_status=None):
    """Retourne les candidatures avec leurs statistiques pour le rapport général."""
    filters = {}
    if filiere:
        filters["filiere"] = filiere
    if candidature_status:
        filters["candidature_status"] = candidature_status

    candidates = frappe.get_all(
        "Session Inscription Candidate",
        filters=filters,
        fields=[
            "name", "first_name", "last_name", "full_name", "email",
            "phone", "filiere", "niveau", "candidature_status", "examination_centre",
            "creation",
        ],
        order_by="creation desc",
    )

    filiere_map = {
        field_of_study: frappe.db.get_value(
            "Field of study", field_of_study, "name_of_field"
        ) or field_of_study
        for field_of_study in {c.get("filiere") for c in candidates if c.get("filiere")}
    }
    rows = []
    for candidate in candidates:
        rows.append({
            "name": candidate.get("name"),
            "nom_complet": candidate.get("full_name") or (
                f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}"
            ).strip(),
            "email": candidate.get("email") or "",
            "phone": candidate.get("phone") or candidate.get("telephone") or "",
            "filiere_label": filiere_map.get(
                candidate.get("filiere"), candidate.get("filiere") or "Non défini"
            ),
            "niveau": candidate.get("niveau") or "Non défini",
            "candidature_status": candidate.get("candidature_status") or "En attente",
            "examination_centre": candidate.get("examination_centre") or "Non défini",
            "creation": str(candidate.get("creation") or ""),
        })

    par_statut = {}
    par_filiere = {}
    par_niveau = {}
    for row in rows:
        par_statut[row["candidature_status"]] = par_statut.get(row["candidature_status"], 0) + 1
        par_filiere[row["filiere_label"]] = par_filiere.get(row["filiere_label"], 0) + 1
        par_niveau[row["niveau"]] = par_niveau.get(row["niveau"], 0) + 1

    return {
        "rows": rows,
        "total": len(rows),
        "par_statut": par_statut,
        "par_filiere": par_filiere,
        "par_niveau": par_niveau,
    }


def _get_dossier(numero_dossier, nom_candidat):
    numero_dossier = (numero_dossier or "").strip()
    nom_candidat = _normaliser_texte(nom_candidat)
    if not numero_dossier or not nom_candidat:
        return None

    dossier = frappe.db.get_value(
        "Session Inscription Candidate",
        {"name": numero_dossier},
        [
            "name", "first_name", "last_name", "full_name", "email", "filiere",
            "niveau", "birthdate", "birth_place", "phone",
        ],
        as_dict=True,
    )
    if not dossier:
        return None

    noms_possibles = {
        _normaliser_texte(dossier.get("full_name")),
        _normaliser_texte(dossier.get("first_name")),
        _normaliser_texte(dossier.get("last_name")),
    }
    return dossier if nom_candidat in noms_possibles else None


def _normaliser_texte(valeur):
    texte = " ".join(str(valeur or "").split()).strip().casefold()
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texte)
        if not unicodedata.combining(caractere)
    )


def _pdf_url(matricule):
    return (
        "/api/method/frappe.utils.print_format.download_pdf"
        f"?doctype=Inscription Academique&name={matricule}"
        "&format=Fiche Officielle UDM&no_letterhead=1"
    )
