# -*- coding: utf-8 -*-
import frappe
import unicodedata
from frappe import _
from frappe.utils import now_datetime, get_url
from contextlib import contextmanager


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
    """Enregistre le formulaire après une authentification réussie (flux Web Form)."""
    _verifier_session_ouverte()

    dossier = _get_dossier(numero_dossier, nom_candidat)
    if not dossier:
        frappe.throw("Session d'authentification invalide.")

    _verifier_candidature_validee(dossier)

    if isinstance(donnees, str):
        donnees = frappe.parse_json(donnees)
    donnees = donnees or {}

    return _finaliser_inscription_complete(dossier, donnees)


@frappe.whitelist(allow_guest=True)
def submit_inscription(doc_name: str, data: str) -> dict:
    """Finalise l'inscription d'un candidat accepté (flux page /inscription)."""
    if not doc_name:
        frappe.throw(_("Numéro de dossier manquant."))

    import json as _json
    if isinstance(data, str):
        data = _json.loads(data)

    doc_name = doc_name.strip().upper()
    candidate = frappe.get_doc("Session Inscription Candidate", doc_name)

    if candidate.candidature_status != "Accepté":
        frappe.throw(_("Seules les candidatures acceptées peuvent finaliser l'inscription."))

    # Préparer les données pour la finalisation unifiée
    donnees = {
        "annee_academique": data.get("annee_academique"),
        "sexe": data.get("sexe"),
        "nationalite": data.get("nationalite"),
        "region_origine": data.get("region_origine"),
        "langue": data.get("langue"),
        "religion": data.get("religion"),
        "situation_matrimoniale": data.get("situation_matrimoniale"),
        "situatio_emploi": data.get("situatio_emploi"),
        "handicape": data.get("handicape"),
        "nom_prenom_pere": data.get("nom_prenom_pere"),
        "pere_telephone": data.get("pere_telephone"),
        "pere_profession": data.get("pere_profession"),
        "pere_ville": data.get("pere_ville"),
        "nom_prenom_mere": data.get("nom_prenom_mere"),
        "telephone_mere": data.get("telephone_mere"),
        "profession_mere": data.get("profession_mere"),
        "mere_ville": data.get("mere_ville"),
        "nom_prenom_sponsor": data.get("nom_prenom_sponsor"),
        "telephone_sponsor": data.get("telephone_sponsor"),
        "profession_sponsor": data.get("profession_sponsor"),
        "sponsor_ville": data.get("sponsor_ville"),
        "dernier_etablissement": data.get("dernier_etablissement"),
        "diplome_entree": data.get("diplome_entree"),
        "matricule_diplome": data.get("matricule_diplome"),
        "activites_sportives": data.get("activites_sportives"),
        "activites_associatives": data.get("activites_associatives"),
        "activites_culturelles": data.get("activites_culturelles"),
        "connaissances_informatiques": data.get("connaissances_informatiques"),
    }

    return _finaliser_inscription_complete(candidate, donnees)


def _finaliser_inscription_complete(dossier, donnees):
    """
    Fonction UNIFIÉE : transaction atomique pour l'inscription complète.
    1. Crée Inscription Academique (avec matricule unique atomique)
    2. Crée/maj Student (matricule, infos)
    3. Auto-enroll aux UE (bulk insert)
    4. Crée compte utilisateur
    5. Met à jour statut candidature = "Inscrit"
    6. Envoie email + retourne URL PDF
    """
    # Vérifier si déjà inscrit (idempotent)
    deja_inscrit = frappe.db.get_value(
        "Inscription Academique",
        {"dossier_origine": dossier.name},
        ["name", "matricule"],
        as_dict=True,
    )
    if deja_inscrit:
        return {
            "status": "success",
            "matricule": deja_inscrit.matricule,
            "pdf_url": _pdf_url(deja_inscrit.name),
            "already_registered": True,
        }

    # Transaction atomique : tout ou rien
    with _transaction_ou_erreur():
        # 1. Générer matricule UNIQUE (atomique avec lock)
        matricule = _generer_matricule_atomique()

        # 2. Créer Inscription Academique
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
        for champ in ("pere_telephone", "telephone_mere", "telephone_sponsor"):
            if champ in valeurs:
                valeurs[champ] = _telephone_237(valeurs[champ])

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
        nom_inscription = doc_inscription.name

        # 3. Créer/mettre à jour Student (une seule opération)
        student = _creer_ou_maj_student(dossier, matricule, donnees)

        # 4. Auto-enroll BULK aux UE (une seule requête groupée)
        enrolled_tus = _auto_enroll_student_bulk(student, dossier.filiere, dossier.niveau)

        # 5. Créer compte utilisateur
        _cree_compte_utilisateur(student, dossier)

        # 6. Mettre à jour candidature -> "Inscrit"
        candidate_doc = frappe.get_doc("Session Inscription Candidate", dossier.name)
        candidate_doc.candidature_status = "Inscrit"
        candidate_doc.status_updated_on = now_datetime()
        candidate_doc.status_comment = f"Inscription finalisée. Matricule: {matricule}"
        candidate_doc.save(ignore_permissions=True)

        # 7. Envoyer email (non bloquant)
        _envoyer_email_matricule_async(dossier, matricule, nom_inscription)

    # Retourner succès (hors transaction pour éviter lock long)
    return {
        "status": "success",
        "matricule": matricule,
        "pdf_url": _pdf_url(nom_inscription),
        "student_name": student.name,
        "enrolled_count": len(enrolled_tus),
    }


