import frappe
from frappe.model.document import Document
from udshed.grade_calculation import get_active_formula


class ResultatAcademique(Document):

    def validate(self):
        self.remplir_noms()
        self.determiner_statut()
        self.determiner_grade_et_mention()

    def after_insert(self):
        self.declencher_mps_mpc()

    def on_update(self):
        if not self.is_new():
            self.declencher_mps_mpc()

    def declencher_mps_mpc(self):
        from udshed.api.resultat_academique import calculer_et_sauvegarder_mps_mpc

        calculer_et_sauvegarder_mps_mpc(
            self.student, self.semestre, self.academic_year
        )

    def remplir_noms(self):
        if self.student:
            student_doc = frappe.get_doc("Student", self.student)
            self.student_name = f"{student_doc.matricule or ''} - {student_doc.nom or ''} {student_doc.prenom or ''}".strip()

        if self.teaching_unit:
            tu_doc = frappe.get_doc("Teaching Unit", self.teaching_unit)
            if tu_doc.course:
                self.ue_name = frappe.db.get_value("Course", tu_doc.course, "intitule") or self.teaching_unit
            else:
                self.ue_name = self.teaching_unit

    def _get_seuil(self):
        student_doc = frappe.get_doc("Student", self.student)
        cycle = student_doc.cycle or "Licence"
        formula = get_active_formula(cycle)
        return formula.seuil_validation

    def determiner_statut(self):
        seuil = self._get_seuil()

        if self.note_pct >= seuil:
            self.statut = "Validé"
            self.statut_color = "green"
        else:
            self.statut = "Non Validé"
            self.statut_color = "red"

    def determiner_grade_et_mention(self):
        setting = frappe.get_single("Udshed Setting")

        for g in setting.grille_grades:
            if g.note_min <= self.note_pct <= g.note_max:
                self.grade = g.grade
                self.point = g.point
                self.mention = g.mention
                return

        frappe.throw(
            f"Aucun grade trouvé pour la note <b>{self.note_pct}%</b>. "
            f"Vérifiez la grille des grades dans Udshed Setting"
        )
