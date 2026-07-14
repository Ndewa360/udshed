# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class SessionExamenNote(Document):
	pass
import frappe
from frappe.model.document import Document


class SessionExamenNote(Document):

    def validate(self):
        self.valider_saisie()
        self.calculer_note_finale()
        self.determiner_grade()

    def valider_saisie(self):
        note_max = 20
        if self.note_cc and self.note_cc > note_max:
            frappe.throw(f"La note CC <b>{self.note_cc}</b> dépasse le maximum autorisé ({note_max})")
        if self.note_examen and self.note_examen > note_max:
            frappe.throw(f"La note Examen <b>{self.note_examen}</b> dépasse le maximum autorisé ({note_max})")
        if self.note_tp and self.note_tp > note_max:
            frappe.throw(f"La note TP <b>{self.note_tp}</b> dépasse le maximum autorisé ({note_max})")
        if self.note_rapport and self.note_rapport > note_max:
            frappe.throw(f"La note Rapport <b>{self.note_rapport}</b> dépasse le maximum autorisé ({note_max})")
        if self.note_competence and self.note_competence > note_max:
            frappe.throw(f"La note Compétence <b>{self.note_competence}</b> dépasse le maximum autorisé ({note_max})")

    def calculer_note_finale(self):
        setting = frappe.get_single("Udshed Setting")
        formules = [f for f in setting.formule_notes if f.type_ue == self.type_ue]

        if not formules:
            frappe.throw(
                f"Aucune formule trouvée pour le type UE <b>{self.type_ue}</b>. "
                f"Vérifiez la configuration dans Udshed Setting"
            )

        note_map = {
            "Controle Continu(CC)": self.note_cc or 0,
            "Examen": self.note_examen or 0,
            "Travaux Pratique (TP)": self.note_tp or 0,
            "Rapport": self.note_rapport or 0,
            "Competence": self.note_competence or 0,
        }

        note_finale = 0
        for formule in formules:
            note_composante = note_map.get(formule.composante, 0)
            contribution = (note_composante / 20) * formule.pourcentage
            note_finale += contribution

        self.note_finale = round(note_finale * 20 / 100, 2)
        self.note_pct = round(note_finale, 2)

    def determiner_grade(self):
        setting = frappe.get_single("Udshed Setting")
        grade_trouve = None
        point_trouve = 0
        mention_trouvee = ""

        for g in setting.grille_grades:
            if g.note_min <= self.note_pct <= g.note_max:
                grade_trouve = g.grade
                point_trouve = g.point
                mention_trouvee = g.mention
                break

        if not grade_trouve:
            frappe.throw(
                f"Aucun grade trouvé pour la note <b>{self.note_pct}%</b>. "
                f"Vérifiez la grille des grades dans Udshed Setting"
            )

        self.grade = grade_trouve
        self.point = point_trouve

        student = frappe.get_doc("Student", self.student)
        if student.cycle == "Licence":
            seuil = setting.seuil_validation_licence or 50
        else:
            seuil = setting.seuil_validation_master or 60

        if self.note_pct >= seuil:
            frappe.msgprint(
                f"✅ UE <b>Validée</b> — Note: {self.note_pct}% | Grade: {self.grade} | Point: {self.point} | {mention_trouvee}",
                indicator="green"
            )
        else:
            frappe.msgprint(
                f"❌ UE <b>Non Validée</b> — Note: {self.note_pct}% | Grade: {self.grade} | Point: {self.point} | {mention_trouvee}",
                indicator="red"
            )