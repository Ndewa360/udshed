# -*- coding: utf-8 -*-
"""Inscriptions hors candidature : arrivée en cours d'année, import et export.

Page « Liste des inscriptions » :
  - liste et export (Excel / CSV) des Inscription Academique filtrées, dans
    le respect des permissions Frappe ;
  - modèle d'importation et import (Excel / CSV) d'étudiants en masse.

Formulaire « Inscription Academique » :
  - un responsable saisit un étudiant arrivé en cours d'année ; son
    matricule (série Z : 25Z001…) est généré au téléchargement de la fiche.

Les deux parcours partagent `finaliser_inscription_hors_candidature` :
matricule unique, Student, inscription aux UE, compte utilisateur, e-mail —
comme le parcours de candidature (udshed.api.inscription).
"""

import csv
import io
import re
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint, cstr, getdate, nowdate, validate_email_address

from udshed.api.inscription import (
    _annee_academique_courante,
    _auto_enroll_student_bulk,
    _cree_compte_utilisateur,
    _envoyer_email_matricule_async,
    _generer_matricule_atomique,
    _normaliser_texte,
    _telephone_237,
)

ROLES_GESTION = ("System Manager", "Registration Manager", "Agent de scolarité")
LETTRE_HORS_CANDIDATURE = "Z"
VERROU = "udshed_inscription_hors_candidature"
MAX_LIGNES_IMPORT = 2000

STATUT_INSCRIT = "Inscrit"
STATUT_EN_ATTENTE = "En attente de matricule"
STATUT_SANS_FICHE = "Sans inscription académique"

ORIGINE_CANDIDATURE = "Candidature"
ORIGINE_HORS_CANDIDATURE = "Hors candidature"

_RE_MATRICULE = re.compile(r"^[A-Z0-9][A-Z0-9/_-]{2,29}$")

# (clé, en-tête du modèle, obligatoire, aide)
COLONNES = [
    ("matricule", "Matricule", False,
     "Laisser vide pour un nouvel étudiant : son matricule (série Z, ex. 25Z001) est "
     "généré à l'import. Renseigner uniquement pour un étudiant qui possède déjà un matricule."),
    ("nom", "Nom", True, "Nom de famille."),
    ("prenom", "Prénom", True, "Prénom(s)."),
    ("sexe", "Sexe", True, "M ou F (Masculin / Féminin)."),
    ("date_naissance", "Date de naissance", True, "Format JJ/MM/AAAA (ex. 15/03/2004)."),
    ("lieu_naissance", "Lieu de naissance", True, ""),
    ("email", "Email", True, "Adresse unique de l'étudiant : identifiant de son compte."),
    ("telephone", "Téléphone", True, "Sans indicatif, +237 est ajouté automatiquement."),
    ("filiere", "Filière", True, "Code ou libellé de la filière (voir l'onglet « Filières »)."),
    ("niveau", "Niveau", True, "Niveau de la filière, ex. Licence 1 (voir l'onglet « Filières »)."),
    ("annee_academique", "Année académique", False,
     "Ex. 2025-2026. Vide : année choisie dans la fenêtre d'importation."),
    ("nationalite", "Nationalité", False, ""),
    ("region_origine", "Région d'origine", False, ""),
    ("nom_prenom_pere", "Nom et prénom du père", False, ""),
    ("pere_telephone", "Téléphone du père", False, ""),
    ("nom_prenom_mere", "Nom et prénom de la mère", False, ""),
    ("telephone_mere", "Téléphone de la mère", False, ""),
    ("nom_prenom_sponsor", "Nom et prénom du sponsor", False, ""),
    ("telephone_sponsor", "Téléphone du sponsor", False, ""),
    ("dernier_etablissement", "Dernier établissement fréquenté", False, ""),
]
CHAMPS_OPTIONNELS_IA = [
    "nationalite", "region_origine", "nom_prenom_pere", "pere_telephone",
    "nom_prenom_mere", "telephone_mere", "nom_prenom_sponsor", "telephone_sponsor",
    "dernier_etablissement",
]
CHAMPS_TELEPHONE = ("telephone", "pere_telephone", "telephone_mere", "telephone_sponsor")

# Champs « parents » de la page : candidature -> Inscription Academique
PARENTS_CANDIDATURE_VERS_IA = {
    "father_name": "nom_prenom_pere",
    "father_phone": "pere_telephone",
    "father_profession": "pere_profession",
    "father_email": None,
    "father_city": "pere_ville",
    "father_country": None,
    "mother_name": "nom_prenom_mere",
    "mother_phone": "telephone_mere",
    "mother_profession": "profession_mere",
    "mother_email": None,
    "mother_city": "mere_ville",
    "mother_country": None,
    "sponsor_name": "nom_prenom_sponsor",
    "sponsor_phone": "telephone_sponsor",
    "sponsor_profession": "profession_sponsor",
    "sponsor_email": None,
    "sponsor_city": "sponsor_ville",
    "sponsor_country": None,
    "parent_phone": None,
    "email_parent": None,
}


