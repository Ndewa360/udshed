import frappe
from frappe import _
from frappe.model.document import Document

from udshed.grade_calculation import (
    calculer_note_ue,
    combinaison_type_ue,
    determiner_statut_ue,
    get_formula,
    get_student_cycle,
)

NOTE_MAX = 20


class SessionExamenNote(Document):

    def _formule_note(self):
        """Formule active du cycle de l'étudiant pour le type d'UE de la note."""
        if not self.student:
            return None
        cycle = get_student_cycle(self.student)
        return get_formula(cycle, combinaison_type_ue(self.type_ue))

    def validate(self):
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

        formula = self._formule_note()

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
        formula = self._formule_note()

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
        """Détermine grade, point, mention et type de résultat via le moteur.

        Utilise ``determiner_statut_ue`` (grille des grades de Grade Config) :
        la note est convertie sur 100 et comparée aux bornes de la grille.
        Le statut capitalise les crédits lorsque l'UE est validée (seuil du
        cycle) et que le grade correspond à des crédits capitalisables.
        """
        if not self.note_finale:
            self.grade = None
            self.point = None
            self.mention = None
            self.type_resultat = None
            self.capitalise = 0
            return

        statut = determiner_statut_ue(
            self.note_finale, get_student_cycle(self.student)
        )
        if statut["grade"] is None:
            frappe.throw(
                _("Aucun grade trouvé pour la note <b>{0}%</b>. Vérifiez la grille des grades dans Udshed Setting.").format(
                    self.note_pct
                )
            )

        self.grade = statut["grade"]
        self.point = statut["point"]
        self.mention = statut["mention"]
        self.type_resultat = statut["type_resultat"]
        self.capitalise = 1 if statut["capitalise"] else 0
