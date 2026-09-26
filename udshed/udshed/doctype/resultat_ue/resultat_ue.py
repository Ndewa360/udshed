# Copyright (c) 2026, Udshed and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class ResultatUE(Document):
    """Résultat d'une UE (une ligne par étudiant x UE x année x semestre).

    La note de l'UE est la moyenne **pondérée par les crédits** des matières
    retenues, alignée sur la MPS du semestre (`calculer_mps`). Le statut et la
    couleur sont redérivés à chaque sauvegarde : le champ n'est donc jamais
    modifiable à la main, exactement comme `Resultat Academique`.
    """

    def validate(self):
        self.remplir_noms()
        self.determiner_statut()

    def remplir_noms(self):
        if self.student:
            student_doc = frappe.get_doc("Student", self.student)
            self.student_name = (
                f"{student_doc.matricule or ''} - {student_doc.nom or ''} "
                f"{student_doc.prenom or ''}"
            ).strip()

        if self.teaching_unit_value and not self.ue_code:
            ue = frappe.db.get_value(
                "Teaching Unit Value",
                self.teaching_unit_value,
                ["code", "intitule"],
                as_dict=True,
            )
            if ue:
                self.ue_code = ue.code or ""
                self.ue_intitule = ue.intitule or ""

    def determiner_statut(self):
        from udshed.grade_calculation import get_seuil_validation, get_student_cycle

        if not self.student:
            return

        self.seuil_validation = get_seuil_validation(get_student_cycle(self.student))

        # UE incomplète : au moins une matière sans note retenue. Aucun calcul
        # partiel n'est fait, la note reste vide.
        #
        # Le test porte sur `est_calculable` et non sur `note_ue_pct is None` :
        # les colonnes numériques de Frappe sont `NOT NULL DEFAULT 0`, donc une
        # note absente est relue 0.0. Se fier à la valeur ferait passer l'UE
        # « En attente » à « Non Validé » dès la sauvegarde suivante.
        if not self.est_calculable:
            self.statut = "En attente"
            self.statut_color = "orange"
            return

        if flt(self.note_ue_pct) >= flt(self.seuil_validation):
            self.statut = "Validé"
            self.statut_color = "green"
        else:
            self.statut = "Non Validé"
            self.statut_color = "red"