# ====================================================================== #
#  Liste des inscriptions (page) et export
# ====================================================================== #
def lister_inscriptions(filiere=None, annee_academique=None, niveau=None, statut=None):
    """Inscrits visibles par l'utilisateur courant (frappe.get_list)."""
    rows = []
    if frappe.has_permission("Inscription Academique", "read"):
        rows = _lignes_inscriptions(filiere, annee_academique, niveau, statut)
    if not annee_academique and statut in (None, "", STATUT_SANS_FICHE):
        rows += _lignes_candidatures_sans_fiche(filiere, niveau, {r["dossier_origine"] for r in rows})

    par_filiere, par_niveau, par_statut = {}, {}, {}
    for row in rows:
        par_filiere[row["filiere_label"]] = par_filiere.get(row["filiere_label"], 0) + 1
        par_niveau[row["niveau"]] = par_niveau.get(row["niveau"], 0) + 1
        par_statut[row["statut"]] = par_statut.get(row["statut"], 0) + 1

    return {
        "rows": rows,
        "total": len(rows),
        "par_filiere": par_filiere,
        "par_niveau": par_niveau,
        "par_statut": par_statut,
        "annee_courante": _annee_academique_courante(),
        "peut_gerer": _peut_gerer(),
        "peut_exporter": bool(frappe.has_permission("Inscription Academique", "export")),
    }


def _lignes_inscriptions(filiere, annee_academique, niveau, statut):
    filtres = {}
    if filiere:
        filtres["filiere"] = filiere
    if annee_academique:
        filtres["annee_academique"] = annee_academique
    if niveau:
        filtres["classe"] = niveau
    if statut == STATUT_INSCRIT:
        filtres["matricule"] = ["is", "set"]
    elif statut == STATUT_EN_ATTENTE:
        filtres["matricule"] = ["is", "not set"]
    elif statut == STATUT_SANS_FICHE:
        return []

    champs_parents_ia = sorted({c for c in PARENTS_CANDIDATURE_VERS_IA.values() if c})
    inscriptions = frappe.get_list(
        "Inscription Academique",
        filters=filtres,
        fields=[
            "name", "matricule", "dossier_origine", "nom_prenom", "email", "telephone",
            "sexe", "date_naissance", "lieu_naissance", "annee_academique", "filiere",
            "classe", "creation",
        ] + champs_parents_ia,
        order_by="creation desc",
        limit_page_length=0,
    )

    # Détails complémentaires des candidatures d'origine (une seule requête)
    dossiers = [i.dossier_origine for i in inscriptions if i.dossier_origine]
    candidatures = {}
    if dossiers and frappe.has_permission("Session Inscription Candidate", "read"):
        for c in frappe.get_list(
            "Session Inscription Candidate",
            filters={"name": ["in", dossiers]},
            fields=["name", "examination_centre"] + list(PARENTS_CANDIDATURE_VERS_IA),
            limit_page_length=0,
        ):
            candidatures[c.name] = c

    libelles = _libelles_filieres({i.filiere for i in inscriptions})
    rows = []
    for i in inscriptions:
        c = candidatures.get(i.dossier_origine) or {}
        parents = {
            cle: c.get(cle) or (i.get(champ_ia) if champ_ia else "") or ""
            for cle, champ_ia in PARENTS_CANDIDATURE_VERS_IA.items()
        }
        rows.append({
            "name": i.dossier_origine or i.name,
            "inscription": i.name,
            "dossier_origine": i.dossier_origine or "",
            "nom_complet": i.nom_prenom or "",
            "email": i.email or "",
            "phone": i.telephone or "",
            "sexe": i.sexe or "",
            "date_naissance": cstr(i.date_naissance or ""),
            "lieu_naissance": i.lieu_naissance or "",
            "matricule": i.matricule or "",
            "annee_academique": i.annee_academique or "",
            "filiere": i.filiere or "",
            "filiere_label": libelles.get(i.filiere, i.filiere or "Non défini"),
            "niveau": i.classe or "Non défini",
            "statut": STATUT_INSCRIT if i.matricule else STATUT_EN_ATTENTE,
            "origine": ORIGINE_CANDIDATURE if i.dossier_origine else ORIGINE_HORS_CANDIDATURE,
            "examination_centre": c.get("examination_centre") or "Non défini",
            "creation": cstr(i.creation or ""),
            **parents,
        })
    return rows


def _lignes_candidatures_sans_fiche(filiere, niveau, dossiers_avec_fiche):
    """Candidatures « Inscrit » sans Inscription Academique (cas anormal,
    conservé pour ne rien masquer de l'ancienne liste)."""
    if not frappe.has_permission("Session Inscription Candidate", "read"):
        return []
    filtres = {"candidature_status": "Inscrit"}
    if filiere:
        filtres["filiere"] = filiere
    if niveau:
        filtres["niveau"] = niveau
    candidats = [
        c for c in frappe.get_list(
            "Session Inscription Candidate",
            filters=filtres,
            fields=[
                "name", "full_name", "first_name", "last_name", "email", "phone", "sexe",
                "birthdate", "birth_place", "filiere", "niveau", "examination_centre", "creation",
            ] + list(PARENTS_CANDIDATURE_VERS_IA),
            order_by="creation desc",
            limit_page_length=0,
        )
        if c.name not in dossiers_avec_fiche
    ]
    libelles = _libelles_filieres({c.filiere for c in candidats})
    return [
        {
            "name": c.name,
            "inscription": "",
            "dossier_origine": c.name,
            "nom_complet": c.full_name or f"{c.first_name or ''} {c.last_name or ''}".strip(),
            "email": c.email or "",
            "phone": c.phone or "",
            "sexe": c.sexe or "",
            "date_naissance": cstr(c.birthdate or ""),
            "lieu_naissance": c.birth_place or "",
            "matricule": "",
            "annee_academique": "",
            "filiere": c.filiere or "",
            "filiere_label": libelles.get(c.filiere, c.filiere or "Non défini"),
            "niveau": c.niveau or "Non défini",
            "statut": STATUT_SANS_FICHE,
            "origine": ORIGINE_CANDIDATURE,
            "examination_centre": c.examination_centre or "Non défini",
            "creation": cstr(c.creation or ""),
            **{cle: c.get(cle) or "" for cle in PARENTS_CANDIDATURE_VERS_IA},
        }
        for c in candidats
    ]


