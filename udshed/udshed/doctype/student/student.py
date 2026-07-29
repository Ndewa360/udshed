# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Student(Document):

    def validate(self):
        self.definir_nom_complet()
        self.determiner_cycle()

    def definir_nom_complet(self):
        self.nom_complet = f"{self.matricule or ''} - {self.nom or ''} {self.prenom or ''}".strip()

    def determiner_cycle(self):
        if not self.niveau:
            return

        level = frappe.db.get_value("Field of study Level", self.niveau, "level")
        if not level:
            return

        if level.startswith("Licence"):
            self.cycle = "Licence"
        elif level.startswith("Master"):
            self.cycle = "Master"
        elif level.startswith("BTS"):
            self.cycle = "BTS"
        else:
            self.cycle = "Licence"
