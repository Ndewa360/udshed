# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class FicheReport(Document):
    """Fiche de report d'une note anonyme après levée de l'anonymat.

    Une ligne par (étudiant, matière, session) levé(e) : identité, matière,
    session et note reportée (celle enregistrée lors de la correction). C'est
    la trace filable de l'opération de levée et la source imprimable
    (« fiche de report ») transmise ensuite au circuit des résultats.
    """

    def validate(self):
        if self.note_reportee is None:
            frappe.throw(_("La note reportée (/20) est obligatoire."))
        if self.note_reportee < 0 or self.note_reportee > 20:
            frappe.throw(_("La note reportée doit être comprise entre 0 et 20."))

        doublon = frappe.db.exists(
            "Fiche Report",
            {
                "session_examen": self.session_examen,
                "teaching_unit": self.teaching_unit,
                "student": self.student,
                "name": ["!=", self.name],
            },
        )
        if doublon:
            frappe.throw(
                _("Une fiche de report existe déjà pour cet étudiant, cette matière "
                  "et cette session d'examen ({0}).").format(doublon)
            )

    def before_insert(self):
        self.synchroniser_identite_etudiant()

    def synchroniser_identite_etudiant(self):
        """Recopie le matricule et l'identité depuis le Student lié."""
        if not self.student:
            return
        etudiant = frappe.db.get_value(
            "Student",
            self.student,
            ["matricule", "nom", "prenom"],
            as_dict=1,
        )
        if not etudiant:
            return
        self.matricule = etudiant.matricule or self.student
        self.nom = etudiant.nom or ""
        self.prenom = etudiant.prenom or ""