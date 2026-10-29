# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from udshed.grade_calculation import (
    SEUILS_DEFAUT,
    combinaison_formule,
    rendre_apercu,
    valider_formule,
)


class GradeFormula(Document):

    def before_validate(self):
        self.preciser_seuil_defaut()
        self.activer_premiere_formule()
        self.combinaison = combinaison_formule(self)

    def validate(self):
        valider_formule(self)
        self.verifier_unicite_combinaison()
        self.combinaison = combinaison_formule(self)
        self.apercu = rendre_apercu(self)

    # ------------------------------------------------------------------ #
    def preciser_seuil_defaut(self):
        """Applique le seuil de validation par défaut du cycle si vide."""
        if self.seuil_validation is None:
            self.seuil_validation = SEUILS_DEFAUT.get(self.cycle, 50)

    def activer_premiere_formule(self):
        """Active automatiquement la première formule créée pour un cycle."""
        if not self.is_new() or self.active:
            return
        existe = frappe.db.get_value(
            "Grade Formula",
            {"cycle": self.cycle},
            "name",
        )
        if not existe:
            self.active = 1

    def verifier_unicite_combinaison(self):
        """Une seule formule active est autorisée par (cycle, combinaison)."""
        if not self.active:
            return
        conflit = frappe.db.get_value(
            "Grade Formula",
            {
                "cycle": self.cycle,
                "active": 1,
                "combinaison": self.combinaison or "",
                "name": ["!=", self.name or ""],
            },
            "name",
        )
        if conflit:
            frappe.throw(
                _("Une formule active existe déjà pour le cycle <b>{0}</b> avec la combinaison "
                  "d'évaluations « {1} » : <b>{2}</b>. Modifiez la combinaison ou désactivez "
                  "l'autre formule.").format(self.cycle, self.combinaison or "", conflit)
            )
