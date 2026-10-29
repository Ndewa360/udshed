# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CopieExamen(Document):
    """Copie d'examen anonyme : aucun Champ d'identité étudiant.

    La copie est identifiée uniquement par son code d'anonymat. Le lien vers
    l'étudiant est porté par le document « Examen Anonymat » (confidentiel)
    auquel seul un rôle autorisé a accès.
    """

    def validate(self):
        if not self.examen_anonymat:
            frappe.throw(
                "La copie doit être rattachée à une fiche d'anonymat "
                "(Examen Anonymat) : c'est elle qui porte le code."
            )

        # Le code d'anonymat n'est pas une donnée de la copie : il est porté par
        # la fiche d'anonymat, seule source de vérité (et seule porteuse de
        # l'identité). Le recopier ici revenait à garder deux valeurs
        # indépendantes, qui divergeaient dès qu'une note saisie à la main
        # n'était pas recopiée : la fiche d'anonymat et la fiche de report
        # affichaient alors deux numéros différents, et la levée d'anonymat
        # perdait la note (jointure faite sur le code).
        code = frappe.db.get_value(
            "Examen Anonymat", self.examen_anonymat, "code_anonymat"
        )
        if not code:
            frappe.throw(
                "La fiche d'anonymat <b>{0}</b> n'a pas de code : impossible de "
                "numéroter la copie.".format(self.examen_anonymat)
            )
        self.code_anonymat = code

        if self.note_examen is not None and (self.note_examen < 0 or self.note_examen > 20):
            frappe.throw("La note d'examen doit être comprise entre 0 et 20.")