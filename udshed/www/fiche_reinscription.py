import frappe
from frappe import _

from udshed.utils.reregistration import has_reregistered


def get_context(context):
    """Fiche de réinscription de l'étudiant connecté.

    - Si l'étudiant s'est déjà réinscrit : affiche sa fiche avec le
      bouton de téléchargement (si la fiche n'a pas déjà été téléchargée).
    - Sinon : affiche la fiche pré-remplie à soumettre.
    """
    context.title = "Fiche de réinscription"

    student_name = frappe.session.user
    if not student_name or student_name == "Guest":
        frappe.local.flags.redirect_location = "/connexion-etudiant"
        raise frappe.Redirect

    student = _get_student(student_name)
    if not student:
        frappe.local.flags.redirect_location = "/connexion-etudiant"
        raise frappe.Redirect

    context.student = student
    context.student_name = f"{student.prenom or ''} {student.nom or ''}".strip()
    context.initials = _get_initials(student)
    context.niveau = student.niveau_actuel or ""
    context.filiere_name = frappe.db.get_value("Field of study", student.filiere, "name_of_field") if student.filiere else ""
    context.active = "reinscription"

    # Déjà réinscrit ?
    context.has_reregistered, context.reregistration = has_reregistered(student.name)

    if not context.has_reregistered:
        # Préparer les infos de la fiche à remplir
        context.open_sessions = frappe.get_all(
            "Session Reinscription",
            filters={"statut": "Ouverte"},
            fields=["name", "academic_year", "date_ouverture", "date_cloture"],
            order_by="date_ouverture desc",
        )
        context.semestres = ["Semestre 1", "Semestre 2", "Les deux"]

    # Construire les détails lisibles de la fiche (pour l'affichage en lecture seule
    # lorsque l'étudiant est déjà réinscrit).
    if context.has_reregistered:
        context.fiche_details = _build_fiche_details(context.reregistration)


def _get_student(user_email):
    student_name = frappe.db.get_value("Student", {"utilisateur": user_email}, "name")
    if student_name:
        return frappe.get_doc("Student", student_name)
    return None


def _get_initials(student):
    prenom = (student.prenom or "")[:1]
    nom = (student.nom or "")[:1]
    return f"{prenom}{nom}".upper()


def _build_fiche_details(doc):
    """Construit un dict lisible de la fiche pour affichage en lecture seule.

    La grille de matières et les UE à reprendre proviennent UNIQUEMENT du
    module de gestion de notes (get_transcript_data). Les informations
    d'identification de la fiche (référence, année, filière, niveau, semestre,
    statut) viennent du doctype Academic Reregistration.
    """
    filiere_label = frappe.db.get_value("Field of study", doc.filiere, "name_of_field") or doc.filiere

    # Données réelles du module note (même source que le relevé officiel).
    from udshed.api.transcript import get_transcript_data

    student_doc = frappe.get_doc("Student", doc.student)
    transcript = get_transcript_data(student_doc)
    semesters = transcript.get("semesters", [])

    grille = []
    ue_a_reprendre = []
    vus = set()
    for sem in semesters:
        for ue in sem.get("ues", []):
            if ue.get("code") in vus:
                continue
            vus.add(ue.get("code"))
            grille.append({
                "code": ue.get("code") or "",
                "intitule": ue.get("intitule") or ue.get("code") or "",
                "semestre": sem.get("label") or "",
                "academic_year": sem.get("academic_year") or "",
                "credits": ue.get("credits") or 0,
                "note_finale": ue.get("note_finale"),
                "grade": ue.get("grade") or "",
                "mention": ue.get("mention") or "",
                "statut": ue.get("statut") or "",
                "session": ue.get("session") or "",
                "est_rattrapage": bool(ue.get("est_rattrapage")),
            })
            if ue.get("statut") != "Validé":
                ue_a_reprendre.append(grille[-1])

    return {
        "name": doc.name,
        "academic_year": doc.academic_year,
        "year_label": transcript.get("niveau_label") or "",
        "filiere_label": filiere_label,
        "niveau": doc.niveau,
        "niveau_precedent": doc.niveau_precedent or "",
        "decision_notes": doc.decision_notes or "",
        "semestre": doc.semestre,
        "statut": doc.statut,
        "fiche_telechargee": bool(doc.fiche_telechargee),
        "date": doc.creation.strftime("%d/%m/%Y") if hasattr(doc.creation, "strftime") else doc.creation,
        "grille": grille,
        "ue_a_reprendre": ue_a_reprendre,
        "nb_ue": len(grille),
        "nb_a_reprendre": len(ue_a_reprendre),
        "nb_validees": sum(1 for g in grille if g["statut"] == "Validé"),
        "cum_credits_obtenus": transcript.get("total_credits_obtenus") or 0,
        "cum_credits": transcript.get("total_credits") or 0,
        "pct_validation": transcript.get("pct_validation") or 0,
        "decision_globale": transcript.get("overall_decision") or "",
    }
