# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import formatdate, getdate, nowdate

STATUT_PLANIFIEE = "Planifiée"
STATUT_OUVERTE = "Ouverte"
STATUT_FERMEE = "Fermée"


class SessionReinscription(Document):
	_DOCTYPE_NAME = "SessionReinscription"

	def validate(self):
		if self.date_ouverture and self.date_cloture:
			if self.date_ouverture >= self.date_cloture:
				frappe.throw("La date d'ouverture doit être antérieure à la date de clôture")

		self.verifier_cibles()

		if self.statut == STATUT_OUVERTE:
			self.verifier_session_unique_ouverte()
			if self.has_value_changed("statut") or self.has_value_changed("date_cloture"):
				self.verifier_periode_en_cours()

	def verifier_session_unique_ouverte(self):
		"""Une seule session de réinscription peut être ouverte à la fois"""
		autre_ouverte = frappe.db.exists("Session Reinscription", {
			"statut": "Ouverte",
			"name": ["!=", self.name]
		})
		if autre_ouverte:
			frappe.throw("Une autre session de réinscription est déjà ouverte. Fermez-la avant d'en ouvrir une nouvelle.")

	def verifier_periode_en_cours(self):
		"""Une session ne s'ouvre que pendant sa période (sinon : statut Planifiée)."""
		jour = getdate(nowdate())
		if jour > getdate(self.date_cloture):
			frappe.throw(
				"Impossible d'ouvrir la session : sa date de clôture ({0}) est dépassée. "
				"Modifiez les dates de la période.".format(formatdate(self.date_cloture))
			)
		if jour < getdate(self.date_ouverture):
			frappe.throw(
				"La période commence le {0} : enregistrez la session au statut « Planifiée », "
				"elle sera ouverte automatiquement à cette date.".format(formatdate(self.date_ouverture))
			)

	def verifier_cibles(self):
		vues = set()
		for row in self.get("cibles") or []:
			if not row.filiere and not row.niveau:
				frappe.throw("Ligne {0} du ciblage : renseignez une filière, un niveau ou les deux.".format(row.idx))
			cle = (row.filiere or "", row.niveau or "")
			if cle in vues:
				frappe.throw("Ligne {0} du ciblage : cette filière / ce niveau est déjà listé.".format(row.idx))
			vues.add(cle)

	def concerne(self, filiere, niveau):
		"""True si la session s'adresse à un étudiant de cette filière / ce niveau suivi."""
		cibles = self.get("cibles") or []
		if not cibles:
			return True
		return any(
			(not row.filiere or row.filiere == filiere) and (not row.niveau or row.niveau == niveau)
			for row in cibles
		)


def verifier_session_utilisable(session_name, filiere=None, niveau=None):
	"""Lève une erreur explicite si la session ne peut pas recevoir de réinscription.

	Contrôles : statut « Ouverte », date du jour dans la période, ciblage
	filière / niveau suivi (si `filiere` est fourni).

	Returns:
		Document: la Session Reinscription
	"""
	if not session_name or not frappe.db.exists("Session Reinscription", session_name):
		frappe.throw("Session de réinscription invalide.")

	session = frappe.get_doc("Session Reinscription", session_name)
	if session.statut != STATUT_OUVERTE:
		frappe.throw("La session de réinscription {0} n'est pas ouverte.".format(session.name))

	jour = getdate(nowdate())
	if jour < getdate(session.date_ouverture):
		frappe.throw(
			"La période de réinscription n'a pas encore commencé (ouverture le {0}).".format(
				formatdate(session.date_ouverture)
			)
		)
	if jour > getdate(session.date_cloture):
		frappe.throw(
			"La période de réinscription est close depuis le {0}.".format(formatdate(session.date_cloture))
		)

	if filiere is not None and not session.concerne(filiere, niveau):
		frappe.throw(
			"La session de réinscription {0} ne concerne pas votre filière / niveau ({1} — {2}).".format(
				session.name, filiere or "—", niveau or "—"
			)
		)
	return session


def sessions_utilisables(filiere=None, niveau=None):
	"""Sessions ouvertes, dans leur période et (si fourni) ciblant cette filière / ce niveau."""
	jour = getdate(nowdate())
	noms = frappe.get_all(
		"Session Reinscription",
		filters={
			"statut": STATUT_OUVERTE,
			"date_ouverture": ["<=", jour],
			"date_cloture": [">=", jour],
		},
		pluck="name",
	)
	sessions = [frappe.get_doc("Session Reinscription", n) for n in noms]
	if filiere is not None:
		sessions = [s for s in sessions if s.concerne(filiere, niveau)]
	return sessions


def mettre_a_jour_statuts(jour=None):
	"""Applique les dates : Ouverte -> Fermée après la clôture, Planifiée -> Ouverte à l'ouverture.

	Appelée chaque jour par le planificateur (udshed.udshed.tasks.daily).
	Une session fermée à la main reste fermée : seules les sessions
	« Planifiée » sont ouvertes automatiquement.
	"""
	jour = getdate(jour or nowdate())

	for name in frappe.get_all(
		"Session Reinscription",
		filters={"statut": STATUT_OUVERTE, "date_cloture": ["<", jour]},
		pluck="name",
	):
		try:
			doc = frappe.get_doc("Session Reinscription", name)
			doc.statut = STATUT_FERMEE
			doc.save(ignore_permissions=True)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"Session Reinscription Auto-Close {name}")

	for name in frappe.get_all(
		"Session Reinscription",
		filters={
			"statut": STATUT_PLANIFIEE,
			"date_ouverture": ["<=", jour],
			"date_cloture": [">=", jour],
		},
		pluck="name",
		order_by="date_ouverture asc",
	):
		autre = frappe.db.exists("Session Reinscription", {"statut": STATUT_OUVERTE})
		if autre:
			frappe.log_error(
				f"Impossible d'ouvrir la session {name} : la session {autre} est déjà ouverte.",
				"Session Reinscription Auto-Open",
			)
			continue
		try:
			doc = frappe.get_doc("Session Reinscription", name)
			doc.statut = STATUT_OUVERTE
			doc.save(ignore_permissions=True)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"Session Reinscription Auto-Open {name}")
