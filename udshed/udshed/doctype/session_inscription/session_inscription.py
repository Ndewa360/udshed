# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Campagne d'admission : année cible, période de dépôt, période d'inscription
des admis et centres d'examen (voir udshed/utils/campagne.py)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate

JOURS_INSCRIPTION_PAR_DEFAUT = 90


@frappe.whitelist(allow_guest=True)
def get_open_session():
	"""Campagne dont les dépôts sont ouverts aujourd'hui, et l'adresse du formulaire."""
	from udshed.utils.campagne import campagne_ouverte

	campagne = campagne_ouverte()
	if not campagne:
		return None
	return {"name": campagne.name, "academic_year": campagne.academic_year, "route": "candidature/new"}


class SessionInscription(Document):
	def validate(self):
		self.validate_dates()
		self.validate_unique_open_session()
		if not (self.titre or "").strip():
			self.titre = _("Candidatures {0}").format(self.academic_year)
		if not self.delai_finalisation or int(self.delai_finalisation) < 1:
			self.delai_finalisation = 15
		self._normaliser_centres()

	def before_save(self):
		# L'année cible d'une campagne qui a déjà reçu des candidatures ne change
		# plus : tous les dossiers, matricules et inscriptions en dépendent.
		avant = self.get_doc_before_save()
		if avant and avant.academic_year != self.academic_year and frappe.db.exists(
			"Session Inscription Candidate", {"session_inscription": self.name}
		):
			frappe.throw(_("Des candidatures existent déjà : l'année de rentrée de cette campagne ne peut plus changer."))

	def on_update(self):
		# Accueil et formulaire affichent l'état de la campagne : cache du site vidé.
		from frappe.website.utils import clear_cache

		clear_cache()

	def before_delete(self):
		if self.status == "Open":
			frappe.throw(_("Impossible de supprimer une campagne ouverte. Fermez-la d'abord."))

	def validate_dates(self):
		if getdate(self.closing_date) <= getdate(self.opening_date):
			frappe.throw(_("La clôture des dépôts doit être postérieure à leur ouverture."))
		if not self.date_limite_inscription:
			self.date_limite_inscription = add_days(self.closing_date, JOURS_INSCRIPTION_PAR_DEFAUT)
		if getdate(self.date_limite_inscription) < getdate(self.closing_date):
			frappe.throw(_("La date limite d'inscription des admis ne peut pas précéder la clôture des dépôts."))

	def validate_unique_open_session(self):
		if self.status == "Open":
			existing = frappe.db.exists("Session Inscription", {"status": "Open", "name": ("!=", self.name)})
			if existing:
				frappe.throw(_("La campagne {0} est déjà ouverte : fermez-la d'abord.").format(existing))

	def _normaliser_centres(self):
		lignes = []
		for ligne in (self.centres_examen or "").replace("\r", "").split("\n"):
			ligne = " ".join(ligne.split())
			if ligne and ligne not in lignes:
				lignes.append(ligne)
		self.centres_examen = "\n".join(lignes)

	@frappe.whitelist()
	def open_session(self):
		self.validate_unique_open_session()
		self.status = "Open"
		self.save()

	@frappe.whitelist()
	def close_session(self):
		self.status = "Closed"
		self.save()