def _libelles_filieres(codes):
    codes = [c for c in codes if c]
    if not codes:
        return {}
    return {
        f.name: f.name_of_field or f.name
        for f in frappe.get_all(
            "Field of study", filters={"name": ["in", codes]}, fields=["name", "name_of_field"]
        )
    }


COLONNES_EXPORT = [
    ("matricule", "Matricule"),
    ("nom_complet", "Nom et prénom"),
    ("email", "Email"),
    ("phone", "Téléphone"),
    ("sexe", "Sexe"),
    ("date_naissance", "Date de naissance"),
    ("lieu_naissance", "Lieu de naissance"),
    ("annee_academique", "Année académique"),
    ("filiere", "Code filière"),
    ("filiere_label", "Filière"),
    ("niveau", "Niveau"),
    ("statut", "Statut de l'inscription"),
    ("origine", "Origine"),
    ("dossier_origine", "N° de dossier"),
]


@frappe.whitelist()
def exporter_inscriptions(
    format="xlsx", filiere=None, annee_academique=None, niveau=None, statut=None, recherche=None
):
    """Exporte (Excel ou CSV) les inscriptions affichées sur la page, filtres
    et recherche compris. Lecture seule : aucune donnée n'est créée ni modifiée."""
    frappe.has_permission("Inscription Academique", "export", throw=True)

    rows = lister_inscriptions(filiere, annee_academique, niveau, statut)["rows"]
    rows = [r for r in rows if _correspond_recherche(r, recherche)]

    data = [[libelle for _cle, libelle in COLONNES_EXPORT]]
    data += [[r.get(cle) or "" for cle, _libelle in COLONNES_EXPORT] for r in rows]

    nom_fichier = "inscriptions_" + nowdate()
    if (format or "").lower() == "csv":
        _repondre_csv(data, nom_fichier)
    else:
        from frappe.utils.xlsxutils import build_xlsx_response

        build_xlsx_response(data, nom_fichier)


def _correspond_recherche(row, recherche):
    """Même recherche que la barre de recherche de la page."""
    q = (recherche or "").strip().lower()
    if not q:
        return True
    cles = (
        "matricule", "nom_complet", "email", "phone", "filiere_label", "niveau",
        "father_name", "mother_name", "sponsor_name",
    )
    return any(q in cstr(row.get(cle)).lower() for cle in cles)


def _repondre_csv(data, nom_fichier):
    flux = io.StringIO()
    writer = csv.writer(flux, delimiter=";")
    for ligne in data:
        writer.writerow([_cellule_csv_sure(v) for v in ligne])
    frappe.response["type"] = "binary"
    frappe.response["filename"] = nom_fichier + ".csv"
    # BOM : accents correctement lus par Excel
    frappe.response["filecontent"] = ("﻿" + flux.getvalue()).encode("utf-8")


def _cellule_csv_sure(valeur):
    """Neutralise l'injection de formule à l'ouverture dans un tableur."""
    texte = cstr(valeur)
    return "'" + texte if texte[:1] in ("=", "@") else texte


# ====================================================================== #
#  Modèle d'importation
# ====================================================================== #
@frappe.whitelist()
def telecharger_modele_import(format="xlsx"):
    _verifier_droits_gestion()
    entetes = [libelle for _cle, libelle, _obl, _aide in COLONNES]
    nom_fichier = "modele_import_inscriptions"

    if (format or "").lower() == "csv":
        _repondre_csv([entetes], nom_fichier)
        return

    import xlsxwriter
    from frappe.desk.utils import provide_binary_file
    from frappe.utils.xlsxutils import make_xlsx

    flux = io.BytesIO()
    wb = xlsxwriter.Workbook(flux, {"in_memory": True})
    make_xlsx([entetes], "Étudiants", wb=wb, column_widths=[22] * len(entetes))

    instructions = [
        ["Colonne", "Obligatoire", "Comment la remplir"],
        *[[libelle, "Oui" if obl else "Non", aide] for _cle, libelle, obl, aide in COLONNES],
        [],
        ["Règles", "", ""],
        ["", "", "Remplir l'onglet « Étudiants » : une ligne par étudiant, sans modifier les en-têtes."],
        ["", "", "Un étudiant déjà enregistré (même matricule, e-mail ou identité) n'est jamais "
                  "dupliqué : son dossier et son matricule sont réutilisés."],
        ["", "", "Une inscription déjà existante pour l'année est signalée et non recréée."],
        ["", "", "Chaque nouvel étudiant est inscrit aux UE de son niveau, reçoit un compte et "
                  "l'e-mail de son matricule (option de la fenêtre d'importation)."],
        ["", "", "Un bilan détaillé (importées / ignorées / rejetées + motif) est affiché avant "
                  "et après la validation."],
    ]
    make_xlsx(instructions, "Instructions", wb=wb, column_widths=[30, 12, 100])

    filieres = [["Code filière", "Filière", "Niveaux acceptés"]]
    for f in frappe.get_all("Field of study", fields=["name", "name_of_field"], order_by="name asc"):
        niveaux = frappe.get_all(
            "Field of study Level", filters={"parent": f.name}, fields=["level"],
            order_by="order asc, level asc",
        )
        filieres.append([f.name, f.name_of_field or "", ", ".join(n.level for n in niveaux if n.level)])
    make_xlsx(filieres, "Filières", wb=wb, column_widths=[18, 40, 60])

    wb.close()
    provide_binary_file(nom_fichier, "xlsx", flux.getvalue())


