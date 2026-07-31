import frappe
from frappe.model.document import Document
from udshed.grade_calculation import (
    get_active_formula,
    calculer_note_finale_ue,
    est_valide,
)

WORKFLOW_ORDRE = {"Brouillon": 0, "Saisi": 1, "Validé": 2, "Publié": 3}
ROLES_TRANSITIONS = {
    "Saisi": ["Teacher", "Coordonateur", "System Manager"],
    "Validé": ["Coordonateur", "System Manager"],
    "Publié": ["System Manager"],
}


class SessionExamenNote(Document):

    def validate(self):
        self.remplir_filiere_niveau()
        self.valider_saisie()
        self.valider_workflow()
        self.calculer_note_finale()
        self.determiner_grade()

    def remplir_filiere_niveau(self):
        if not self.teaching_unit:
            return
        levels = frappe.get_all(
            "Course Field of study level item",
            filters={"parent": self.teaching_unit},
            fields=["filiere", "niveau"],
            limit_page_length=1,
        )
        if levels:
            self.filiere = levels[0].filiere
            self.niveau = levels[0].niveau

    def valider_saisie(self):
        note_max = 20
        champs = [
            ("note_cc", "Note CC"),
            ("note_examen", "Note Examen"),
            ("note_examen_rattrapage", "Note Examen Rattrapage"),
            ("note_tp", "Note TP"),
            ("note_rapport", "Note Rapport"),
            ("note_competence", "Note Compétence"),
        ]
        for champ, label in champs:
            val = getattr(self, champ, None)
            if val is not None and val > note_max:
                frappe.throw(
                    f"La {label} <b>{val}</b> dépasse le maximum autorisé ({note_max})"
                )

    def valider_workflow(self):
        if not self.get("__islocal") and not self._doc_before_save:
            return
        ancien = self._doc_before_save.get("statut") if self._doc_before_save else None
        nouveau = self.statut or "Brouillon"

        if not ancien:
            self.statut = "Brouillon"
            return

        ordre_ancien = WORKFLOW_ORDRE.get(ancien, -1)
        ordre_nouveau = WORKFLOW_ORDRE.get(nouveau, -1)

        if ordre_nouveau < ordre_ancien:
            frappe.throw(
                f"Impossible de revenir en arrière dans le workflow : "
                f"{ancien} → {nouveau}"
            )
        if ordre_nouveau == ordre_ancien:
            return

        roles_autorises = ROLES_TRANSITIONS.get(nouveau, [])
        user_roles = frappe.get_roles(frappe.session.user)
        if not any(r in roles_autorises for r in user_roles):
            frappe.throw(
                f"Seuls les rôles {', '.join(roles_autorises)} peuvent "
                f"passer le statut à « {nouveau} »."
            )

    def _get_formula(self):
        student = frappe.get_doc("Student", self.student)
        cycle = student.cycle or "Licence"
        return get_active_formula(cycle)

    def calculer_note_finale(self):
        rattrapage = self.note_examen_rattrapage or 0
        normal = self.note_examen or 0
        self.note_examen_active = (rattrapage if rattrapage > 0 else normal)

        formula = self._get_formula()

        notes_map = {
            "TP": self.note_tp or 0,
            "Rapport": self.note_rapport or 0,
            "Competence": self.note_competence or 0,
            "Competences": self.note_competence or 0,
        }

        notes_complementaires = {}
        for comp in formula.composantes_supplementaires:
            notes_complementaires[comp.nom] = notes_map.get(comp.nom, 0)

        note_finale = calculer_note_finale_ue(
            note_cc=self.note_cc or 0,
            note_examen=self.note_examen_active or 0,
            notes_complementaires=notes_complementaires,
            formula=formula,
        )

        self.note_finale = note_finale
        self.note_pct = round((note_finale / 20) * 100, 2)

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
        self.mention = mention_trouvee

        student = frappe.get_doc("Student", self.student)
        cycle = student.cycle or "Licence"
        valide = est_valide(self.note_finale, cycle)

        if valide:
            self.statut_color = "green"
            frappe.msgprint(
                f"UE <b>Validée</b> — Note: {self.note_pct}% | "
                f"Grade: {self.grade} | Point: {self.point} | {mention_trouvee}",
                indicator="green",
            )
        else:
            self.statut_color = "red"
            frappe.msgprint(
                f"UE <b>Non Validée</b> — Note: {self.note_pct}% | "
                f"Grade: {self.grade} | Point: {self.point} | {mention_trouvee}",
                indicator="red",
            )
