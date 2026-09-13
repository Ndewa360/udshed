# -*- coding: utf-8 -*-
import frappe
import unicodedata
from frappe import _
from urllib.parse import urlencode
from udshed.udshed.doctype.session_inscription_candidate.session_inscription_candidate import (
    _auto_enroll_student,
    _cree_compte_utilisateur,
)

@frappe.whitelist(allow_guest=True)
def authentifier_et_inscrire(numero_dossier, nom_candidat):
    """
    Vérifie le dossier de candidature et prépare la deuxième étape du formulaire.
    """

    _verifier_session_ouverte()

    dossier = _get_dossier(numero_dossier, nom_candidat)

    if not dossier:
        frappe.throw("Authentification échouée. Numéro de dossier ou nom incorrect.")

    _verifier_candidature_validee(dossier)

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
    _verifier_session_ouverte()

    dossier = _get_dossier(numero_dossier, nom_candidat)
    if not dossier:
        frappe.throw("Session d'authentification invalide.")

    _verifier_candidature_validee(dossier)

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
        nom_doc = deja_inscrit.name
    else:
        matricule = _generer_matricule()
        nom_doc = None
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
        nom_doc = doc_inscription.name

    _finaliser_student_et_enrollement(dossier, donnees)

    if not dossier.email:
        frappe.logger().warning(
            f"Pas d'email pour {dossier.name} — email matricule non envoyé."
        )
    else:
        try:
            pdf_url = _pdf_url(nom_doc or matricule)

            frappe.sendmail(
                recipients=[dossier.email],
                subject=_("Votre matricule d'inscription - UDSHED"),
                template="inscription_matricule_email",
                args={
                    "matricule": matricule,
                    "nom_prenom": dossier.full_name,
                    "numero_dossier": dossier.name,
                    "pdf_url": frappe.utils.get_url(pdf_url),
                },
                now=True,
            )
            frappe.logger().info(f"Email matricule envoyé à {dossier.email} pour {dossier.name}")
        except Exception as e:
            frappe.log_error(
                message=str(e),
                title=f"Échec envoi e-mail matricule {dossier.name}",
            )

    return {
        "status": "success",
        "matricule": matricule,
        "pdf_url": _pdf_url(nom_doc or matricule),
    }


@frappe.whitelist(allow_guest=True)
def get_grille_enseignement(numero_dossier, nom_candidat):
    """Grille d'enseignement (UE et cours) de la filière du candidat.

    Regroupe les deux semestres de l'année académique courante pour le niveau
    de la candidature, pour affichage avant la validation finale du formulaire.
    """
    _verifier_session_ouverte()

    dossier = _get_dossier(numero_dossier, nom_candidat)
    if not dossier:
        frappe.throw(_("Session d'authentification invalide."))

    _verifier_candidature_validee(dossier)

    session = _session_inscription_active()
    academic_year = session.get("academic_year") if session else _annee_academique_courante()

    filiere = dossier.get("filiere") or ""
    niveau = dossier.get("niveau") or ""

    filiere_doc = None
    faculte = ""
    try:
        filiere_doc = frappe.get_cached_doc("Field of study", filiere)
        faculte = filiere_doc.faculte or ""
    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_grille_enseignement - Field of study")

    semestres = []
    from udshed.api.teaching_grid import _get_academic_teaching_unit_impl

    for semestre in ("Semestre 1", "Semestre 2"):
        try:
            data = _get_academic_teaching_unit_impl(academic_year, faculte, filiere, niveau, semestre)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"get_grille_enseignement - {semestre} ({filiere} {niveau} {academic_year})",
            )
            data = {
                "stats": {"ue_count": 0, "course_count": 0, "total_credits": 0, "total_hours": 0},
                "grid": [],
            }
        if data and data.get("grid"):
            semestres.append({
                "semestre": semestre,
                "stats": data.get("stats"),
                "grid": data.get("grid"),
            })

    return {
        "status": "success",
        "academic_year": academic_year,
        "faculte": faculte,
        "filiere": filiere,
        "filiere_label": (filiere_doc.name_of_field if filiere_doc else "") or filiere,
        "niveau": niveau,
        "semestres": semestres,
    }