# ====================================================================== #
#  Importation
# ====================================================================== #
@frappe.whitelist(methods=["POST"])
def importer_inscriptions(file_url, annee_academique=None, valider=0, envoyer_email=1):
    """Importe un fichier Excel/CSV d'étudiants.

    valider=0 : simulation (aucune écriture) -> bilan prévisionnel.
    valider=1 : création effective, sérialisée par un verrou (un seul import
    ou génération de matricule hors candidature à la fois).
    """
    _verifier_droits_gestion()
    frappe.has_permission("Inscription Academique", "create", throw=True)

    lignes = _lire_fichier(file_url)
    annee = (annee_academique or "").strip() or _annee_academique_courante()

    if not cint(valider):
        return _traiter_import(lignes, annee, executer=False)

    with _verrou(attente=0):
        try:
            bilan = _traiter_import(lignes, annee, executer=True, envoyer_email=cint(envoyer_email))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            raise
    return bilan


def _lire_fichier(file_url):
    if not file_url:
        frappe.throw(_("Veuillez joindre un fichier."))
    nom = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not nom:
        frappe.throw(_("Fichier introuvable."))
    fichier = frappe.get_doc("File", nom)
    fichier.check_permission("read")

    extension = (fichier.file_name or file_url).lower().rsplit(".", 1)[-1]
    contenu = fichier.get_content()
    if extension == "xlsx":
        from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

        if isinstance(contenu, str):
            contenu = contenu.encode("utf-8")
        return read_xlsx_file_from_attached_file(fcontent=contenu) or []
    if extension == "csv":
        from frappe.utils.csvutils import read_csv_content

        return read_csv_content(contenu, use_sniffer=True) or []
    frappe.throw(_("Format non pris en charge : utilisez un fichier Excel (.xlsx) ou CSV (.csv)."))


def _traiter_import(lignes, annee_defaut, executer, envoyer_email=True):
    entetes, donnees, colonnes_ignorees = _decouper_fichier(lignes)
    contexte = _ContexteImport()
    deja_vus = {"matricule": {}, "email": {}, "identite": {}}
    resultats = []

    for numero, brut in donnees:
        valeurs, erreurs = _analyser_ligne(brut, annee_defaut, contexte)
        nom_affiche = f"{valeurs.get('nom', '')} {valeurs.get('prenom', '')}".strip()
        if erreurs:
            resultats.append(_resultat(numero, "Rejetée", valeurs.get("matricule"), nom_affiche, " ; ".join(erreurs)))
            continue

        plan = _planifier(valeurs, deja_vus, numero)
        if plan["action"] != "creer":
            statut = "Ignorée" if plan["action"] == "ignorer" else "Rejetée"
            resultats.append(_resultat(numero, statut, plan.get("matricule") or valeurs.get("matricule"), nom_affiche, plan["motif"]))
            continue

        if not executer:
            resultats.append(_resultat(numero, "À importer", plan.get("matricule") or "", nom_affiche, plan["motif"]))
            continue

        resultats.append(_executer_ligne(numero, valeurs, plan, nom_affiche, envoyer_email))

    compte = lambda *statuts: sum(1 for r in resultats if r["statut"] in statuts)  # noqa: E731
    return {
        "valide": bool(executer),
        "annee_academique": annee_defaut,
        "total": len(resultats),
        "importees": compte("Importée", "À importer"),
        "ignorees": compte("Ignorée"),
        "rejetees": compte("Rejetée"),
        "colonnes_ignorees": colonnes_ignorees,
        "lignes": resultats,
    }


def _resultat(numero, statut, matricule, nom, motif):
    return {"ligne": numero, "statut": statut, "matricule": matricule or "", "nom": nom, "motif": motif}


def _executer_ligne(numero, valeurs, plan, nom_affiche, envoyer_email):
    """Crée l'inscription d'une ligne ; une erreur n'annule que cette ligne."""
    point = "udshed_import_ligne"
    nb_messages = len(frappe.local.message_log or [])
    frappe.db.savepoint(point)
    try:
        ia = frappe.get_doc({
            "doctype": "Inscription Academique",
            "matricule": plan.get("matricule") or None,
            "nom_prenom": nom_affiche,
            "email": valeurs["email"],
            "date_naissance": valeurs["date_naissance"],
            "lieu_naissance": valeurs["lieu_naissance"],
            "telephone": valeurs["telephone"],
            "sexe": valeurs["sexe"],
            "annee_academique": valeurs["annee_academique"],
            "filiere": valeurs["filiere"],
            "classe": valeurs["niveau"],
            **{c: valeurs[c] for c in CHAMPS_OPTIONNELS_IA if valeurs.get(c)},
        })
        ia.insert()  # permissions Frappe de l'utilisateur sur Inscription Academique
        res = finaliser_inscription_hors_candidature(
            ia, nom=valeurs["nom"], prenom=valeurs["prenom"],
            student=plan.get("student"), envoyer_email=envoyer_email,
        )
    except Exception as e:
        frappe.db.rollback(save_point=point)
        if frappe.local.message_log is not None:
            del frappe.local.message_log[nb_messages:]
        motif = cstr(e) or e.__class__.__name__
        if not isinstance(e, frappe.ValidationError):
            frappe.log_error(frappe.get_traceback(), "Import inscriptions")
        return _resultat(numero, "Rejetée", plan.get("matricule"), nom_affiche, re.sub(r"<[^>]+>", "", motif))

    motif = plan["motif"]
    if res.get("nouveau_matricule"):
        motif = _("Nouvel étudiant — matricule généré : {0}").format(res["matricule"])
    if res.get("ue_ignorees"):
        motif += " — " + res["ue_ignorees"]
    return _resultat(numero, "Importée", res["matricule"], nom_affiche, motif)


