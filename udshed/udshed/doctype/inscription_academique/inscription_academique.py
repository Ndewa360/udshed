# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class InscriptionAcademique(Document):
    def validate(self):
        if not self.dossier_origine:
            self._valider_hors_candidature()
        self._update_candidate_status()

    def _valider_hors_candidature(self):
        """Inscription saisie par un responsable (arrivée en cours d'année,
        import) : les données nécessaires au dossier étudiant sont exigées."""
        manquants = [
            self.meta.get_label(champ)
            for champ in ("email", "date_naissance", "lieu_naissance", "telephone")
            if not self.get(champ)
        ]
        if manquants:
            frappe.throw(_("Champs obligatoires manquants : {0}").format(", ".join(manquants)))

        if len((self.nom_prenom or "").split()) < 2:
            frappe.throw(_("Renseignez le nom ET le prénom de l'étudiant (« NOM Prénom »)."))

        from udshed.api.inscription import _resolve_niveau_grid

        if not _resolve_niveau_grid(self.filiere, self.classe):
            niveaux = frappe.get_all(
                "Field of study Level", filters={"parent": self.filiere}, pluck="level"
            )
            frappe.throw(
                _("Niveau « {0} » inconnu pour la filière {1}. Niveaux possibles : {2}").format(
                    self.classe, self.filiere, ", ".join(n for n in niveaux if n) or "—"
                )
            )

    def _update_candidate_status(self):
        if self.dossier_origine:
            frappe.db.set_value(
                "Session Inscription Candidate",
                self.dossier_origine,
                "candidature_status",
                "Inscrit",
                update_modified=False,
            )
