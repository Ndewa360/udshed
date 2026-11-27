# -*- coding: utf-8 -*-
import frappe
import unicodedata
import re
from frappe import _
from frappe.utils import now_datetime, get_url
from contextlib import contextmanager
from udshed.api.candidature import get_school_logo_url
from udshed.utils import campagne, securite

_DUREE_JETON_SEC = 60 * 60  # validité du jeton de connexion formulaire : 1 h

# Anti force brute sur l'authentification « numéro de dossier + nom ».
_MAX_ECHECS_DOSSIER = 5
_MAX_ECHECS_IP = 30
_FENETRE_ECHECS_SEC = 15 * 60


@frappe.whitelist(allow_guest=True)
def authentifier_et_inscrire(numero_dossier, nom_candidat):
    """
    Vérifie le dossier de candidature et prépare la deuxième étape du formulaire.
    Jette une erreur spécifique si le candidat est déjà inscrit.
    """

    cle_dossier = (numero_dossier or "").strip()
    ip = securite.ip_client()
    securite.verifier_tentatives("inscription-dossier", cle_dossier, _MAX_ECHECS_DOSSIER, _FENETRE_ECHECS_SEC)
    securite.verifier_tentatives("inscription-ip", ip, _MAX_ECHECS_IP, _FENETRE_ECHECS_SEC)

    dossier = _get_dossier(numero_dossier, nom_candidat)

    if not dossier:
        securite.enregistrer_echec("inscription-dossier", cle_dossier, _FENETRE_ECHECS_SEC)
        securite.enregistrer_echec("inscription-ip", ip, _FENETRE_ECHECS_SEC)
        frappe.throw("Authentification échouée. Numéro de dossier ou nom incorrect.")

    securite.reinitialiser_tentatives("inscription-dossier", cle_dossier)
    campagne.exiger_inscription_ouverte(dossier)

    # Nouveau : vérifier si le candidat est déjà inscrit
    deja_inscrit = frappe.db.exists(
        "Inscription Academique",
        {"dossier_origine": dossier.name},
    )
    if deja_inscrit:
        frappe.throw("Le candidat est déjà inscrit.")

    _verifier_candidature_validee(dossier)

    infos = _infos_candidat(dossier)
    # Inclusion de la date de naissance pour affichage à la place du nom
    infos["date_naissance"] = dossier.birthdate or ""
    # Jeton signé : évite une re-vérification complète au chargement du formulaire
    infos["token"] = _creer_jeton(dossier.name, nom_candidat)
    return infos


@frappe.whitelist(allow_guest=True)
def get_candidat_infos(numero_dossier, nom_candidat, token=None):
    """Version allégée pour le chargement du formulaire d'inscription.

    Vérifie le jeton signé émis par `authentifier_et_inscrire` (pas de
    re-vérification complète de la session) et retourne les infos du candidat.
    """
    if not _verifier_jeton(token, numero_dossier, nom_candidat):
        frappe.throw(_("Session d'authentification expirée. Veuillez recommencer."))

    dossier = _get_dossier(numero_dossier, nom_candidat)
    if not dossier:
        frappe.throw(_("Session d'authentification invalide."))

    _verifier_candidature_validee(dossier)
    return _infos_candidat(dossier)


