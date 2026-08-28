# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class InscriptionAcademique(Document):
    def validate(self):
        self._update_candidate_status()

    def _update_candidate_status(self):
        if self.dossier_origine:
            frappe.db.set_value(
                "Session Inscription Candidate",
                self.dossier_origine,
                "candidature_status",
                "Inscrit",
                update_modified=False,
            )