def _finaliser_student_et_enrollement(dossier, donnees=None):
    """Crée le Student lié à la candidature finalisée (tolérant les données incomplètes).

    La finalisation doit stocker en BD le dossier complet : le Student (maître),
    l'enrôlement aux Teaching Units et le compte utilisateur. Chaque étape est
    protégée individuellement afin qu'un dossier incomplet ne bloque jamais la
    finalisation de son Inscription Academique et du statut « Inscrit ».
    """
    try:
        if not dossier.get("email"):
            return
        student = frappe.db.get_value("Student", {"email": dossier.get("email")}, "name")
        insc_matricule = frappe.db.get_value(
            "Inscription Academique",
            {"dossier_origine": dossier.get("name")},
            "matricule",
        ) or ""
        if not student:
            cycle = "Master" if "MASTER" in (dossier.get("niveau") or "").upper() else (
                "BTS" if "BTS" in (dossier.get("niveau") or "").upper() else "Licence"
            )
            valeurs = {
                "matricule": insc_matricule,
                "nom": dossier.get("first_name") or "",
                "prenom": dossier.get("last_name") or "",
                "email": dossier.get("email") or "",
                "cycle": cycle,
                "filiere": dossier.get("filiere") or "",
                "sexe": dossier.get("sexe") or "",
                "phone": dossier.get("phone") or "",
                "birth_date": dossier.get("birthdate") or None,
                "birth_place": dossier.get("birth_place") or "",
                "niveau_actuel": dossier.get("niveau") or "",
                "parent_phone": (donnees or {}).get("pere_telephone") or dossier.get("father_phone") or "",
                "email_parent": (donnees or {}).get("email_parent") or dossier.get("email_parent") or "",
                "photo": dossier.get("id_photo") or "",
            }
            student_doc = frappe.get_doc({"doctype": "Student", **valeurs})
            student_doc.insert(ignore_permissions=True)
            student = student_doc.name

        student_doc = frappe.get_doc("Student", student)
        if insc_matricule and (not student_doc.matricule or student_doc.matricule == student_doc.name):
            student_doc.db_set("matricule", insc_matricule)
            student_doc.db_set(
                "nom_complet",
                f"{insc_matricule} - {student_doc.nom or ''} {student_doc.prenom or ''}".strip(),
            )
        candidate = frappe.get_doc("Session Inscription Candidate", dossier.get("name"))
        _cree_compte_utilisateur(student_doc, candidate)
        _auto_enroll_student(student_doc, dossier.get("filiere"), dossier.get("niveau"))
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Échec création Student finalisation {dossier.get('name')}",
        )


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