@frappe.whitelist(allow_guest=True)
def get_grille_enseignement(numero_dossier, nom_candidat, token=None):
    """Retourne la grille d'enseignement (UE) de la filière/niveau du candidat.

    Servie avant la soumission : le candidat vérifie et confirme sa grille.
    La liste reprend exactement les UE qui seront auto-inscrites
    (même requête que _auto_enroll_student_bulk).
    """
    if not _verifier_jeton(token, numero_dossier, nom_candidat):
        frappe.throw(_("Session d'authentification expirée. Veuillez recommencer."))

    dossier = _get_dossier(numero_dossier, nom_candidat)
    if not dossier:
        frappe.throw(_("Session d'authentification invalide."))

    _verifier_candidature_validee(dossier)

    niveau_grid = _resolve_niveau_grid(dossier.filiere, dossier.niveau)
    if not niveau_grid:
        return {
            "status": "ok",
            "filiere": dossier.filiere,
            "filiere_label": dossier.filiere,
            "niveau": dossier.niveau or "",
            "academic_year": campagne.annee_cible(dossier),
            "cours": [],
            "total_credits": 0,
        }

    academic_year = campagne.annee_cible(dossier)
    lignes = frappe.db.sql(
        """
        SELECT tu.name, tu.intitule_cours, tu.semestre,
               tu.credits AS tu_credits, MAX(cfsli.course_poid) AS course_poid
        FROM `tabTeaching Unit` tu
        INNER JOIN `tabCourse Field of study level item` cfsli
            ON cfsli.parent = tu.name
        WHERE tu.academic_year = %s
          AND cfsli.filiere = %s
          AND cfsli.niveau = %s
        GROUP BY tu.name, tu.intitule_cours, tu.semestre, tu.credits
        ORDER BY tu.semestre, MAX(cfsli.course_poid) DESC, tu.intitule_cours
        """,
        (academic_year, dossier.filiere, niveau_grid),
        as_dict=True,
    )

    cours = []
    for ligne in lignes or []:
        credits = ligne.get("course_poid") or ligne.get("tu_credits") or 0
        cours.append({
            "teaching_unit": ligne.get("name"),
            "intitule": ligne.get("intitule_cours") or ligne.get("name"),
            "semestre": ligne.get("semestre") or "",
            "credits": float(credits) or 0,
        })

    filiere_label = (
        frappe.db.get_value("Field of study", dossier.filiere, "name_of_field")
        or dossier.filiere
    )

    return {
        "status": "ok",
        "filiere": dossier.filiere,
        "filiere_label": filiere_label,
        "niveau": dossier.niveau or "",
        "academic_year": academic_year or "",
        "cours": cours,
        "total_credits": sum(c["credits"] for c in cours),
    }


def _construire_grille_depuis_doc(doc):
    """Retourne le HTML de la grille d'enseignement groupée par semestre,
    réutilisant la même logique que get_grille_enseignement mais directement
    depuis le doc Inscription Academique."""
    import re

    academic_year = doc.annee_academique or _annee_academique_courante()
    if not academic_year:
        return "", "", 0

    niveau_grid = _resolve_niveau_grid(doc.filiere, doc.niveau) or ""

    lignes = frappe.db.sql(
        """
        SELECT tu.name, tu.intitule_cours, tu.semestre,
               tu.credits AS tu_credits, MAX(cfsli.course_poid) AS course_poid
        FROM `tabTeaching Unit` tu
        INNER JOIN `tabCourse Field of study level item` cfsli
            ON cfsli.parent = tu.name
        WHERE tu.academic_year = %s
          AND cfsli.filiere = %s
          AND cfsli.niveau = %s
        GROUP BY tu.name, tu.intitule_cours, tu.semestre, tu.credits
        ORDER BY tu.semestre, MAX(cfsli.course_poid) DESC, tu.intitule_cours
        """,
        (academic_year, doc.filiere, niveau_grid),
        as_dict=True,
    )

    s1 = []
    s2 = []
    for ligne in lignes or []:
        credits = ligne.get("course_poid") or ligne.get("tu_credits") or 0
        c = {
            "intitule": ligne.get("intitule_cours") or ligne.get("name") or "—",
            "credits": float(credits) or 0,
        }
        sem = str(ligne.get("semestre") or "").lower()
        if any(kw in sem for kw in ["2", "second", "deux", "s2"]):
            s2.append(c)
        else:
            s1.append(c)

    def _html_table(cours_list):
        if not cours_list:
            return "<tr><td colspan='3' class='text-muted' style='font-style: italic;'>Aucune unité d'enseignement pour ce semestre.</td></tr>"
        rows = []
        total = 0
        for i, c in enumerate(cours_list, 1):
            total += c["credits"]
            rows.append(
                "<tr>"
                "<td>" + str(i) + "</td>"
                "<td>" + frappe.utils.escape_html(c["intitule"]) + "</td>"
                "<td class='text-right'>" + str(c["credits"]) + "</td>"
                "</tr>"
            )
        return (
            "<tbody>"
            + "".join(rows)
            + "<tfoot>"
            "<tr>"
            "<td colspan='2' class='text-right'><strong>Sous-total</strong></td>"
            "<td class='text-right'><strong>" + str(total) + "</strong></td>"
            "</tr>"
            "</tfoot>"
            + "</tbody>"
        )

    s1_html = (
        "<h6 class='grille-sous-titre'>Premier semestre</h6>"
        "<div class='table-responsive'>"
        "<table class='table grille-table'>"
        "<thead>"
        "<tr>"
        "<th style='width: 40px;'>#</th>"
        "<th>Enseignement / Unité d'enseignement</th>"
        "<th class='text-right' style='width: 90px;'>Crédits</th>"
        "</tr>"
        "</thead>"
        + _html_table(s1)
        + "</table>"
        + "</div>"
    )

    s2_html = (
        "<h6 class='grille-sous-titre mt-3'>Deuxième semestre</h6>"
        "<div class='table-responsive'>"
        "<table class='table grille-table'>"
        "<thead>"
        "<tr>"
        "<th style='width: 40px;'>#</th>"
        "<th>Enseignement / Unité d'enseignement</th>"
        "<th class='text-right' style='width: 90px;'>Crédits</th>"
        "</tr>"
        "</thead>"
        + _html_table(s2)
        + "</table>"
        + "</div>"
    )

    total_credits = sum(c["credits"] for c in (s1 + s2))
    return s1_html, s2_html, total_credits


