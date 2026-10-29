# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ResultatSemestre(Document):

    def validate(self):
        self.remplir_noms()
        self.determiner_mention()
        self.verifier_unicite()

    def remplir_noms(self):
        if self.student:
            student_doc = frappe.get_doc("Student", self.student)
            self.student_name = (
                f"{student_doc.matricule or ''} - "
                f"{student_doc.nom or ''} {student_doc.prenom or ''}"
            ).strip()

    def determiner_mention(self):
        if not self.mps:
            return

        setting = frappe.get_single("Udshed Setting")
        for g in setting.grille_grades:
            note_min = g.get("note_min_100")
            if note_min is None:
                note_min = g.get("note_min") or 0
            note_max = g.get("note_max_100")
            if note_max is None:
                note_max = g.get("note_max") or 0
            try:
                if note_min <= self.mps <= note_max:
                    self.mention = g.mention
                    return
            except TypeError:
                continue

        self.mention = ""

    def verifier_unicite(self):
        filters = {
            "student": self.student,
            "academic_year": self.academic_year,
            "semestre": self.semestre,
        }
        if self.name:
            filters["name"] = ["!=", self.name]

        existant = frappe.db.exists("Resultat Semestre", filters)
        if existant:
            frappe.throw(
                f"Un résultat de semestre existe déjà pour l'étudiant "
                f"<b>{self.student}</b> pour {self.semestre} / {self.academic_year}"
            )
