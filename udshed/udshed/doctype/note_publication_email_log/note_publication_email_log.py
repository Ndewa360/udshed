import frappe
from frappe import _
from frappe.model.document import Document


class NotePublicationEmailLog(Document):
    """Journal de suivi des e-mails de notification de publication de notes.

    Garantit qu'un étudiant ne reçoit qu'un seul e-mail « Envoyé » pour
    une même publication (session × matière × étudiant). Un doublon « Envoyé »
    est refusé ; les tentatives en « Échec » / « Adresse inexistante »
    peuvent être relancées.
    """

    def validate(self):
        if self.statut != "Envoyé":
            return

        existant = frappe.db.exists(
            "Note Publication Email Log",
            {
                "session_examen": self.session_examen,
                "teaching_unit": self.teaching_unit,
                "student": self.student,
                "statut": "Envoyé",
                "name": ["!=", self.name],
            },
        )
        if existant:
            frappe.throw(
                _("L'étudiant <b>{0}</b> a déjà reçu le courriel de publication "
                  "pour la matière <b>{1}</b> de la session <b>{2}</b>. "
                  "Aucun doublon n'est autorisé.").format(
                    self.student, self.teaching_unit, self.session_examen
                )
            )