def _infos_candidat(dossier):
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
        "annee_academique": campagne.annee_cible(dossier),
        "finaliser_avant": frappe.utils.format_date(dossier.get("finaliser_avant")) if dossier.get("finaliser_avant") else "",
    }


def _resolve_niveau_grid(filiere, niveau_label):
    """Résout un niveau (label, ex. 'Licence 1') vers le `name` de la ligne de
    niveau utilisé dans `Course Field of study level item.niveau`.

    Le dossier candidat stocke le label (ex. « Licence 1 ») tandis que la grille
    pédagogique référence la ligne du Field of study par son `name` (ex. « 1 »).
    """
    niveau_label = (niveau_label or "").strip()
    if not filiere or not niveau_label:
        return None
    try:
        doc = frappe.get_doc("Field of study", filiere)
    except frappe.DoesNotExistError:
        return None
    lignes = doc.get("field_of_study_level") or []
    cible = _normaliser_texte(niveau_label)
    for ligne in lignes:
        if _normaliser_texte(ligne.get("level") or "") == cible:
            return str(ligne.get("name"))
        if str(ligne.get("name")) == niveau_label:
            return str(ligne.get("name"))
    return None


def _parties_jeton(numero_dossier, nom_candidat):
    # Normalisation : le numéro saisi (casse, espaces) et le nom (accents,
    # casse) doivent produire le même jeton à la création et à la vérification.
    return (str(numero_dossier or "").strip().upper(), _normaliser_texte(nom_candidat))


def _creer_jeton(numero_dossier, nom_candidat):
    """Jeton signé (clé du site) valable _DUREE_JETON_SEC pour ce dossier."""
    expiration = int(now_datetime().timestamp()) + _DUREE_JETON_SEC
    signature = securite.signer("inscription", *_parties_jeton(numero_dossier, nom_candidat), expiration)
    return f"{expiration}.{signature}"


def _verifier_jeton(jeton, numero_dossier, nom_candidat):
    if not jeton:
        return False
    try:
        expiration, signature = str(jeton).split(".", 1)
        expiration = int(expiration)
    except ValueError:
        return False
    if int(now_datetime().timestamp()) > expiration:
        return False
    return securite.verifier_signature(
        signature, "inscription", *_parties_jeton(numero_dossier, nom_candidat), expiration
    )


