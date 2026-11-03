# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from udshed.api.progression import (
	CHAMPS_DECISION,
	STATUTS_AUTORISANT_REINSCRIPTION,
	ROLES_CORRECTION,
	niveau_existe,
)
from udshed.api.reregistration import get_next_academic_year


class ProgressionAcademique(Document):
	"""Progression d'un étudiant pour l'année qui suit `annee_source`.

	Créée / mise à jour uniquement par le calcul déclenché à la publication
	officielle des résultats (flag `calcul_automatique`). Toute autre
	modification du statut, de la filière ou du niveau est une correction de
	la scolarité : elle exige un motif et est historisée (track_changes).
	"""

	def validate(self):
		self.annee_cible = get_next_academic_year(self.annee_source)
		if self.student:
			nom, prenom = frappe.db.get_value("Student", self.student, ["nom", "prenom"]) or ("", "")
			self.nom_etudiant = f"{nom or ''} {prenom or ''}".strip()

		if not self.flags.calcul_automatique:
			if self.is_new() or any(self.has_value_changed(f) for f in CHAMPS_DECISION):
				self._enregistrer_correction()

		self._verifier_cible()

	def _enregistrer_correction(self):
		if not (set(frappe.get_roles()) & ROLES_CORRECTION) and frappe.session.user != "Administrator":
			frappe.throw(
				"Seule la scolarité peut corriger une progression académique.",
				frappe.PermissionError,
			)
		if self.reinscription:
			frappe.throw(
				"Cette progression a déjà servi à la réinscription {0} : elle ne peut plus être modifiée. "
				"Corrigez directement la réinscription.".format(self.reinscription)
			)
		if not (self.motif_correction or "").strip():
			frappe.throw("Indiquez le motif de la correction (champ « Motif de la correction »).")
		self.corrigee = 1
		self.corrigee_par = frappe.session.user
		self.date_correction = now_datetime()

	def _verifier_cible(self):
		if self.statut not in STATUTS_AUTORISANT_REINSCRIPTION:
			return
		if not self.filiere_cible or not self.niveau_cible:
			frappe.throw("Le statut « {0} » exige une filière et un niveau.".format(self.statut))
		filiere_dossier = frappe.db.get_value("Student", self.student, "filiere")
		if self.filiere_cible != filiere_dossier:
			frappe.throw(
				"La filière de réinscription doit être celle du dossier étudiant ({0}). "
				"Pour un changement de filière, modifiez d'abord le dossier étudiant.".format(filiere_dossier)
			)
		if not niveau_existe(self.filiere_cible, self.niveau_cible):
			frappe.throw(
				"Le niveau « {0} » n'existe pas dans la filière {1}.".format(self.niveau_cible, self.filiere_cible)
			)