@frappe.whitelist()
def get_liste_inscriptions(filiere=None):
    """Retourne la liste des candidats dont le statut est « Inscrit » (récap des inscriptions).

    Chaque ligne contient le matricule d'inscription (lié via Inscription Academique),
    le nom, le contact, la filière, le niveau, le centre et la date de soumission.
    """
    filters = {"candidature_status": "Inscrit"}
    if filiere:
        filters["filiere"] = filiere

    candidates = frappe.get_all(
        "Session Inscription Candidate",
        filters=filters,
        fields=[
            "name", "first_name", "last_name", "full_name", "email",
            "phone", "filiere", "niveau", "examination_centre", "creation",
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
    for c in candidates:
        # matricule + année depuis l'Inscription Academique liée au dossier
        insc = frappe.db.get_value(
            "Inscription Academique",
            {"dossier_origine": c.get("name")},
            ["matricule", "annee_academique", "classe"],
            as_dict=True,
        )
        rows.append({
            "name": c.get("name"),
            "nom_complet": c.get("full_name") or (
                f"{c.get('first_name', '')} {c.get('last_name', '')}"
            ).strip(),
            "email": c.get("email") or "",
            "phone": c.get("phone") or "",
            "matricule": (insc.get("matricule") if insc else "") or "",
            "annee_academique": (insc.get("annee_academique") if insc else "") or "",
            "filiere": c.get("filiere") or "",
            "filiere_label": filiere_map.get(c.get("filiere"), c.get("filiere") or "Non défini"),
            "niveau": (insc.get("classe") if insc else None) or c.get("niveau") or "Non défini",
            "examination_centre": c.get("examination_centre") or "Non défini",
            "creation": str(c.get("creation") or ""),
        })

    par_filiere = {}
    par_niveau = {}
    for row in rows:
        par_filiere[row["filiere_label"]] = par_filiere.get(row["filiere_label"], 0) + 1
        par_niveau[row["niveau"]] = par_niveau.get(row["niveau"], 0) + 1

    return {
        "rows": rows,
        "total": len(rows),
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
            "niveau", "birthdate", "birth_place", "phone", "candidature_status",
            "sexe", "father_phone", "email_parent", "id_photo",
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


def _verifier_session_ouverte():
    """Bloque l'inscription s'il n'existe aucune session d'inscription ouverte."""
    session = frappe.db.exists("Session Inscription", {"status": "Open"})
    if not session:
        frappe.throw(
            _("Aucune session d'inscription en cours. Veuillez réessayer plus tard.")
        )


def _verifier_candidature_validee(dossier):
    """Bloque l'inscription si la candidature n'est pas acceptée."""
    statut = (dossier.get("candidature_status") or "").strip() or "En attente"
    if statut != "Accepté":
        frappe.throw(
            _(
                "Votre candidature n'est pas encore validée. Statut actuel : {0}."
                " Vous ne pouvez confirmer votre inscription qu'une fois votre"
                " candidature acceptée."
            ).format(statut)
        )


def _normaliser_texte(valeur):
    texte = " ".join(str(valeur or "").split()).strip().casefold()
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texte)
        if not unicodedata.combining(caractere)
    )


def _pdf_url(matricule):
    params = urlencode({
        "doctype": "Inscription Academique",
        "name": matricule,
        "format": "Fiche d'Inscription",
        "no_letterhead": 1,
    })
    return f"/api/method/frappe.utils.print_format.download_pdf?{params}"


def _generer_matricule():
    """Génère un matricule d'inscription unique.

    Format : {2 chiffres année début}{lettre de session}{numéro séquentiel}
    Exemple : 26B001 (année 2026-2027, 2e session « B », première inscription).

    1. Session active (Session Inscription « Open », sinon la plus récente).
    2. Année = deux derniers chiffres du début de l'année académique de la session.
    3. Lettre = indice alphabétique de la session (A, B, ... Z, AA, ...).
    4. Numéro = max des matricules existants pour ce préfixe + 1 (min 3 chiffres).
    """
    session = _session_inscription_active()
    academic_year = session.get("academic_year") if session else _annee_academique_courante()
    annee = _matricule_annee(academic_year)
    lettre = _lettre_session(session)
    prefix = annee + lettre

    existants = frappe.db.sql(
        "SELECT matricule FROM `tabInscription Academique`"
        " WHERE matricule LIKE %s",
        (prefix + "%",),
    )
    max_numero = 0
    for (matricule,) in existants:
        suffixe = matricule[len(prefix):].lstrip("0") or "0"
        if suffixe.isdigit():
            max_numero = max(max_numero, int(suffixe))

    return prefix + str(max_numero + 1).zfill(3)


def _annee_academique_courante():
    try:
        value = frappe.db.get_single_value("Udshed Setting", "current_year")
        if value:
            return str(value)
    except Exception:
        pass
    return ""


def _session_inscription_active():
    sessions = frappe.get_all(
        "Session Inscription",
        fields=["name", "academic_year", "status", "opening_date", "closing_date"],
        order_by="academic_year asc, opening_date asc",
    )
    if not sessions:
        return None
    for s in sessions:
        if s.get("status") == "Open":
            return s
    return sessions[-1]


def _lettre_session(session):
    if not session:
        return "A"
    sessions = frappe.get_all(
        "Session Inscription",
        fields=["name"],
        order_by="academic_year asc, opening_date asc",
    )
    index = next(
        (i + 1 for i, s in enumerate(sessions) if s.name == session.get("name")),
        1,
    )
    return _indice_en_lettres(index)


def _indice_en_lettres(n):
    """Convertit un indice (1-based) en lettres de colonne : 1->A, 26->Z, 27->AA."""
    libelle = ""
    n = max(int(n or 1), 1)
    while n > 0:
        n, reste = divmod(n - 1, 26)
        libelle = chr(65 + reste) + libelle
    return libelle


def _matricule_annee(academic_year):
    """Renvoie les 2 derniers chiffres du début de l'année académique.

    2026-2027 -> « 26 » ; 2026 -> « 26 » ; valeur vide -> « 00 ».
    """
    texte = str(academic_year or "").strip()
    debut = texte.split("-")[0].strip()
    return debut[-2:].zfill(2)