@frappe.whitelist(allow_guest=True)
def enregistrer_inscription(numero_dossier, nom_candidat, donnees=None, token=None):
    """Enregistre le formulaire après une authentification réussie (flux Web Form).

    Exige le jeton signé émis par `authentifier_et_inscrire` : sans lui,
    n'importe qui connaissant un numéro de dossier et un nom pourrait
    finaliser l'inscription d'un autre candidat.
    """
    if not _verifier_jeton(token, numero_dossier, nom_candidat):
        frappe.throw(_("Session d'authentification expirée. Veuillez recommencer."))

    dossier = _get_dossier(numero_dossier, nom_candidat)
    if not dossier:
        frappe.throw(_("Session d'authentification invalide."))
    campagne.exiger_inscription_ouverte(dossier)

    _verifier_candidature_validee(dossier)

    if isinstance(donnees, str):
        donnees = frappe.parse_json(donnees)
    donnees = donnees or {}

    return _finaliser_inscription_complete(dossier, donnees)


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
            "pdf_url": _pdf_url(deja_inscrit.matricule),
            "already_registered": True,
        }

    # Une admission non confirmée dans le délai n'ouvre plus droit au matricule.
    from udshed.api.concours_finalisation import verifier_delai

    verifier_delai(dossier)

    # Transaction atomique : tout ou rien
    annee = campagne.annee_cible(dossier)
    if not annee:
        frappe.throw(_("Aucune année de rentrée n'est définie pour la campagne de ce dossier."))

    with _transaction_ou_erreur():
        # 1. Générer matricule UNIQUE (atomique avec lock), série de la campagne
        matricule = _generer_matricule_atomique(
            academic_year=annee, session_name=dossier.get("session_inscription"), filiere=dossier.filiere
        )

        # 2. Créer Inscription Academique
        # L'année n'est jamais saisie par le candidat : c'est celle de sa campagne.
        champs_autorises = {
            "sexe", "nationalite", "region_origine", "langue",
            "religion", "handicape", "situation_matrimoniale", "situatio_emploi",
            "nom_prenom_pere", "pere_telephone", "pere_profession", "pere_ville",
            "nom_prenom_mere", "telephone_mere", "profession_mere", "mere_ville",
            "nom_prenom_sponsor", "telephone_sponsor", "profession_sponsor", "sponsor_ville",
            "dernier_etablissement", "diplome_entree", "matricule_diplome",
            "activites_sportives", "activites_associatives", "activites_culturelles",
            "connaissances_informatiques",
        }
        valeurs = {champ: donnees.get(champ) for champ in champs_autorises if donnees.get(champ) is not None}
        if not valeurs.get("sexe"):
            valeurs["sexe"] = {"Homme": "Masculin", "Femme": "Féminin"}.get(dossier.get("sexe") or "", "")
        for champ in ("pere_telephone", "telephone_mere", "telephone_sponsor"):
            if champ in valeurs:
                valeurs[champ] = _telephone_237(valeurs[champ])

        doc_inscription = frappe.get_doc({
            "doctype": "Inscription Academique",
            "annee_academique": annee,
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
        student_name, est_nouveau = _creer_ou_maj_student(dossier, matricule, donnees)

        # 4. Auto-enroll BULK aux UE (une seule requête groupée)
        enrolled_tus = _auto_enroll_student_bulk(
            student_name, dossier.filiere, dossier.niveau, academic_year=annee
        )
        if not enrolled_tus:
            _alerter_inscription_sans_ue(nom_inscription, matricule, dossier, annee)

        # 5. Compte utilisateur : déjà créé par Student.after_insert si nouveau
        if not est_nouveau:
            _cree_compte_utilisateur(student_name, dossier)

        # 6. Candidature -> "Inscrit" (mise à jour directe, pas de rechargement doc)
        frappe.db.set_value(
            "Session Inscription Candidate",
            dossier.name,
            {
                "candidature_status": "Inscrit",
                "status_updated_on": now_datetime(),
                "status_comment": f"Inscription finalisée. Matricule: {matricule}",
            },
        )

        # 7. Envoyer email (non bloquant)
        _envoyer_email_matricule_async(dossier, matricule, nom_inscription)

    # Retourner succès (hors transaction pour éviter lock long)
    return {
        "status": "success",
        "matricule": matricule,
        "pdf_url": _pdf_url(matricule),
        "student_name": student_name,
        "enrolled_count": len(enrolled_tus),
        "annee_academique": annee,
    }


def _alerter_inscription_sans_ue(inscription, matricule, dossier, annee):
    """Aucune UE trouvée pour la classe sur l'année de rentrée (grille pas
    encore saisie) : l'inscription est enregistrée, la scolarité est prévenue
    pour affecter les UE une fois la grille saisie."""
    message = _(
        "Inscription {0} (matricule {1}) : aucune UE n'existe encore pour {2} {3} en {4}. "
        "Affectez les UE à cet étudiant une fois la grille saisie."
    ).format(inscription, matricule, dossier.filiere, dossier.niveau, annee)
    frappe.get_doc("Inscription Academique", inscription).add_comment("Comment", message)
    destinataires = set()
    for role in ("Registration Manager", "Agent de scolarité"):
        destinataires.update(
            frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
        )
    from udshed.notifications import emettre

    emettre("inscription_sans_ue", sorted(destinataires), _("Inscription sans UE : {0}").format(matricule), message,
            reference=("Inscription Academique", inscription), cle=f"sans-ue:{inscription}")


def _creer_ou_maj_student(dossier, matricule, donnees):
    """Crée ou met à jour le Student avec le matricule généré.

    Retourne (name, est_nouveau). La mise à jour passe par db.set_value
    (évite un rechargement complet + pipeline de save).
    """
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
        return student_doc.name, True

    # Mise à jour directe (set_value) : évite un rechargement complet du doc
    # et le pipeline de save. Nom complet et cycle sont recalculés côté lecture.
    frappe.db.set_value("Student", student, valeurs)
    return student, False


def _auto_enroll_student_bulk(student_name, filiere, niveau, academic_year=None):
    """
    Inscription BULK aux UE : une seule requête pour trouver les TU éligibles,
    puis bulk insert dans Academic Reregistration.

    Le pipeline validate() d'Academic Reregistration est conçu pour le portail
    de réinscription (session ouverte, année suivante, admission, crédits) et
    rejette une première inscription : il est donc ignoré ici. Les champs utiles
    (session de réinscription courante, niveau, nom, email) sont renseignés et
    les UE inscrites sont explicitement fournies.
    """
    academic_year = academic_year or _annee_academique_courante()
    if not academic_year:
        frappe.logger().warning("Aucune année académique pour l'inscription aux UE.")
        return []

    niveau_grid = _resolve_niveau_grid(filiere, niveau)
    if not niveau_grid:
        frappe.logger().warning(
            f"Aucun niveau de grille trouvé pour filière '{filiere}' et niveau '{niveau}'."
        )
        return []

    # UNE SEULE requête : récupérer les TU qui matchent filière+niveau via Course Field of study level item
    tus_eligibles = frappe.db.sql("""
        SELECT DISTINCT tu.name
        FROM `tabTeaching Unit` tu
        INNER JOIN `tabCourse Field of study level item` cfsli ON cfsli.parent = tu.name
        WHERE tu.academic_year = %s
          AND cfsli.filiere = %s
          AND cfsli.niveau = %s
    """, (academic_year, filiere, niveau_grid), pluck=True)

    if not tus_eligibles:
        return []

    session_reinscription = frappe.get_value(
        "Session Reinscription",
        {"statut": "Ouverte", "academic_year": academic_year},
        "name",
    )

    # Créer Academic Reregistration avec tous les cours en une fois
    reregistration = frappe.get_doc({
        "doctype": "Academic Reregistration",
        "student": student_name,
        "reinscription_session": session_reinscription,
        "academic_year": academic_year,
        "filiere": filiere,
        "niveau": niveau,
        "semestre": "Les deux",
        "statut": "Validée",
        "cours_inscrits": [
            {"teaching_unit": tu_name, "inscrire": 1, "est_obligatoire": 1}
            for tu_name in tus_eligibles
        ],
    })
    reregistration.flags.ignore_validate = True
    reregistration.flags.ignore_mandatory = True
    reregistration.insert(ignore_permissions=True)

    return tus_eligibles


def _cree_compte_utilisateur(student_name, dossier=None):
	"""Crée ou complète le compte Frappe de l'étudiant (identifiant = matricule)."""
	from udshed.utils.compte_etudiant import assurer_compte

	return assurer_compte(student_name)


def _generer_matricule_atomique(lettre=None, academic_year=None, session_name=None, filiere=None):
    """Matricule unique selon le format des réglages (udshed.utils.matricule), sous verrou SQL.

    `lettre` force la lettre ; sinon la règle des réglages s'applique (suite des campagnes,
    lettre fixe ou lettre de la filière). Même règle pour les admissions et les imports.
    """
    from udshed.utils import matricule

    annee = academic_year or _annee_academique_courante()
    if not annee:
        frappe.throw(_("Aucune année académique n'est définie pour générer le matricule."))
    return matricule.generer(annee, session_name=session_name, filiere=filiere, lettre_forcee=lettre)


def _max_numero_matricule(doctype, prefix):
    """Plus grand numéro déjà attribué derrière `prefix` dans `doctype`."""
    row = frappe.db.sql(
        f"""
        SELECT MAX(CAST(SUBSTRING(matricule, %s) AS UNSIGNED))
        FROM `tab{doctype}`
        WHERE matricule LIKE %s
          AND SUBSTRING(matricule, %s) REGEXP '^[0-9]+$'
        """,
        (len(prefix) + 1, prefix + "%", len(prefix) + 1),
    )
    return int((row[0][0] if row and row[0] else 0) or 0)


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
    """Envoi email réellement asynchrone : job RQ planifié après le commit.

    Le SMTP (potentiellement lent) n'est plus exécuté dans la requête HTTP /
    la transaction : il repart sur le worker en arrière-plan.
    """
    if not dossier.email:
        frappe.logger().warning(f"Pas d'email pour {dossier.name} — email matricule non envoyé.")
        return

    try:
        frappe.enqueue(
            "udshed.api.inscription._envoyer_email_matricule",
            email=dossier.email,
            nom_prenom=dossier.full_name,
            numero_dossier=dossier.name,
            matricule=matricule,
            nom_inscription=nom_inscription,
            base_url=frappe.utils.get_url(),
            queue="default",
            enqueue_after_commit=True,
        )
    except Exception as e:
        frappe.log_error(message=str(e), title=f"Échec planification e-mail matricule {dossier.name}")


def _envoyer_email_matricule(email, nom_prenom, numero_dossier, matricule, nom_inscription, base_url=None):
    """Envoie l'email du matricule (exécuté par le worker RQ)."""
    try:
        pdf_url = _pdf_url(matricule)
        sender = _get_sender()

        from udshed.utils.compte_etudiant import lien_activation
        from udshed.utils.etablissement import etablissement

        etab = etablissement()
        student = frappe.db.get_value("Student", {"matricule": matricule}, ["name", "utilisateur"], as_dict=True)
        from udshed.notifications import emettre

        emettre(
            "compte_etudiant_cree",
            [email],
            _("Votre matricule et votre compte étudiant - {0}").format(etab.nom),
            sender=sender,
            template="inscription_matricule_email",
            args={
                "matricule": matricule,
                "nom_prenom": nom_prenom,
                "numero_dossier": numero_dossier,
                "pdf_url": pdf_url,
                "base_url": base_url or frappe.utils.get_url(),
                "lien_activation": lien_activation(student.utilisateur) if student else "",
                "lien_connexion": frappe.utils.get_url("/login"),
            },
            now=True,
        )
        frappe.logger().info(f"Email matricule envoyé à {email} pour {numero_dossier}")
    except Exception as e:
        frappe.log_error(message=str(e), title=f"Échec envoi e-mail matricule {numero_dossier}")


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
            "sexe", "father_phone", "email_parent", "id_photo", "finaliser_avant",
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


def _verifier_candidature_validee(dossier):
    statut = (dossier.get("candidature_status") or "").strip() or "En attente"
    if statut != "Accepté":
        frappe.throw(
            _("Votre candidature n'est pas encore validée. Statut actuel : {0}. "
              "Vous ne pouvez confirmer votre inscription qu'une fois votre candidature acceptée.").format(statut)
        )
    from udshed.api.concours_finalisation import verifier_delai

    verifier_delai(dossier)


def _normaliser_texte(valeur):
    texte = " ".join(str(valeur or "").split()).strip().casefold()
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texte)
        if not unicodedata.combining(caractere)
    )


