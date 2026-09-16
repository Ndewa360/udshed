# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ExamenAnonymat(Document):
    """Lien confidentiel entre un étudiant et son code d'anonymat.

    Document à visibilité restreinte (System Manager, Coordonnateur,
    Registration Manager). Le rôle « Correcteur » ne doit jamais y avoir accès.
    """

    def validate(self):
        if not self.code_anonymat:
            frappe.throw("Le code d'anonymat est obligatoire.")

        doublon = frappe.db.exists(
            "Examen Anonymat",
            {
                "session_examen": self.session_examen,
                "teaching_unit": self.teaching_unit,
                "student": self.student,
                "name": ["!=", self.name],
            },
        )
        if doublon:
            frappe.throw(
                "Un code d'anonymat existe déjà pour cet étudiant, cette matière "
                "et cette session d'examen ({0}).".format(doublon)
            )

        doublon_code = frappe.db.exists(
            "Examen Anonymat",
            {"code_anonymat": self.code_anonymat, "name": ["!=", self.name]},
        )
        if doublon_code:
            frappe.throw(
                "Le code d'anonymat <b>{0}</b> est déjà attribué.".format(self.code_anonymat)
            )