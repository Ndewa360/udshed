import frappe
from frappe.model.document import Document


class GradeFormula(Document):

    def validate(self):
        self.set_seuil_validation()
        self.valider_poids()
        self.valider_unicite_active()

    def set_seuil_validation(self):
        if self.cycle == "Licence":
            self.seuil_validation = 50
        elif self.cycle == "Master":
            self.seuil_validation = 60

    def valider_poids(self):
        total = (self.poids_cc or 0) + (self.poids_examen or 0)
        for row in self.composantes_supplementaires:
            total += row.poids or 0
        self.total_poids = total
        if total != 100:
            frappe.throw(
                f"La somme de tous les poids ({total}%) doit être égale à 100%. "
                f"Poids CC: {self.poids_cc}% + Examen: {self.poids_examen}% + "
                f"Supplémentaires: {total - (self.poids_cc or 0) - (self.poids_examen or 0)}% = {total}%"
            )

    def valider_unicite_active(self):
        if not self.active:
            return
        filters = {
            "cycle": self.cycle,
            "active": 1,
            "name": ["!=", self.name or "new-grade-formula-1"],
        }
        existante = frappe.db.exists("Grade Formula", filters)
        if existante:
            frappe.throw(
                f"Une formule active existe déjà pour le cycle {self.cycle} : "
                f"<a href='/app/grade-formula/{existante}'>{existante}</a>. "
                "Désactivez-la avant d'en activer une nouvelle."
            )