def _creer_ou_maj_student(dossier, matricule, donnees):
    """Crée ou met à jour le Student avec le matricule généré. Une seule écriture."""
    student = frappe.db.get_value("Student", {"email": dossier.get("email")}, "name")

    _niveau = (dossier.get("niveau") or "").upper()
    if "BTS" in _niveau:
        cycle = "BTS"
    elif "MASTER" in _niveau:
        cycle = "Master"
    else:
        cycle = "Licence"

    valeurs = {
        "matricule": matricule,
        "nom": dossier.get("first_name") or "",
        "prenom": dossier.get("last_name") or "",
        "email": dossier.get("email") or "",
        "cycle": cycle,
        "filiere": dossier.get("filiere") or "",
        "sexe": dossier.get("sexe") or "",
        "phone": dossier.get("phone") or "",
        "birth_date": dossier.get("birthdate"),
        "birth_place": dossier.get("birth_place") or "",
        "niveau_actuel": dossier.get("niveau") or "",
        "parent_phone": (donnees or {}).get("pere_telephone") or dossier.get("father_phone") or "",
        "email_parent": (donnees or {}).get("email_parent") or dossier.get("email_parent") or "",
        "photo": dossier.get("id_photo") or "",
    }

    if not student:
        student_doc = frappe.get_doc({"doctype": "Student", **valeurs})
        student_doc.insert(ignore_permissions=True)
        return student_doc

    # Mise à jour atomique (db_set unique avec dict)
    student_doc = frappe.get_doc("Student", student)
    student_doc.update(valeurs)
    student_doc.save(ignore_permissions=True)
    return student_doc


def _auto_enroll_student_bulk(student, filiere, niveau):
    """
    Inscription BULK aux UE : une seule requête pour trouver les TU éligibles,
    puis bulk insert dans Academic Reregistration.
    """
    setting = frappe.get_single("Udshed Setting")
    academic_year = getattr(setting, "current_year", None)

    if not academic_year:
        frappe.logger().warning("Aucune année académique courante configurée dans Udshed Setting.")
        return []

    # UNE SEULE requête : récupérer les TU qui matchent filière+niveau via Course Field of study level item
    tus_eligibles = frappe.db.sql("""
        SELECT DISTINCT tu.name
        FROM `tabTeaching Unit` tu
        INNER JOIN `tabCourse Field of study level item` cfsli ON cfsli.parent = tu.name
        WHERE tu.academic_year = %s
          AND cfsli.filiere = %s
          AND cfsli.niveau = %s
    """, (academic_year, filiere, niveau), pluck=True)

    if not tus_eligibles:
        return []

    # Créer Academic Reregistration avec tous les cours en une fois
    reregistration = frappe.get_doc({
        "doctype": "Academic Reregistration",
        "student": student.name,
        "academic_year": academic_year,
        "filiere": student.filiere,
        "semestre": "Les deux",
        "statut": "Validee",
        "cours_inscrits": [
            {"teaching_unit": tu_name, "inscrire": 1, "est_obligatoire": 1}
            for tu_name in tus_eligibles
        ],
    })
    reregistration.insert(ignore_permissions=True)

    return tus_eligibles


def _cree_compte_utilisateur(student, dossier):
	"""Crée le compte utilisateur pour l'étudiant inscrit."""
	email = dossier.email or f"{student.name}@udshed.local"
	if not frappe.db.exists("User", email):
		user = frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": dossier.get("first_name") or "",
			"last_name": dossier.get("last_name") or "",
			"send_welcome_email": 0,
			"roles": [{"role": "Student"}],
		})
		user.insert(ignore_permissions=True)
	frappe.db.set_value("Student", student.name, "utilisateur", email)


