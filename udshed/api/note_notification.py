import re
from urllib.parse import urlencode

import frappe
from frappe import _

from udshed.api.candidature import get_school_logo_url
from udshed.api.inscription import _get_sender

DOCTYPE_LOG = "Note Publication Email Log"

_PATTERN_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------------ #
#  Accès aux données étudiants / matière
# ------------------------------------------------------------------ #
def _email_etudiant(student):
    """Adresse e-mail renseignée par l'étudiant lors de son inscription.

    Le champ ``email`` du document Student est alimenté depuis l'adresse
    fournie dans la Session Inscription Candidate au moment de l'inscription.
    """
    email = frappe.db.get_value("Student", student, "email") or ""
    return email.strip()


def _nom_etudiant(student):
    doc = frappe.db.get_value("Student", student, ["nom", "prenom"], as_dict=True) or {}
    nom = (doc.get("nom") or "").strip()
    prenom = (doc.get("prenom") or "").strip()
    return f"{nom} {prenom}".strip() or student


def _libelle_matiere(teaching_unit):
    """Libellé affichable de la matière (même règle que le babillard)."""
    tu = frappe.db.get_value(
        "Teaching Unit", teaching_unit, ["course", "intitule_cours"], as_dict=True
    ) or {}
    course_name = tu.get("course") or ""
    if course_name:
        row = frappe.db.get_value(
            "Course", course_name, ["code", "intitule"], as_dict=True
        ) or {}
        intitule = (row.get("intitule") or "").strip()
        code = (row.get("code") or course_name).strip()
        return f"{intitule} ({code})" if intitule else code
    return (tu.get("intitule_cours") or "").strip() or teaching_unit


def _est_email_valide(email):
    return bool(_PATTERN_EMAIL.match(email or ""))


# ------------------------------------------------------------------ #
#  Lien du babillard
# ------------------------------------------------------------------ #
def _lien_babillard(session_doc, student_name):
    """Lien vers le babillard public, pré-rempli pour l'étudiant concerné."""
    base = frappe.utils.get_url() + "/babillard"
    params = {}

    niveau = frappe.db.get_value("Student", student_name, "niveau_actuel") or ""
    if niveau:
        params["niveau"] = niveau

    matricule = frappe.db.get_value("Student", student_name, "matricule") or student_name
    if matricule:
        params["matricule"] = matricule

    if session_doc.get("academic_year"):
        params["academic_year"] = session_doc.academic_year
    if session_doc.get("semestre"):
        params["semestre"] = session_doc.semestre

    if not params:
        return base

    return "{0}?{1}".format(base, urlencode(params))


# ------------------------------------------------------------------ #
#  Journal de suivi
# ------------------------------------------------------------------ #
def _deja_envoye(session, teaching_unit, student):
    """Vrai si un e-mail a déjà été envoyé pour (session × matière × étudiant)."""
    return bool(
        frappe.db.exists(
            DOCTYPE_LOG,
            {
                "session_examen": session,
                "teaching_unit": teaching_unit,
                "student": student,
                "statut": "Envoyé",
            },
        )
    )


def _journaliser(session, teaching_unit, student, email, statut, erreur=None):
    doc = frappe.new_doc(DOCTYPE_LOG)
    doc.session_examen = session
    doc.teaching_unit = teaching_unit
    doc.student = student
    doc.email = email
    doc.statut = statut
    doc.erreur = f"{erreur}"[:2000] if erreur else None
    doc.date_envoi = frappe.utils.now_datetime()
    doc.insert(ignore_permissions=True)
    return doc.name


# ------------------------------------------------------------------ #
#  Envoi / traitement
# ------------------------------------------------------------------ #
def _envoyer(email, nom_etudiant, matiere, babillard_url):
    frappe.sendmail(
        recipients=[email],
        sender=_get_sender(),
        subject=_("Les notes de la matière {0} sont disponibles").format(matiere),
        template="note_publication",
        args={
            "nom_etudiant": nom_etudiant,
            "matiere": matiere,
            "babillard_url": babillard_url,
            "base_url": frappe.utils.get_url(),
            "logo_url": get_school_logo_url(),
        },
        now=True,
    )


def _traiter_etudiant(session_doc, student, teaching_unit):
    """Envoie (si nécessaire) l'e-mail de publication à un étudiant.

    Adresse absente ou invalide  -> journalisé « Adresse inexistante »
    Déjà notifié                  -> ignoré (aucun doublon)
    Envoi réussi                  -> journalisé « Envoyé »
    Erreur d'envoi                -> journalisé « Échec »

    Ne lève jamais : ce traitement ne doit pas bloquer le reste du lot.
    """
    email = _email_etudiant(student)

    if not _est_email_valide(email):
        _journaliser(session_doc.name, teaching_unit, student, email, "Adresse inexistante")
        frappe.logger().info(
            "udshed: notification publication {0} - {1} sans adresse valide".format(
                session_doc.name, student
            )
        )
        return

    if _deja_envoye(session_doc.name, teaching_unit, student):
        return

    try:
        _envoyer(
            email,
            _nom_etudiant(student),
            _libelle_matiere(teaching_unit),
            _lien_babillard(session_doc, student),
        )
        _journaliser(session_doc.name, teaching_unit, student, email, "Envoyé")
        frappe.logger().info(
            "udshed: e-mail de publication envoyé à {0} ({1}) pour {2} / {3}".format(
                student, email, session_doc.name, teaching_unit
            )
        )
    except Exception as e:
        try:
            _journaliser(session_doc.name, teaching_unit, student, email, "Échec", str(e))
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "udshed: journalisation échec notification publication {}".format(
                    session_doc.name
                ),
            )


def notifier_publication_matiere(session):
    """Envoie les e-mails de publication aux étudiants concernés.

    S'exécute normalement dans un worker RQ après la validation du commit
    de publication : les notes sont donc effectivement publiées (statut
    « Publié ») quand les e-mails partent. Pour chaque matière de la
    session, chaque étudiant ayant une note publiée reçoit un e-mail
    unique (déduplication par session × matière × étudiant).

    La fonction ne lève jamais : les erreurs sont journalisées dans
    « Note Publication Email Log » à des fins de suivi.
    """
    session_doc = frappe.get_doc("Session Examen", session)

    notes = frappe.get_all(
        "Session Examen Note",
        filters={"session_examen": session, "statut": "Publié"},
        fields=["teaching_unit", "student"],
    )

    traites = set()
    for note in notes:
        cle = (note.student, note.teaching_unit)
        if cle in traites:
            continue
        traites.add(cle)
        try:
            _traiter_etudiant(session_doc, note.student, note.teaching_unit)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "udshed: notification publication {}".format(session),
            )

    frappe.db.commit()

    return len(traites)


def notifier_publication_note(session, student, teaching_unit):
    """Notifie un étudiant pour une note publiée unitairement.

    Utilisé par le DocType Session Examen Note (bouton « Publier ») lorsque
    la publication du lot (``publier_session``) ne passe pas par ce hook.
    Déduplication et journalisation identiques au traitement par lot.
    """
    try:
        session_doc = frappe.get_doc("Session Examen", session)
        _traiter_etudiant(session_doc, student, teaching_unit)
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "udshed: notification publication unitaire {} / {}".format(session, student),
        )


@frappe.whitelist()
def relancer_notification_publication(session):
    """Relance manuellement la notification d'une publication (admin / test)."""
    nb = notifier_publication_matiere(session)
    frappe.msgprint(
        _("{0} étudiant(s) concerné(s) par la notification de la session {1}.").format(
            nb, session
        )
    )
    return {"session": session, "students": nb}