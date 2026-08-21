# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ResultatAcademique(Document):

    def validate(self):
        self.remplir_noms()
        self.determiner_statut()

    def after_insert(self):
        self._declencher_mps_mpc()

    def on_update(self):
        if not self.is_new():
            self._declencher_mps_mpc()

    def on_trash(self):
        # on_trash s'exécute AVANT la suppression effective en base : on exclut
        # cette UE pour ne pas la compter dans la MPS encore existante.
        self._declencher_mps_mpc(teaching_unit_a_exclure=self.teaching_unit)

    def _declencher_mps_mpc(self, teaching_unit_a_exclure=None):
        """Recalcule MPS/MPC uniquement si les données clés ont changé.

        On évite la boucle infinie : ResultatAcademique.save() -> calculer_et_sauvegarder_mps_mpc
        -> ResultatSemestre.save() -> (rien sur ResultatAcademique).
        Le flag _skip_mps_mpc permet aux appels internes de court-circuiter le déclenchement.
        """
        if getattr(self, "_skip_mps_mpc", False):
            return
        if not (self.student and self.semestre and self.academic_year):
            return
        from udshed.api.resultat_academique import calculer_et_sauvegarder_mps_mpc
        calculer_et_sauvegarder_mps_mpc(
            self.student, self.semestre, self.academic_year,
            teaching_unit_a_exclure=teaching_unit_a_exclure,
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

    def determiner_statut(self):
        from udshed.grade_calculation import get_seuil_validation, get_student_cycle

        if not self.student:
            return

        cycle = get_student_cycle(self.student)
        seuil = get_seuil_validation(cycle)

        if self.note_pct is not None and self.note_pct >= seuil:
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