def _decouper_fichier(lignes):
    """Repère la ligne d'en-tête et retourne (entêtes, [(n° ligne, {clé: valeur})], ignorées)."""
    lignes = list(lignes or [])
    index_entete = next((i for i, l in enumerate(lignes) if any(cstr(v).strip() for v in (l or []))), None)
    if index_entete is None:
        frappe.throw(_("Le fichier est vide."))

    alias = _alias_colonnes()
    entetes, colonnes_ignorees = [], []
    for valeur in lignes[index_entete]:
        libelle = cstr(valeur).replace("﻿", "").strip()
        cle = alias.get(_cle_entete(libelle))
        entetes.append(cle)
        if libelle and not cle:
            colonnes_ignorees.append(libelle)

    manquantes = [libelle for cle, libelle, obl, _aide in COLONNES if obl and cle not in entetes]
    if manquantes:
        frappe.throw(
            _("Colonnes obligatoires absentes du fichier : {0}. Utilisez le modèle d'importation.").format(
                ", ".join(manquantes)
            )
        )

    donnees = []
    for i, ligne in enumerate(lignes[index_entete + 1:], start=index_entete + 2):
        ligne = list(ligne or [])
        if not any(cstr(v).strip() for v in ligne):
            continue
        donnees.append((i, {cle: ligne[j] if j < len(ligne) else None for j, cle in enumerate(entetes) if cle}))

    if not donnees:
        frappe.throw(_("Le fichier ne contient aucun étudiant."))
    if len(donnees) > MAX_LIGNES_IMPORT:
        frappe.throw(_("Le fichier dépasse {0} lignes : découpez-le en plusieurs fichiers.").format(MAX_LIGNES_IMPORT))
    return entetes, donnees, colonnes_ignorees


def _cle_entete(texte):
    return re.sub(r"[^a-z0-9]+", "_", _normaliser_texte(texte)).strip("_")


def _alias_colonnes():
    alias = {}
    for cle, libelle, _obl, _aide in COLONNES:
        alias[_cle_entete(cle)] = cle
        alias[_cle_entete(libelle)] = cle
    alias.update({
        "prenoms": "prenom",
        "e_mail": "email",
        "adresse_e_mail": "email",
        "adresse_email": "email",
        "courriel": "email",
        "tel": "telephone",
        "classe": "niveau",
        "annee": "annee_academique",
        "genre": "sexe",
        "code_filiere": "filiere",
    })
    return alias


class _ContexteImport:
    """Caches des filières / niveaux / années pour la durée d'un import."""

    def __init__(self):
        self.filieres = {}
        for f in frappe.get_all("Field of study", fields=["name", "name_of_field"]):
            self.filieres[_normaliser_texte(f.name)] = f.name
            if f.name_of_field:
                self.filieres.setdefault(_normaliser_texte(f.name_of_field), f.name)
        self._niveaux = {}
        self._annees = {}

    def filiere(self, valeur):
        return self.filieres.get(_normaliser_texte(valeur))

    def niveaux(self, filiere):
        if filiere not in self._niveaux:
            self._niveaux[filiere] = frappe.get_all(
                "Field of study Level", filters={"parent": filiere}, fields=["name", "level"],
                order_by="order asc, level asc",
            )
        return self._niveaux[filiere]

    def niveau(self, filiere, valeur):
        """Libellé officiel du niveau (même correspondance que _resolve_niveau_grid)."""
        cible = _normaliser_texte(valeur)
        for ligne in self.niveaux(filiere):
            if _normaliser_texte(ligne.level) == cible or cstr(ligne.name) == cstr(valeur).strip():
                return ligne.level
        return None

    def annee_existe(self, annee):
        if annee not in self._annees:
            self._annees[annee] = bool(frappe.db.exists("Academic Year", annee))
        return self._annees[annee]


def _texte(valeur):
    if isinstance(valeur, float) and valeur.is_integer():
        valeur = int(valeur)
    return " ".join(cstr(valeur if valeur is not None else "").split())


