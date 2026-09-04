import frappe
from frappe import _
from frappe.model.document import Document

from udshed.grade_calculation import (
    calculer_note_ue,
    combinaison_detectee,
    combinaison_type_ue,
    determiner_statut_ue,
    get_formula,
    get_student_cycle,
)

NOTE_MAX = 20


class SessionExamenNote(Document):

    def _formule_note(self):
        """Formule active du cycle de l'étudiant pour la combinaison détectée.

        La combinaison est détectée à partir des composantes effectivement
        renseignées (CC, CCTP, EXAMTP, EXAM...). À défaut de formule pour la
        combinaison détectée, on retombe sur la combinaison du type d'UE
        uniquement si la saisie est partielle (composantes renseignées
        comprises dans la combinaison attendue). Une combinaison détectée
        non configurée (ex. CC + CCTP + EXAM sans Grade Formula) ne donne
        aucune formule : la note finale reste alors indéterminée plutôt que
        d'être calculée avec des composantes ignorées.
        """
        if not self.student:
            return None
        cycle = get_student_cycle(self.student)
        remplis = self.composantes_remplies()
        if remplis:
            formula = get_formula(cycle, combinaison_detectee(remplis))
            if formula:
                return formula
            attendue = combinaison_type_ue(self.type_ue)
            if set(remplis).issubset(attendue.split(" + ")):
                return get_formula(cycle, attendue)
            return None
        return get_formula(cycle, combinaison_type_ue(self.type_ue))

    def composantes_remplies(self):
        """Labels des composantes effectivement renseignées (sans doublon).

        La source de vérité est le drapeau *saisi : le stockage Currency
        ramène les notes non saisies à 0.0, un 0 par défaut ne compte donc
        jamais comme une composante remplie.

        Returns:
            list[str]: labels dans l'ordre canonique du moteur
        """
        remplis = []
        if self.cc_saisi:
            remplis.append("Controle Continu(CC)")
        if self.cctp_saisi:
            remplis.append("Controle Continu Travaux Pratiques(CCTP)")
        if self.examtp_saisi:
            remplis.append("Examen Travaux Pratiques(EXAMTP)")
        if self.examen_saisi or self.rattrapage_saisi:
            remplis.append("Examen")
        if self.tp_saisi:
            remplis.append("Travaux Pratique (TP)")
        if self.note_rapport:
            remplis.append("Rapport")
        if self.note_competence:
            remplis.append("Competence")
        return remplis

    def combinaison_detectee(self):
        """Combinaison canonique détectée des composantes renseignées."""
        return combinaison_detectee(self.composantes_remplies())

    def formule_manquante(self):
        """Vrai si une combinaison renseignée n'a aucune formule configurée."""
        if not self.composantes_remplies():
            return False
        return self._formule_note() is None

    def validate(self):
        self.remplir_filiere_niveau()
        self.deriver_drapeaux_saisie()
        self.valider_saisie()
        self.calculer_note_cc_moyenne()
        self.calculer_note_examen_active()
        self.calculer_note_finale()
        self.determiner_grade()

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
        """Déduit les drapeaux *saisi des valeurs réellement présentes (cohérence multi-canal).

        Le stockage Currency ramène les notes non saisies à 0.0 : un drapeau
        n'est jamais dérivé d'un simple « non nul » (0.0 par défaut ≠ note
        saisie). Il est promu par une valeur strictement positive, et posé ou
        levé explicitement par les flux d'enregistrement pour les notes nulles.
        """
        self.cc_saisi = 1 if any(row.note_cc is not None for row in self.notes_cc) else 0
        if self.note_cctp:
            self.cctp_saisi = 1
        if self.note_examtp:
            self.examtp_saisi = 1
        if self.note_examen:
            self.examen_saisi = 1
        if self.note_examen_rattrapage:
            self.rattrapage_saisi = 1
        if self.note_tp:
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
            ("note_cctp", "CCTP"),
            ("note_examtp", "EXAMTP"),
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

        if methode == "Moyenne des N meilleures notes":
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
            "Controle Continu Travaux Pratiques(CCTP)": self.note_cctp if self.cctp_saisi else None,
            "Examen": self.note_examen_active if (self.examen_saisi or self.rattrapage_saisi) else None,
            "Examen Travaux Pratiques(EXAMTP)": self.note_examtp if self.examtp_saisi else None,
            "Travaux Pratique (TP)": self.note_tp if self.tp_saisi else None,
            "Rapport": self.note_rapport,
            "Competence": self.note_competence,
        }
        return mapping.get(composante)

    def _ctx_composantes(self):
        return {
            "Controle Continu(CC)": self._note_composante("Controle Continu(CC)"),
            "Controle Continu Travaux Pratiques(CCTP)": self._note_composante("Controle Continu Travaux Pratiques(CCTP)"),
            "Examen": self._note_composante("Examen"),
            "Examen Travaux Pratiques(EXAMTP)": self._note_composante("Examen Travaux Pratiques(EXAMTP)"),
            "Travaux Pratique (TP)": self._note_composante("Travaux Pratique (TP)"),
            "Rapport": self._note_composante("Rapport"),
            "Competence": self._note_composante("Competence"),
        }

    def calculer_note_finale(self):
        """Calcule la note finale selon la formule correspondant à la combinaison détectée.

        La formule provient exclusivement de la Grade Formula : aucune formule
        n'est reconstruite localement. Si la combinaison détectée n'a pas de
        formule configurée (ex. CC + CCTP + EXAM sans Grade Formula), la note
        finale reste indéterminée plutôt que d'être calculée en ignorant les
        composantes saisies.
        """
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

        self.note_finale = None
        self.note_pct = 0

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