def jeton_fiche_inscription(matricule):
    """Jeton permanent autorisant le téléchargement de la fiche de `matricule`.

    Remis uniquement au candidat (réponse après inscription, email matricule).
    """
    return securite.signer("fiche-inscription", matricule)


def _pdf_url(matricule):
    from urllib.parse import quote

    return (
        "/api/method/udshed.api.inscription.telecharger_fiche_inscription"
        f"?matricule={quote(str(matricule))}&jeton={jeton_fiche_inscription(matricule)}"
    )


def _verifier_acces_fiche_inscription(doc, jeton):
    """Personnel habilité (permission sur le document) ou détenteur du jeton signé."""
    if frappe.session.user != "Guest" and frappe.has_permission(
        "Inscription Academique", "read", doc=doc
    ):
        return
    if doc.matricule and securite.verifier_signature(jeton, "fiche-inscription", doc.matricule):
        return
    frappe.throw(_("Lien de téléchargement invalide."), frappe.PermissionError)


@frappe.whitelist(allow_guest=True)
def telecharger_fiche_inscription(matricule=None, nom=None, jeton=None):
    """Génère la fiche d'inscription officielle (PDF) d'un Inscription Academique.

    Rendu via weasyprint directement sur le corps HTML du Print Format
    « Fiche Inscription » : aucune dépendance à wkhtmltopdf/chrome ni au
    champ « pdf_generator » du Print Format. Le logo en filigrane est
    embarqué en data-URI (aucune URL réseau requise côté rendu).

    Le document est résolu par « matricule » (préféré) ou par « nom »
    (identifiant interne du doc). Le nom du fichier téléchargé reprend le
    matricule affiché dans la fiche et à l'écran (doc.matricule).
    """
    if not matricule and not nom:
        frappe.throw(_("Matricule manquant."))

    if nom:
        try:
            doc = frappe.get_doc("Inscription Academique", nom)
        except frappe.DoesNotExistError:
            doc = None
    else:
        doc = None

    if not doc:
        doc = frappe.get_all(
            "Inscription Academique",
            filters={"matricule": matricule},
            limit=1,
            ignore_permissions=True,
        )
        if not doc:
            frappe.throw(_("Aucune inscription académique trouvée avec ce matricule."))
        doc = frappe.get_doc("Inscription Academique", doc[0].name)

    _verifier_acces_fiche_inscription(doc, jeton)

    pf = frappe.get_doc("Print Format", "Fiche Inscription")

    logo = ""
    try:
        from udshed.api.school_setting import get_school_logo
        _logo = get_school_logo() or "/assets/udshed/images/logo1.png"
        if _logo.startswith("/"):
            _logo = frappe.utils.get_url(_logo)
        logo = _logo
    except Exception:
        logo = ""

    html = frappe.render_template(pf.html, {"doc": doc, "logo": logo})

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "telecharger_fiche_inscription")
        frappe.throw(_("La génération de la fiche a échoué. Veuillez réessayer."))

    identifiant = (doc.matricule or doc.name).replace("/", "-")
    frappe.response["filename"] = f"Fiche-Inscription-{identifiant}.pdf"
    frappe.response["filecontent"] = pdf_bytes
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/pdf; charset=utf-8"