def _analyser_ligne(brut, annee_defaut, contexte):
    """Normalise et valide une ligne. Retourne (valeurs, erreurs)."""
    v, erreurs = {}, []
    for cle, _libelle, _obl, _aide in COLONNES:
        if cle != "date_naissance":
            v[cle] = _texte(brut.get(cle))

    v["matricule"] = v["matricule"].upper()
    if v["matricule"] and not _RE_MATRICULE.match(v["matricule"]):
        erreurs.append(_("Matricule invalide « {0} » (lettres, chiffres, / - _ ; 3 à 30 caractères)").format(v["matricule"]))

    for cle, libelle in (("nom", "Nom"), ("prenom", "Prénom"), ("lieu_naissance", "Lieu de naissance")):
        if not v[cle]:
            erreurs.append(_("{0} manquant").format(libelle))

    sexe = _sexe(v["sexe"])
    if not sexe:
        erreurs.append(_("Sexe invalide « {0} » (M ou F)").format(v["sexe"]))
    v["sexe"] = sexe

    v["date_naissance"] = _date(brut.get("date_naissance"))
    if not v["date_naissance"]:
        erreurs.append(_("Date de naissance invalide (format JJ/MM/AAAA)"))
    elif v["date_naissance"] >= date.today():
        erreurs.append(_("Date de naissance dans le futur"))

    email = (validate_email_address(v["email"]) or "").strip().lower() if v["email"] else ""
    if not email:
        erreurs.append(_("E-mail manquant ou invalide « {0} »").format(v["email"]) if v["email"] else _("E-mail manquant"))
    v["email"] = email

    for cle in CHAMPS_TELEPHONE:
        if v.get(cle):
            v[cle] = _telephone_237(v[cle])
    if not v["telephone"]:
        erreurs.append(_("Téléphone manquant"))
    elif len(re.sub(r"\D", "", v["telephone"])) < 8:
        erreurs.append(_("Téléphone invalide « {0} »").format(v["telephone"]))

    filiere = contexte.filiere(v["filiere"]) if v["filiere"] else None
    if not filiere:
        erreurs.append(_("Filière inconnue « {0} »").format(v["filiere"]) if v["filiere"] else _("Filière manquante"))
    else:
        niveau = contexte.niveau(filiere, v["niveau"]) if v["niveau"] else None
        if not niveau:
            valides = ", ".join(n.level for n in contexte.niveaux(filiere) if n.level) or _("aucun niveau configuré")
            erreurs.append(_("Niveau « {0} » inconnu pour la filière {1} (niveaux : {2})").format(v["niveau"], filiere, valides))
        v["niveau"] = niveau
    v["filiere"] = filiere

    v["annee_academique"] = v["annee_academique"] or annee_defaut
    if not v["annee_academique"]:
        erreurs.append(_("Année académique manquante"))
    elif not contexte.annee_existe(v["annee_academique"]):
        erreurs.append(_("Année académique inconnue « {0} »").format(v["annee_academique"]))

    return v, erreurs


def _sexe(valeur):
    cle = _normaliser_texte(valeur)
    if cle in ("m", "masculin", "homme", "h", "male", "garcon"):
        return "Masculin"
    if cle in ("f", "feminin", "femme", "female", "fille"):
        return "Féminin"
    return None


def _date(valeur):
    if valeur in (None, ""):
        return None
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    if isinstance(valeur, (int, float)):  # numéro de série Excel
        try:
            return date(1899, 12, 30) + timedelta(days=int(valeur))
        except (OverflowError, ValueError):
            return None
    texte = cstr(valeur).strip().split(" ")[0]
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(texte, fmt).date()
        except ValueError:
            continue
    return None


def _cle_identite(nom_complet, date_naissance):
    """Identité = noms (ordre indifférent, sans accents) + date de naissance."""
    mots = sorted(_normaliser_texte(nom_complet).replace("-", " ").split())
    return (" ".join(mots), cstr(getdate(date_naissance)) if date_naissance else "")


def _planifier(v, deja_vus, numero):
    """Décide du sort d'une ligne valide : créer, ignorer ou rejeter.

    Retourne {"action", "motif", "student", "matricule"}. Aucune écriture.
    """
    identite = _cle_identite(f"{v['nom']} {v['prenom']}", v["date_naissance"])
    annee = v["annee_academique"]

    # 1. Doublons à l'intérieur du fichier
    for type_cle, valeur, libelle in (
        ("matricule", v["matricule"], _("matricule")),
        ("email", v["email"], _("e-mail")),
        ("identite", identite, _("identité")),
    ):
        if valeur and valeur in deja_vus[type_cle]:
            return _rejet(_("Doublon dans le fichier ({0} identique à la ligne {1})").format(libelle, deja_vus[type_cle][valeur]))
    for type_cle, valeur in (("matricule", v["matricule"]), ("email", v["email"]), ("identite", identite)):
        if valeur:
            deja_vus[type_cle][valeur] = numero

    # 2. Étudiant déjà enregistré ?
    par_matricule = _student_par_matricule(v["matricule"]) if v["matricule"] else None
    par_email = _student_par_email(v["email"])
    par_identite = _students_par_identite(v["nom"], v["prenom"], v["date_naissance"])

    if v["matricule"]:
        insc = _inscription_par_matricule(v["matricule"])
        if insc:
            return _deja_inscrit(insc, annee, v["matricule"])
        if par_matricule:
            autres = {s for s in [par_email] + par_identite if s and s != par_matricule}
            if autres:
                return _rejet(_("Conflit : l'e-mail ou l'identité correspond à l'étudiant {0}, pas au matricule {1}").format(
                    ", ".join(sorted(autres)), v["matricule"]))
            student = par_matricule
        else:
            existants = {s for s in [par_email] + par_identite if s}
            if existants:
                return _rejet(_("Cet étudiant existe déjà avec le matricule {0} (différent de celui du fichier)").format(
                    ", ".join(sorted(_matricule_de(s) for s in existants))))
            student = None
        matricule = v["matricule"]
    else:
        existants = {s for s in [par_email] + par_identite if s}
        if len(existants) > 1:
            return _rejet(_("L'e-mail et l'identité correspondent à des étudiants différents ({0})").format(
                ", ".join(sorted(existants))))
        student = existants.pop() if existants else None
        matricule = _matricule_de(student) if student else None
        if matricule:
            insc = _inscription_par_matricule(matricule)
            if insc:
                return _deja_inscrit(insc, annee, matricule)

    # 3. Inscription déjà présente pour l'année (ex. issue d'une candidature)
    doublon = _inscription_meme_annee(v["email"], identite, annee)
    if doublon:
        return {"action": "ignorer", "matricule": doublon.matricule,
                "motif": _("Inscription déjà existante pour {0} ({1})").format(annee, doublon.matricule or doublon.name)}

    if student:
        motif = _("Étudiant existant ({0}) — inscription {1} créée, matricule conservé").format(matricule, annee)
    elif matricule:
        motif = _("Nouvel étudiant — matricule du fichier conservé")
    else:
        motif = _("Nouvel étudiant — matricule généré à la validation (série {0})").format(LETTRE_HORS_CANDIDATURE)
    return {"action": "creer", "motif": motif, "student": student, "matricule": matricule}


