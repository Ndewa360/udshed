# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Stages, mémoires et soutenances.

- Un sujet proposé attend la VALIDATION de la coordination (décision humaine) :
  il apparaît dans sa file « À faire », avec relances puis escalade au doyen.
- La décision est notifiée à l'étudiant et à l'encadrant.
- Une soutenance programmée est notifiée à l'étudiant et au jury, avec un rappel
  la veille ; une soutenance tenue fait passer le travail à « Soutenu ».
"""

import frappe
from frappe import _
from frappe.utils import format_datetime, get_datetime, now, now_datetime

from udshed.notifications import emettre
from udshed.notifications.attentes import _user_enseignant, coordination, utilisateur_etudiant

ROLES_DECISION = ("System Manager", "Coordonateur", "Doyen", "Vice-Doyen")


def _etudiant(student):
	s = frappe.db.get_value("Student", student, ["utilisateur", "email", "phone"], as_dict=True) or {}
	return {"user": s.get("utilisateur"), "email": s.get("email"), "phone": s.get("phone")}


def _enseignant(teacher):
	if not teacher:
		return None
	return _user_enseignant(teacher) or frappe.db.get_value("Teacher", teacher, "email")


def valider_stage(doc):
	if doc.date_debut and doc.date_fin and doc.date_fin < doc.date_debut:
		frappe.throw(_("La date de fin précède la date de début."))
	avant = doc.get_doc_before_save()
	ancien = avant.statut if avant else None
	if doc.statut in ("Validé", "Refusé") and ancien != doc.statut:
		if frappe.session.user != "Administrator" and not set(frappe.get_roles()) & set(ROLES_DECISION):
			frappe.throw(_("La validation d'un sujet revient à la coordination ou au doyen."), frappe.PermissionError)
		doc.valide_par = frappe.session.user
		doc.valide_le = now()


def apres_stage(doc):
	avant = doc.get_doc_before_save()
	ancien = avant.statut if avant else None
	if ancien == doc.statut:
		return
	if doc.statut == "Proposé":
		emettre("stage_a_valider", coordination(doc.filiere), _("{0} à valider : {1}").format(doc.type_travail, doc.sujet),
				_("Proposé pour {0}.").format(doc.nom_etudiant or doc.student), reference=("Stage Etudiant", doc.name),
				cle=f"{doc.name}:propose")
	elif doc.statut in ("Validé", "Refusé"):
		message = (_("Votre sujet « {0} » est validé.").format(doc.sujet) if doc.statut == "Validé"
				   else _("Votre sujet « {0} » est refusé : {1}").format(doc.sujet, doc.commentaire or ""))
		emettre("stage_decision", [_etudiant(doc.student), _enseignant(doc.encadrant_academique)],
				_("{0} : {1}").format(doc.type_travail, doc.statut.lower()), message,
				reference=("Stage Etudiant", doc.name), lien="/app/mon-espace-etudiant", cle=f"{doc.name}:{doc.statut}")


def valider_soutenance(doc):
	statut_stage = frappe.db.get_value("Stage Etudiant", doc.stage, "statut")
	if statut_stage in ("Proposé", "Refusé"):
		frappe.throw(_("Le sujet doit être validé avant de programmer la soutenance."))
	if not doc.jury:
		frappe.throw(_("Composez le jury de soutenance."))
	if not any(m.role == "Président" for m in doc.jury):
		frappe.throw(_("Le jury doit avoir un président."))
	if doc.is_new() and doc.statut == "Programmée" and get_datetime(doc.date_soutenance) < now_datetime():
		frappe.throw(_("La date de soutenance est passée."))
	if doc.statut == "Tenue" and doc.note is None:
		frappe.throw(_("Indiquez la note de la soutenance."))


def apres_soutenance(doc):
	avant = doc.get_doc_before_save()
	if doc.statut == "Tenue" and (not avant or avant.statut != "Tenue"):
		frappe.db.set_value("Stage Etudiant", doc.stage, "statut", "Soutenu")
		return
	if doc.statut != "Programmée":
		return
	if avant and get_datetime(avant.date_soutenance) == get_datetime(doc.date_soutenance) and avant.salle == doc.salle:
		return
	quand = format_datetime(doc.date_soutenance, "dd/MM/yyyy HH:mm")
	dest = [_etudiant(doc.student)] + [_enseignant(m.enseignant) for m in doc.jury]
	emettre("soutenance_programmee", dest, _("Soutenance le {0}").format(quand),
			_("« {0} »{1}.").format(doc.sujet or "", _(", salle {0}").format(doc.salle) if doc.salle else ""),
			reference=("Soutenance", doc.name), cle=f"{doc.name}:{doc.date_soutenance}")


def rappel_soutenances(jour=None):
	from frappe.utils import add_days, getdate, nowdate

	demain = add_days(getdate(jour or nowdate()), 1)
	n = 0
	for s in frappe.get_all("Soutenance", filters={"statut": "Programmée", "date_soutenance": [
			"between", [f"{demain} 00:00:00", f"{demain} 23:59:59"]]}, pluck="name"):
		doc = frappe.get_doc("Soutenance", s)
		dest = [_etudiant(doc.student)] + [_enseignant(m.enseignant) for m in doc.jury]
		n += emettre("soutenance_programmee", dest, _("Rappel : soutenance demain à {0}").format(
			format_datetime(doc.date_soutenance, "HH:mm")), _("« {0} »").format(doc.sujet or ""),
			reference=("Soutenance", doc.name), cle=f"{doc.name}:rappel:{demain}")
	return n