def _session_et_lettre(session_name=None):
    """Retourne (session, lettre) avec UNE SEULE requête sur Session Inscription.

    La session est la session « Open », sinon la plus récente ; la lettre est
    son index alphabétique (A, B, C…) dans la liste ordonnée des sessions.
    """
    sessions = frappe.get_all(
        "Session Inscription",
        fields=["name", "academic_year", "status", "opening_date", "closing_date"],
        order_by="academic_year asc, opening_date asc",
    )
    if not sessions:
        return None, "A"
    active = (
        next((s for s in sessions if s.name == session_name), None)
        or next((s for s in sessions if s.get("status") == "Open"), None)
        or sessions[-1]
    )
    index = next(
        (i + 1 for i, s in enumerate(sessions) if s.name == active.get("name")),
        1,
    )
    return active, _indice_en_lettres(index)


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


# -------------------- Fiche d'inscription (Print Format « Fiche Inscription ») --------------------

def _info_etablissement():
    """Coordonnées de l'établissement (Udshed Setting) pour les impressions."""
    st = frappe.get_single("Udshed Setting")
    champ = lambda cle: str(st.get(cle) or "").strip()  # noqa: E731
    return {
        "school_name": champ("school_name"),
        "school_institute": champ("school_institute"),
        "school_address": champ("school_address"),
        "school_phone": champ("school_phone"),
        "school_email": champ("school_email"),
        "school_website": champ("school_website"),
    }


