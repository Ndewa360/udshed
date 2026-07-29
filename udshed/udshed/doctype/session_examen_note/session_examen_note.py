<<<<<<< HEAD
# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

=======
>>>>>>> 7a5ecfa (Ajout du module de réinscription)
import frappe
from frappe.model.document import Document


class SessionExamenNote(Document):

    def validate(self):
<<<<<<< HEAD
        self.verrouiller_cc()
=======
        self.remplir_filiere_niveau()
>>>>>>> 7a5ecfa (Ajout du module de réinscription)
        self.valider_saisie()
        self.valider_rattrapage()
        self.calculer_note_finale()
        self.determiner_grade()
        self.verifier_unicite()
        self.verifier_statut()

    def verrouiller_cc(self):
        if self.is_new():
            return
        old_examen = frappe.db.get_value(
            "Session Examen Note", self.name, "note_examen"
        )
        old_rattrapage = frappe.db.get_value(
            "Session Examen Note", self.name, "note_examen_rattrapage"
        )
        examen_existe = (old_examen and old_examen > 0) or (
            old_rattrapage and old_rattrapage > 0
        )
        if not examen_existe:
            return

        old_notes = frappe.get_all(
            "Note CC Item",
            filters={"parent": self.name},
            fields=["note_cc", "date_saisie", "commentaire"],
            order_by="creation asc",
        )
        new_notes = [
            {
                "note_cc": cc.note_cc,
                "date_saisie": cc.date_saisie,
                "commentaire": cc.commentaire,
            }
            for cc in (self.notes_cc or [])
        ]
        if old_notes != new_notes:
            frappe.throw(
                "Impossible de modifier les notes de Contrôle Continu. "
                "Une note d'examen ou de rattrapage a déjà été enregistrée pour cette UE."
            )

    def remplir_filiere_niveau(self):
        """Remplit automatiquement filiere et niveau depuis Teaching Unit → course_levels"""
        if not self.teaching_unit:
            return

        # Récupérer les course_levels de la Teaching Unit
        levels = frappe.get_all(
            "Course Field of study level item",
            filters={"parent": self.teaching_unit},
            fields=["filiere", "niveau"],
            limit_page_length=1
        )

        if levels:
            self.filiere = levels[0].filiere
            self.niveau = levels[0].niveau

    def valider_saisie(self):
        note_max = 20
        if self.notes_cc:
            for i, cc in enumerate(self.notes_cc):
                if cc.note_cc and cc.note_cc > note_max:
                    frappe.throw(
                        f"La note CC ligne {i + 1} <b>{cc.note_cc}</b> "
                        f"dépasse le maximum autorisé ({note_max})"
                    )
        if self.note_examen and self.note_examen > note_max:
            frappe.throw(
                f"La note Examen <b>{self.note_examen}</b> "
                f"dépasse le maximum autorisé ({note_max})"
            )
        if self.note_examen_rattrapage and self.note_examen_rattrapage > note_max:
            frappe.throw(
                f"La note Rattrapage <b>{self.note_examen_rattrapage}</b> "
                f"dépasse le maximum autorisé ({note_max})"
            )
        if self.note_tp and self.note_tp > note_max:
            frappe.throw(
                f"La note TP <b>{self.note_tp}</b> "
                f"dépasse le maximum autorisé ({note_max})"
            )
        if self.note_rapport and self.note_rapport > note_max:
            frappe.throw(
                f"La note Rapport <b>{self.note_rapport}</b> "
                f"dépasse le maximum autorisé ({note_max})"
            )
        if self.note_competence and self.note_competence > note_max:
            frappe.throw(
                f"La note Compétence <b>{self.note_competence}</b> "
                f"dépasse le maximum autorisé ({note_max})"
            )

    def valider_rattrapage(self):
        if self.note_examen_rattrapage and not self.date_rattrapage:
            frappe.throw(
                "La date du rattrapage est obligatoire lorsqu'une note de rattrapage est saisie."
            )
        if self.date_rattrapage and not self.note_examen_rattrapage:
            frappe.throw(
                "La note de rattrapage est obligatoire lorsqu'une date de rattrapage est saisie."
            )

    def _determiner_note_examen_active(self):
        if self.note_examen_rattrapage and self.note_examen_rattrapage > 0:
            return self.note_examen_rattrapage
        return self.note_examen or 0

    def calculer_note_finale(self):
        setting = frappe.get_single("Udshed Setting")
        formules = [f for f in setting.formule_notes if f.type_ue == self.type_ue]

        if not formules:
            frappe.throw(
                f"Aucune formule trouvée pour le type UE <b>{self.type_ue}</b>. "
                f"Vérifiez la configuration dans Udshed Setting"
            )

        note_cc_moyenne = self._calculer_moyenne_cc()
        self.note_cc_moyenne = note_cc_moyenne

        note_examen_active = self._determiner_note_examen_active()
        self.note_examen_active = note_examen_active

        note_map = {
            "Controle Continu(CC)": note_cc_moyenne,
            "Examen": note_examen_active,
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

        self.note_finale = min(max(self.note_finale, 0), 20)
        self.note_pct = min(max(self.note_pct, 0), 100)

    def _calculer_moyenne_cc(self):
        if not self.notes_cc:
            return 0
        notes = [cc.note_cc for cc in self.notes_cc if cc.note_cc is not None]
        if not notes:
            return 0
        return round(sum(notes) / len(notes), 2)

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
        if cycle == "Licence":
            seuil = setting.seuil_validation_licence or 50
        else:
            seuil = setting.seuil_validation_master or 60

        if self.note_pct >= seuil:
            frappe.msgprint(
<<<<<<< HEAD
                f"UE <b>Validée</b> — Note: {self.note_pct}% | "
                f"Grade: {self.grade} | Point: {self.point} | {mention_trouvee}",
                indicator="green",
            )
        else:
            frappe.msgprint(
                f"UE <b>Non Validée</b> — Note: {self.note_pct}% | "
                f"Grade: {self.grade} | Point: {self.point} | {mention_trouvee}",
                indicator="red",
            )

    def verifier_unicite(self):
        filters = {
            "student": self.student,
            "teaching_unit": self.teaching_unit,
            "session_examen": self.session_examen,
        }
        if self.name:
            filters["name"] = ["!=", self.name]

        existant = frappe.db.exists("Session Examen Note", filters)
        if existant:
            frappe.throw(
                f"Une note existe déjà pour l'étudiant <b>{self.student}</b> "
                f"dans l'UE <b>{self.teaching_unit}</b> pour cette session d'examen."
            )

    def verifier_statut(self):
        transitions = {
            "Brouillon": ["Saisi"],
            "Saisi": ["Validé"],
            "Validé": ["Publié"],
        }

        if not self.statut:
            self.statut = "Brouillon"
            return

        if self._get_old_statut() and self._get_old_statut() != self.statut:
            statuts_autorises = transitions.get(self._get_old_statut(), [])
            if self.statut not in statuts_autorises:
                frappe.throw(
                    f"Transition non autorisée : <b>{self._get_old_statut()}</b> "
                    f"→ <b>{self.statut}</b>. "
                    f"Transitions possibles : "
                    f"{', '.join(statuts_autorises) or 'aucune'}"
                )

    def _get_old_statut(self):
        if self.is_new():
            return None
        return frappe.db.get_value("Session Examen Note", self.name, "statut")
=======
                f"UE <b>Validée</b> — Note: {self.note_pct}% | Grade: {self.grade} | Point: {self.point} | {mention_trouvee}",
                indicator="green"
            )
        else:
            frappe.msgprint(
                f"UE <b>Non Validée</b> — Note: {self.note_pct}% | Grade: {self.grade} | Point: {self.point} | {mention_trouvee}",
                indicator="red"
            )
>>>>>>> 7a5ecfa (Ajout du module de réinscription)
