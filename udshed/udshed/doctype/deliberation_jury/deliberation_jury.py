# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Délibération du jury de fin d'année d'une classe (voir udshed/utils/deliberation.py)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from udshed.utils import deliberation

ROLES_JURY = {"System Manager", "Registration Manager", "Coordonateur"}


def _exiger_jury():
	if not (set(frappe.get_roles()) & ROLES_JURY):
		frappe.throw(_("Action réservée au jury (coordonnateur, responsable des admissions)."), frappe.PermissionError)


class DeliberationJury(Document):
	def validate(self):
		parent = frappe.db.get_value("Field of study Level", self.niveau, "parent")
		if parent and parent != self.filiere:
			frappe.throw(_("Le niveau choisi n'appartient pas à la filière {0}.").format(self.filiere))
		if self.points_jury_max is not None and not (0 <= flt(self.points_jury_max) <= 5):
			frappe.throw(_("Les points de jury doivent être compris entre 0 et 5 (sur 20)."))
		if self.seuil_abaisse and not (0 < flt(self.seuil_abaisse) < 20):
			frappe.throw(_("Le seuil abaissé doit être compris entre 0 et 20."))
		if self.pourcentage_credits_min and not (0 < flt(self.pourcentage_credits_min) <= 100):
			frappe.throw(_("Le pourcentage minimum de crédits doit être compris entre 0 et 100."))
		for d in self.decisions or []:
			if d.type_decision == deliberation.VALIDATION_UNITE and not (d.unite or d.matiere):
				frappe.throw(_("Ligne {0} : indiquez l'unité (ou la matière) validée par le jury.").format(d.idx))
			if not (d.motif or "").strip():
				frappe.throw(_("Ligne {0} : le motif de la décision est obligatoire.").format(d.idx))
		avant = self.get_doc_before_save()
		if avant and avant.statut == "Appliquée":
			# Une délibération appliquée se modifie après annulation (traçabilité).
			for champ in ("points_jury_max", "seuil_abaisse", "pourcentage_credits_min", "dette_max_credits"):
				if flt(avant.get(champ)) != flt(self.get(champ)):
					frappe.throw(_("Délibération appliquée : annulez l'application avant de modifier ses règles."))

	@frappe.whitelist()
	def simuler(self):
		_exiger_jury()
		return deliberation.simuler(self)

	@frappe.whitelist()
	def appliquer(self):
		_exiger_jury()
		if self.statut == "Appliquée":
			frappe.throw(_("Cette délibération est déjà appliquée."))
		return deliberation.appliquer(self)

	@frappe.whitelist()
	def annuler_application(self):
		_exiger_jury()
		if self.statut != "Appliquée":
			frappe.throw(_("Cette délibération n'est pas appliquée."))
		return deliberation.annuler(self)