def _chiffres_niveau(label):
    """'Licence 3' -> '3', 'BTS 1' -> '1'."""
    m = re.search(r"(\d+)", str(label or ""))
    return m.group(1) if m else ""


def _rang_niveau(filiere, niveau_label, niveau_grid):
    """Numéro d'année du niveau (1, 2, 3…) via la ligne du Field of study."""
    try:
        doc = frappe.get_doc("Field of study", filiere)
        for ligne in doc.get("field_of_study_level") or []:
            if str(ligne.get("name")) == str(niveau_grid):
                if ligne.get("order"):
                    try:
                        return int(ligne.get("order"))
                    except (TypeError, ValueError):
                        pass
                break
    except frappe.DoesNotExistError:
        pass
    rang = _chiffres_niveau(niveau_label)
    try:
        return int(rang) or 1
    except (TypeError, ValueError):
        return 1


def _indice_semestre(sem):
    """'Semestre 2'/'S2' -> 2, sinon -> 1 (« Les deux » rangé au premier)."""
    s = unicodedata.normalize("NFKD", str(sem or "")).lower()
    if "les deux" in s:
        return 1
    if re.search(r"(^|[^0-9])2([^0-9]|$)", s) or "second" in s or "deuxi" in s:
        return 2
    return 1


def _grille_enseignement_fiche(doc):
    """Grille d'enseignement d'un Inscription Academique (même requête que le
    chargement de la grille : Teaching Unit × Course Field of study level item).

    Semestres numérotés globalement comme sur le modèle papier :
    Licence 1 -> SEMESTRE 1 / 2, Licence 2 -> SEMESTRE 3 / 4, Licence 3 -> 5 / 6…

    Retourne (grille, total_credits).
    """
    filiere = (doc.get("filiere") or "").strip()
    niveau_label = (doc.get("classe") or "").strip()
    academic_year = (doc.get("annee_academique") or "").strip()

    niveau_grid = _resolve_niveau_grid(filiere, niveau_label)
    if not niveau_grid:
        return [], 0

    lignes = frappe.db.sql(
        """
        SELECT tu.name, tu.intitule_cours, tu.semestre,
               tu.credits AS tu_credits, MAX(cfsli.course_poid) AS course_poid
        FROM `tabTeaching Unit` tu
        INNER JOIN `tabCourse Field of study level item` cfsli
            ON cfsli.parent = tu.name
        WHERE tu.academic_year = %s
          AND cfsli.filiere = %s
          AND cfsli.niveau = %s
        GROUP BY tu.name, tu.intitule_cours, tu.semestre, tu.credits
        ORDER BY tu.semestre, MAX(cfsli.course_poid) DESC, tu.intitule_cours
        """,
        (academic_year, filiere, niveau_grid),
        as_dict=True,
    )

    rang = _rang_niveau(filiere, niveau_label, niveau_grid)
    total_credits = 0
    semestres = {}
    for ligne in lignes or []:
        credits = float(ligne.get("course_poid") or ligne.get("tu_credits") or 0)
        num = (rang - 1) * 2 + _indice_semestre(ligne.get("semestre"))
        semestres.setdefault(num, []).append({
            "code": ligne.get("name"),
            "intitule": ligne.get("intitule_cours") or ligne.get("name"),
            "credits": credits,
        })
        total_credits += credits

    grille = [
        {
            "label": "SEMESTRE {0}".format(num),
            "rows": semestres[num],
            "total": sum(r["credits"] for r in semestres[num]),
        }
        for num in sorted(semestres)
    ]
    return grille, total_credits


