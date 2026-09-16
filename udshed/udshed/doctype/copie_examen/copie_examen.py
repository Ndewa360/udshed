# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CopieExamen(Document):
    """Copie d'examen anonyme : aucun Champ d'identité étudiant.

    La copie est identifiée uniquement par son code d'anonymat. Le lien vers
    l'étudiant est porté par le document « Examen Anonymat » (confidentiel)
    auquel seul un rôle autorisé a accès.
    """

    def validate(self):
        if not self.code_anonymat:
            frappe.throw("Le code d'anonymat est obligatoire.")

        if self.note_examen is not None and (self.note_examen < 0 or self.note_examen > 20):
            frappe.throw("La note d'examen doit être comprise entre 0 et 20.")