import frappe
<<<<<<< HEAD
from frappe import _
from frappe.model.document import Document

from udshed.grade_calculation import (
    calculer_note_ue,
    get_cycle_formula,
    get_student_cycle,
)

NOTE_MAX = 20
=======
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
>>>>>>> origin/feat/Eval-Note


class SessionExamenNote(Document):

    def validate(self):
<<<<<<< HEAD
        self.verrouiller_si_publie()
        self.remplir_filiere_niveau()
        self.deriver_drapeaux_saisie()
        self.valider_saisie()
        self.calculer_note_cc_moyenne()
        self.calculer_note_examen_active()
        self.calculer_note_finale()
        self.determiner_grade()

    # ------------------------------------------------------------------ #
    #  Verrouillage
    # ------------------------------------------------------------------ #
    def verrouiller_si_publie(self):
        """Empêche toute modification quand la session d'examen est publiée."""
        if not self.session_examen:
            return
        statut_session = frappe.db.get_value("Session Examen", self.session_examen, "statut")
        if statut_session == "Publiée" and not frappe.session.user == "Administrator":
            frappe.throw(
                _("Notes publiées — la session <b>{0}</b> est clôturée, toute modification est impossible.").format(
                    self.session_examen
                )
            )

    # ------------------------------------------------------------------ #
    #  Identification
    # ------------------------------------------------------------------ #
    def remplir_filiere_niveau(self):
        """Complète filière et niveau depuis la Teaching Unit si absents."""
        if not self.teaching_unit:
            return
        if not self.filiere or not self.niveau:
            levels = frappe.get_all(
                "Course Field of study level item",
                filters={"parent": self.teaching_unit},
                fields=["filiere", "niveau"],
                limit_page_length=1,
            )
            if levels:
                if not self.filiere:
                    self.filiere = levels[0].filiere
                if not self.niveau:
                    self.niveau = levels[0].niveau

    def deriver_drapeaux_saisie(self):
        """Déduit les drapeaux *saisi des valeurs réellement présentes (cohérence multi-canal)."""
        self.cc_saisi = 1 if any(row.note_cc is not None for row in self.notes_cc) else 0
        if self.note_examen is not None:
            self.examen_saisi = 1
        if self.note_examen_rattrapage is not None:
            self.rattrapage_saisi = 1
        if self.note_tp is not None:
            self.tp_saisi = 1

    # ------------------------------------------------------------------ #
    #  Validation de la saisie
    # ------------------------------------------------------------------ #
    def valider_saisie(self):
        champs = [
            ("note_cc_moyenne", "CC"),
            ("note_examen", "Examen"),
            ("note_examen_rattrapage", "Rattrapage"),
            ("note_examen_active", "Examen retenue"),
            ("note_tp", "TP"),
            ("note_rapport", "Rapport"),
            ("note_competence", "Compétence"),
        ]
        for champ, libelle in champs:
            valeur = self.get(champ)
            if valeur is not None:
                if valeur < 0:
                    frappe.throw(_("La note <b>{0}</b> ({1}) ne peut pas être négative.").format(valeur, libelle))
                if valeur > NOTE_MAX:
                    frappe.throw(
                        _("La note <b>{0}</b> ({1}) dépasse le maximum autorisé ({2}/20).").format(
                            valeur, libelle, NOTE_MAX
                        )
                    )

        for row in self.notes_cc:
            if row.note_cc is not None:
                if row.note_cc < 0:
                    frappe.throw(_("La note CC <b>{0}</b> ne peut pas être négative.").format(row.note_cc))
                if row.note_cc > NOTE_MAX:
                    frappe.throw(
                        _("La note CC <b>{0}</b> ({1}) dépasse le maximum autorisé ({2}/20).").format(
                            row.note_cc, row.cc_label or "CC", NOTE_MAX
                        )
                    )

    # ------------------------------------------------------------------ #
    #  Calcul de la moyenne CC
    # ------------------------------------------------------------------ #
    def calculer_note_cc_moyenne(self):
        """Calcule la moyenne de CC selon la méthode configurée (Grade Formula d'abord)."""
        valeurs = [(row.cc_weight or 1, row.note_cc) for row in self.notes_cc if row.note_cc is not None]

        if not valeurs:
            self.note_cc_moyenne = None
            self.cc_saisi = 0
            return

        formula = None
        if self.student:
            cycle = get_student_cycle(self.student)
            formula = get_cycle_formula(cycle)

        setting = frappe.get_single("Udshed Setting")
        methode = (
            formula.methode_calcul_cc
            if formula and formula.methode_calcul_cc
            else (setting.methode_calcul_cc or "Moyenne arithmétique")
        )

        if methode == "Moyenne pondérée":
            somme_produits = sum(w * n for w, n in valeurs)
            somme_coeffs = sum(w for w, _ in valeurs) or 1
            moyenne = somme_produits / somme_coeffs
        elif methode == "Moyenne des N meilleures notes":
            nb = int(
                formula.nb_meilleures_notes_cc
                if formula and formula.nb_meilleures_notes_cc
                else (setting.nb_meilleures_notes_cc or 2)
            )
            if nb <= 0:
                frappe.throw(_("Le nombre de meilleures notes CC (N) doit être supérieur à 0."))
            meilleures = sorted((n for _, n in valeurs), reverse=True)[:nb]
            moyenne = sum(meilleures) / len(meilleures)
        else:
            moyenne = sum(n for _, n in valeurs) / len(valeurs)

        self.note_cc_moyenne = round(moyenne, 2)
        self.cc_saisi = 1

    # ------------------------------------------------------------------ #
    #  Note d'examen retenue
    # ------------------------------------------------------------------ #
    def calculer_note_examen_active(self):
        """Note retenue = max(note examen, note rattrapage). Les deux notes sont conservées."""
        examen = self.note_examen if self.examen_saisi else None
        rattrapage = self.note_examen_rattrapage if self.rattrapage_saisi else None

        if rattrapage is not None:
            self.note_examen_active = round(max(examen or 0, rattrapage), 2)
        elif examen is not None:
            self.note_examen_active = round(examen, 2)
        else:
            self.note_examen_active = None

    # ------------------------------------------------------------------ #
    #  Note finale selon la formule configurée
    # ------------------------------------------------------------------ #
    def _note_composante(self, composante):
        mapping = {
            "Controle Continu(CC)": self.note_cc_moyenne if self.cc_saisi else None,
            "Examen": self.note_examen_active if (self.examen_saisi or self.rattrapage_saisi) else None,
            "Travaux Pratique (TP)": self.note_tp if self.tp_saisi else None,
            "Rapport": self.note_rapport,
            "Competence": self.note_competence,
        }
        return mapping.get(composante)

    def _ctx_composantes(self):
        return {
            "Controle Continu(CC)": self._note_composante("Controle Continu(CC)"),
            "Examen": self._note_composante("Examen"),
            "Travaux Pratique (TP)": self._note_composante("Travaux Pratique (TP)"),
            "Rapport": self._note_composante("Rapport"),
            "Competence": self._note_composante("Competence"),
        }

    def calculer_note_finale(self):
        """Calcule la note finale selon la formule active du cycle (Grade Formula)."""
        formula = None
        if self.student:
            formula = get_cycle_formula(get_student_cycle(self.student))

        if formula:
            note_finale, note_pct = calculer_note_ue(self._ctx_composantes(), formula)
            if note_finale is None:
                self.note_finale = None
                self.note_pct = 0
                return
            self.note_finale = note_finale
            self.note_pct = note_pct
            return

        setting = frappe.get_single("Udshed Setting")
        formules = [f for f in setting.formule_notes if f.type_ue == self.type_ue]

        if not formules:
            frappe.throw(
                _("Aucune formule trouvée pour le type UE <b>{0}</b>. Vérifiez la configuration dans Udshed Setting.").format(
                    self.type_ue
                )
            )

        notes = []
        for formule in formules:
            note = self._note_composante(formule.composante)
            if note is None:
                self.note_finale = None
                self.note_pct = 0
                return
            notes.append((note, formule.pourcentage))

        note_finale = 0
        for note, pourcentage in notes:
            note_finale += (note / NOTE_MAX) * pourcentage

        self.note_finale = round(note_finale * NOTE_MAX / 100, 2)
        self.note_pct = round(note_finale, 2)

    # ------------------------------------------------------------------ #
    #  Grade / point / mention
    # ------------------------------------------------------------------ #
    def determiner_grade(self):
        if not self.note_finale:
            self.grade = None
            self.point = None
            self.mention = None
            return

        setting = frappe.get_single("Udshed Setting")
        for g in setting.grille_grades:
            if g.note_min <= self.note_pct <= g.note_max:
                self.grade = g.grade
                self.point = g.point
                self.mention = g.mention
                return

        frappe.throw(
            _("Aucun grade trouvé pour la note <b>{0}%</b>. Vérifiez la grille des grades dans Udshed Setting.").format(
                self.note_pct
            )
        )
=======
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
>>>>>>> origin/feat/Eval-Note