def _generer_matricule_atomique():
    """
    Génère un matricule unique de façon ATOMIQUE (avec lock nommé).
    Évite les doublons sous concurrence.
    """
    # Lock nommé pour sérialiser la génération
    lock_key = "matricule_generation_lock"
    acquired = frappe.db.lock(lock_key, timeout=10)
    if not acquired:
        frappe.throw(_("Impossible de générer le matricule (concurrence). Réessayez."))

    try:
        session = _session_inscription_active()
        academic_year = session.get("academic_year") if session else _annee_academique_courante()
        annee = _matricule_annee(academic_year)
        lettre = _lettre_session(session)
        prefix = annee + lettre

        # Recherche du max existant pour ce préfixe
        existants = frappe.db.sql(
            "SELECT matricule FROM `tabInscription Academique` WHERE matricule LIKE %s FOR UPDATE",
            (prefix + "%",),
        )
        max_numero = 0
        for (matricule,) in existants:
            suffixe = matricule[len(prefix):].lstrip("0") or "0"
            if suffixe.isdigit():
                max_numero = max(max_numero, int(suffixe))

        return prefix + str(max_numero + 1).zfill(3)
    finally:
        frappe.db.unlock(lock_key)


@contextmanager
def _transaction_ou_erreur():
    """Context manager : commit si succès, rollback + erreur claire si échec."""
    try:
        yield
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        raise


def _envoyer_email_matricule_async(dossier, matricule, nom_inscription):
    """Envoi email non bloquant (log erreurs seulement)."""
    if not dossier.email:
        frappe.logger().warning(f"Pas d'email pour {dossier.name} — email matricule non envoyé.")
        return

    try:
        pdf_url = _pdf_url(nom_inscription)
        setting = frappe.get_single("Udshed Setting")
        sender = _get_sender()

        frappe.sendmail(
            recipients=[dossier.email],
            sender=sender,
            subject=_("Votre matricule d'inscription - UDSHED"),
            template="inscription_matricule_email",
            args={
                "matricule": matricule,
                "nom_prenom": dossier.full_name,
                "numero_dossier": dossier.name,
                "pdf_url": pdf_url,
            },
            now=True,
        )
        frappe.logger().info(f"Email matricule envoyé à {dossier.email} pour {dossier.name}")
    except Exception as e:
        frappe.log_error(message=str(e), title=f"Échec envoi e-mail matricule {dossier.name}")


# -------------------- Helpers existants (inchangés) --------------------

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
    session = frappe.db.exists("Session Inscription", {"status": "Open"})
    if not session:
        frappe.throw(_("Aucune session d'inscription en cours. Veuillez réessayer plus tard."))


def _verifier_candidature_validee(dossier):
    statut = (dossier.get("candidature_status") or "").strip() or "En attente"
    if statut != "Accepté":
        frappe.throw(
            _("Votre candidature n'est pas encore validée. Statut actuel : {0}. "
              "Vous ne pouvez confirmer votre inscription qu'une fois votre candidature acceptée.").format(statut)
        )


def _normaliser_texte(valeur):
    texte = " ".join(str(valeur or "").split()).strip().casefold()
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texte)
        if not unicodedata.combining(caractere)
    )


def _pdf_url(matricule_ou_nom):
    return (
        "/api/method/frappe.utils.print_format.download_pdf"
        f"?doctype=Inscription Academique&name={matricule_ou_nom}"
        "&format=Fiche Officielle UDM&no_letterhead=1"
    )


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
    libelle = ""
    n = max(int(n or 1), 1)
    while n > 0:
        n, reste = divmod(n - 1, 26)
        libelle = chr(65 + reste) + libelle
    return libelle


def _matricule_annee(academic_year):
    texte = str(academic_year or "").strip()
    debut = texte.split("-")[0].strip()
    return debut[-2:].zfill(2)


def _annee_academique_courante():
    try:
        value = frappe.db.get_single_value("Udshed Setting", "current_year")
        if value:
            return str(value)
    except Exception:
        pass
    return ""


def _get_sender():
    setting = frappe.get_single("Udshed Setting")
    sender_name = getattr(setting, "email_candidature_sender_name", None) or "UDSHED"
    email_account = frappe.db.get_value("Email Account", {"default_outgoing": 1}, "email_id")
    if email_account:
        return f"{sender_name} <{email_account}>"
    return None


@frappe.whitelist()
def get_inscription_report(filiere=None, candidature_status=None):
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


def _telephone_237(valeur):
    """Préfixe l'indicatif pays +237 (Cameroun) aux numéros de téléphone.

    Les champs de type Phone de Frappe refusent un numéro sans code pays
    (InvalidPhoneNumberError). Si le numéro saisi n'est pas précédé de « + »,
    on y ajoute l'indicatif camerounais.
    """
    texte = " ".join(str(valeur or "").split())
    if not texte or texte.startswith("+"):
        return texte
    chiffres = "".join(caractere for caractere in texte if caractere.isdigit())
    return "+237" + chiffres if chiffres else texte