def donnees_fiche_inscription(doc):
    """Données dynamiques du Print Format « Fiche Inscription ».

    Regroupe les coordonnées de l'établissement (config), l'en-tête
    (département = Field of study, matricule, n° de dossier) et la grille
    d'enseignement du candidat, prêtes à être rendues par le template Jinja.
    """
    filiere = (doc.get("filiere") or "").strip()
    niveau_label = (doc.get("classe") or "").strip()
    departement = frappe.db.get_value("Field of study", filiere, "name_of_field") or filiere

    grille, total_credits = _grille_enseignement_fiche(doc)

    return {
        "etablissement": _info_etablissement(),
        "departement": departement,
        "classe_tag": (filiere + _chiffres_niveau(niveau_label)).upper(),
        "matricule": (doc.get("matricule") or "").strip(),
        "numero_dossier": (doc.get("dossier_origine") or "").strip(),
        "annee_academique": (doc.get("annee_academique") or "").strip(),
        "grille": grille,
        "total_credits": total_credits,
    }


def _get_sender():
    setting = frappe.get_single("Udshed Setting")
    sender_name = getattr(setting, "email_candidature_sender_name", None) or "Udshed"
    email_account = frappe.db.get_value("Email Account", {"default_outgoing": 1}, "email_id")
    if email_account:
        return f"{sender_name} <{email_account}>"
    return None


@frappe.whitelist()
def get_liste_inscriptions(filiere=None, annee_academique=None, niveau=None, statut=None, origine=None, cycle=None):
    """Liste des inscrits (page « Liste des inscriptions »).

    Construite à partir des Inscription Academique (candidatures ET
    inscriptions hors candidature : arrivée en cours d'année, import), dans le
    respect des permissions Frappe de l'utilisateur.
    """
    from udshed.api.inscription_import_export import lister_inscriptions

    securite.exiger_acces_page("liste-des-inscriptions")
    return lister_inscriptions(
        filiere=filiere, annee_academique=annee_academique, niveau=niveau, statut=statut,
        origine=origine, cycle=cycle,
    )


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