def _rejet(motif):
    return {"action": "rejeter", "motif": motif}


def _deja_inscrit(insc, annee, matricule):
    if insc.annee_academique == annee:
        return {"action": "ignorer", "matricule": matricule,
                "motif": _("Inscription déjà existante pour {0}").format(annee)}
    return {"action": "rejeter", "matricule": matricule,
            "motif": _("Déjà inscrit en {0} : passer par la réinscription pour {1}").format(insc.annee_academique, annee)}


def _student_par_matricule(matricule):
    return frappe.db.get_value("Student", {"matricule": matricule}, "name") if matricule else None


def _student_par_email(email):
    return frappe.db.get_value("Student", {"email": email}, "name") if email else None


def _students_par_identite(nom, prenom, date_naissance):
    if not date_naissance:
        return []
    cible = _cle_identite(f"{nom} {prenom}", date_naissance)
    return [
        s.name
        for s in frappe.get_all(
            "Student", filters={"birth_date": date_naissance}, fields=["name", "nom", "prenom", "birth_date"]
        )
        if _cle_identite(f"{s.nom or ''} {s.prenom or ''}", s.birth_date) == cible
    ]


def _matricule_de(student):
    return frappe.db.get_value("Student", student, "matricule") or student


def _inscription_par_matricule(matricule):
    return frappe.db.get_value(
        "Inscription Academique", {"matricule": matricule}, ["name", "annee_academique"], as_dict=True
    )


def _inscription_meme_annee(email, identite, annee):
    if email:
        insc = frappe.db.get_value(
            "Inscription Academique", {"annee_academique": annee, "email": email},
            ["name", "matricule"], as_dict=True,
        )
        if insc:
            return insc
    if identite[1]:
        for insc in frappe.get_all(
            "Inscription Academique",
            filters={"annee_academique": annee, "date_naissance": identite[1]},
            fields=["name", "matricule", "nom_prenom", "date_naissance"],
        ):
            if _cle_identite(insc.nom_prenom, insc.date_naissance) == identite:
                return insc
    return None


# ====================================================================== #
#  Arrivée en cours d'année (formulaire Inscription Academique)
# ====================================================================== #
@frappe.whitelist(methods=["POST"])
def generer_matricule_et_fiche(inscription):
    """Bouton « Générer le matricule et télécharger la fiche ».

    Au premier appel : matricule (série Z), Student, UE, compte, e-mail.
    Aux appels suivants : rien n'est régénéré, seule l'URL de la fiche est
    renvoyée.
    """
    _verifier_droits_gestion()
    ia = frappe.get_doc("Inscription Academique", inscription)
    ia.check_permission("write")

    if not ia.dossier_origine and not _est_finalisee(ia):
        with _verrou(attente=10):
            try:
                ia.reload()
                if not _est_finalisee(ia):
                    finaliser_inscription_hors_candidature(ia)
                frappe.db.commit()
            except Exception:
                frappe.db.rollback()
                raise

    if not ia.matricule:
        frappe.throw(_("Cette inscription n'a pas encore de matricule."))
    return {"matricule": ia.matricule, "pdf_url": url_fiche(ia.name)}


def url_fiche(nom_inscription):
    return (
        "/api/method/udshed.api.inscription.telecharger_fiche_inscription"
        f"?nom={quote(nom_inscription)}"
    )


def _est_finalisee(ia):
    return bool(ia.matricule and frappe.db.exists("Student", {"matricule": ia.matricule}))


def finaliser_inscription_hors_candidature(ia, nom=None, prenom=None, student=None, envoyer_email=True):
    """Attribue le matricule et crée le dossier étudiant d'une inscription
    hors candidature (formulaire ou import).

    - étudiant déjà enregistré (matricule, e-mail ou identité) : son dossier
      et son matricule sont réutilisés, jamais modifiés ;
    - sinon : matricule de l'inscription s'il est fourni, ou nouveau
      matricule de la série Z, puis création du Student (+ compte utilisateur
      via Student.after_insert) ;
    - inscription aux UE de l'année courante (si pas déjà faite) ;
    - e-mail du matricule (asynchrone, après commit).

    Le contrôle d'accès est fait par l'appelant (rôle + permission sur
    Inscription Academique) ; les documents dérivés (Student, User, Academic
    Reregistration) sont créés comme dans le parcours de candidature.
    """
    if ia.dossier_origine:
        frappe.throw(_("Cette inscription provient d'une candidature : son matricule est attribué par le parcours de candidature."))

    if not (nom and prenom):
        nom, prenom = _scinder_nom(ia.nom_prenom)

    if not student:
        if ia.matricule:
            student = _student_par_matricule(ia.matricule)
        else:
            student = _trouver_student(ia.email, nom, prenom, ia.date_naissance)

    nouveau_matricule = False
    if student:
        s = frappe.db.get_value("Student", student, ["name", "matricule", "email", "nom", "prenom", "utilisateur"], as_dict=True)
        if ia.matricule and ia.matricule != s.matricule:
            frappe.throw(_("Le matricule {0} ne correspond pas à l'étudiant {1} ({2}).").format(ia.matricule, s.name, s.matricule))
        if not ia.matricule:
            autre = frappe.db.get_value(
                "Inscription Academique",
                {"matricule": s.matricule, "name": ["!=", ia.name]},
                ["name", "annee_academique"], as_dict=True,
            )
            if autre:
                frappe.throw(_("L'étudiant {0} est déjà inscrit en {1} ({2}) : utilisez la réinscription.").format(
                    s.matricule, autre.annee_academique, autre.name))
            ia.db_set("matricule", s.matricule)
        if not s.utilisateur:
            _cree_compte_utilisateur(s.name, frappe._dict(email=s.email, first_name=s.nom, last_name=s.prenom))
        student_name = s.name
    else:
        if not ia.matricule:
            ia.db_set("matricule", _generer_matricule_atomique(lettre=LETTRE_HORS_CANDIDATURE))
            nouveau_matricule = True
        student_name = _creer_student(ia, nom, prenom)

    ue_inscrites, ue_ignorees = [], ""
    annee_courante = _annee_academique_courante()
    if ia.annee_academique != annee_courante:
        ue_ignorees = _("UE non inscrites : l'année {0} n'est pas l'année courante").format(ia.annee_academique)
    elif not frappe.db.exists("Academic Reregistration", {"student": student_name, "academic_year": annee_courante}):
        ue_inscrites = _auto_enroll_student_bulk(student_name, ia.filiere, ia.classe)

    if envoyer_email and ia.email:
        _envoyer_email_matricule_async(
            frappe._dict(email=ia.email, full_name=ia.nom_prenom, name=ia.name), ia.matricule, ia.name
        )

    return {
        "matricule": ia.matricule,
        "student": student_name,
        "nouveau_matricule": nouveau_matricule,
        "ue_inscrites": len(ue_inscrites or []),
        "ue_ignorees": ue_ignorees,
    }


def _trouver_student(email, nom, prenom, date_naissance):
    trouves = {s for s in [_student_par_email(email)] + _students_par_identite(nom, prenom, date_naissance) if s}
    if len(trouves) > 1:
        frappe.throw(_("L'e-mail et l'identité correspondent à des étudiants différents ({0}).").format(", ".join(sorted(trouves))))
    return trouves.pop() if trouves else None


def _scinder_nom(nom_prenom):
    """« NOM Prénom(s) » -> (nom, prénoms)."""
    mots = (nom_prenom or "").split()
    if len(mots) < 2:
        frappe.throw(_("Renseignez le nom ET le prénom de l'étudiant (« NOM Prénom »)."))
    return mots[0], " ".join(mots[1:])


def _creer_student(ia, nom, prenom):
    niveau = (ia.classe or "").upper()
    cycle = "BTS" if "BTS" in niveau else "Master" if "MASTER" in niveau else "Licence"
    student = frappe.get_doc({
        "doctype": "Student",
        "matricule": ia.matricule,
        "nom": nom,
        "prenom": prenom,
        "email": ia.email,
        "cycle": cycle,
        "filiere": ia.filiere,
        "sexe": "Femme" if ia.sexe == "Féminin" else "Homme",
        "phone": ia.telephone,
        "birth_date": ia.date_naissance,
        "birth_place": ia.lieu_naissance,
        "niveau_actuel": ia.classe,
        "parent_phone": ia.pere_telephone or ia.telephone_mere or "",
    })
    student.insert(ignore_permissions=True)
    return student.name


# ====================================================================== #
#  Utilitaires
# ====================================================================== #
def _peut_gerer():
    return frappe.session.user == "Administrator" or bool(set(ROLES_GESTION) & set(frappe.get_roles()))


def _verifier_droits_gestion():
    frappe.only_for(ROLES_GESTION)


@contextmanager
def _verrou(attente=10):
    """Sérialise les imports et les générations de matricules hors candidature."""
    lignes = frappe.db.sql("SELECT GET_LOCK(%s, %s)", (VERROU, attente))
    if not lignes or lignes[0][0] != 1:
        frappe.throw(_("Une importation ou une génération de matricules est déjà en cours. Réessayez dans quelques instants."))
    try:
        yield
    finally:
        try:
            frappe.db.sql("SELECT RELEASE_LOCK(%s)", (VERROU,))
        except Exception:
            pass
