# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Actions en attente : file « À faire », relances et escalades.

Une ATTENTE est une action qu'une personne doit faire, déduite de l'état des
données (jamais saisie à la main) :
  - `responsables` : qui doit agir (file « À faire », relances) ;
  - `escalade` : qui prévenir si rien n'est fait après le délai de la règle ;
  - `depuis` : début de l'attente (date de la demande, de la fin de période…).

Dès que l'action est faite, l'attente disparaît d'elle-même : la file se vide et
les relances s'arrêtent. Les délais viennent de la règle de notification du même
code (modifiables par l'administrateur).

Les décisions qui engagent l'établissement restent humaines (admission,
dérogation, correction de note, délibération, publication, validation d'un
stage) : udshed les prépare, les signale et relance, mais ne les prend pas.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, getdate, now_datetime, nowdate

from udshed.notifications import emettre, regle
from udshed.utils import perimetre

DAA = "Directeur des Affaires Académiques"


# ---------------------------------------------------------------------- #
#  Destinataires par fonction
# ---------------------------------------------------------------------- #
def _user_enseignant(teacher):
	if not teacher:
		return None
	t = frappe.db.get_value("Teacher", teacher, ["user", "email"], as_dict=True) or {}
	user = t.get("user") or (t.get("email") if t.get("email") and frappe.db.exists("User", t.get("email")) else None)
	return user


def coordination(filiere):
	"""Coordinateurs de la filière (coordinateur de département et des niveaux)."""
	if not filiere:
		return []
	teachers = {frappe.db.get_value("Field of study", filiere, "department_coordinator")}
	teachers.update(frappe.get_all("Field of study Level", filters={"parent": filiere}, pluck="coordonateur"))
	return sorted(u for u in (_user_enseignant(t) for t in teachers if t) if u)


def scolarite(filiere):
	return perimetre.destinataires(("Agent de scolarité", "Registration Manager"), filiere)


def doyens(filiere=None, faculte=None):
	faculte = faculte or perimetre.faculte_de_filiere(filiere)
	if not faculte:
		return []
	d = frappe.db.get_value("Faculty", faculte, ["doyen", "vice_doyen"], as_dict=True) or {}
	return [u for u in (d.get("doyen"), d.get("vice_doyen")) if u]


def daa():
	return perimetre.destinataires((DAA,))


def utilisateur_etudiant(student):
	return frappe.db.get_value("Student", student, "utilisateur") if student else None


def enseignants_du_cours(teaching_unit):
	teachers = set(frappe.get_all("Course Teacher Item", filters={"parent": teaching_unit}, pluck="enseignant"))
	return sorted(u for u in (_user_enseignant(t) for t in teachers) if u)


def _attente(code, groupe, titre, reference, responsables, depuis, lien, escalade=None, critique=False):
	return frappe._dict(code=code, groupe=groupe, titre=titre, reference=reference,
						responsables=sorted({u for u in responsables if u}), escalade=sorted({u for u in (escalade or []) if u}),
						depuis=getdate(depuis), lien=lien, critique=critique)


# ---------------------------------------------------------------------- #
#  Fournisseurs
# ---------------------------------------------------------------------- #
def _requetes():
	for r in frappe.get_all("Requete Etudiant", filters={"statut": ["in", ["Soumise", "En traitement"]]},
							fields=["name", "student", "objet", "type_requete", "statut", "creation", "traite_par",
									"traite_le"]):
		filiere = perimetre.filiere_etudiant(r.student)
		if r.statut == "Soumise":
			yield _attente("requete_soumise", _("Requêtes à prendre en charge"), _("Requête « {0} »").format(r.objet),
						   ("Requete Etudiant", r.name), scolarite(filiere), r.creation, f"/app/requete-etudiant/{r.name}",
						   escalade=doyens(filiere))
		else:
			yield _attente("requete_soumise", _("Requêtes en cours à répondre"), _("Requête « {0} »").format(r.objet),
						   ("Requete Etudiant", r.name), [r.traite_par] if r.traite_par else scolarite(filiere),
						   r.traite_le or r.creation, f"/app/requete-etudiant/{r.name}", escalade=doyens(filiere))


ROLES_ACTES = ("Responsable Diplomation", "Agent de scolarité", "Doyen", "Vice-Doyen")


def _actes():
	for a in frappe.get_all("Acte Academique", filters={"statut": ["in", ["Demandé", "Prêt à retirer"]]},
							fields=["name", "student", "type_acte", "statut", "demande_le", "traite_le", "creation"]):
		filiere = perimetre.filiere_etudiant(a.student)
		if a.statut == "Demandé":
			yield _attente("acte_demande", _("Actes à délivrer"), _("{0} demandé").format(a.type_acte),
						   ("Acte Academique", a.name), perimetre.destinataires(ROLES_ACTES, filiere),
						   a.demande_le or a.creation, f"/app/acte-academique/{a.name}", escalade=doyens(filiere))
		else:
			yield _attente("acte_a_retirer", _("Documents prêts à retirer"),
						   _("{0} prêt à retirer").format(a.type_acte), ("Acte Academique", a.name),
						   [utilisateur_etudiant(a.student)], a.traite_le or a.creation, "/app/mon-espace-etudiant")


def _derogations():
	for d in frappe.get_all("Derogation Saisie", filters={"statut": "Demandée"},
							fields=["name", "intitule", "teaching_unit", "faculte", "filiere", "demande_le", "creation"]):
		yield _attente("derogation_demandee", _("Dérogations de saisie à décider"),
					   _("Dérogation : {0}").format(d.intitule or d.teaching_unit), ("Derogation Saisie", d.name),
					   doyens(d.filiere, d.faculte), d.demande_le or d.creation, f"/app/derogation-saisie/{d.name}",
					   escalade=daa(), critique=True)


def _corrections():
	for c in frappe.get_all("Correction Note", filters={"statut": "En attente"},
							fields=["name", "student", "teaching_unit", "creation"]):
		filiere = perimetre.filiere_etudiant(c.student)
		matiere = frappe.db.get_value("Teaching Unit", c.teaching_unit, "intitule_cours") or c.teaching_unit
		yield _attente("correction_demandee", _("Corrections de notes à approuver"),
					   _("Correction de note : {0}").format(matiere), ("Correction Note", c.name),
					   coordination(filiere) + perimetre.destinataires(("Registration Manager",), filiere),
					   c.creation, f"/app/correction-note/{c.name}", escalade=doyens(filiere), critique=True)


def _candidatures():
	for c in frappe.get_all("Session Inscription Candidate",
							filters={"candidature_status": ["in", ["En attente", "Dossier en cours d'examen"]],
									 "mode_admission": ["!=", "Concours"]},
							fields=["name", "filiere", "full_name", "creation"]):
		yield _attente("candidature_a_etudier", _("Candidatures à étudier"),
					   _("Candidature de {0}").format(c.full_name or c.name), ("Session Inscription Candidate", c.name),
					   coordination(c.filiere) + perimetre.destinataires(("Registration Manager",), c.filiere),
					   c.creation, "/desk/consultation-candidatures", escalade=doyens(c.filiere), critique=True)


def _saisies_en_retard():
	from udshed.utils.periode_saisie import TYPES

	maintenant = now_datetime()
	for p in frappe.get_all("Periode Saisie Notes", filters={"fermeture": ["<", maintenant]},
							fields=["name", "academic_year", "semestre", "type_evaluation", "faculte", "fermeture"]):
		if date_diff(maintenant, p.fermeture) > 60:
			continue  # période ancienne : hors du suivi courant
		for tu in _ues_de_la_periode(p):
			if frappe.db.exists("Confirmation Saisie", {"teaching_unit": tu.name, "type_evaluation": p.type_evaluation,
														"academic_year": p.academic_year, "semestre": p.semestre}):
				continue
			filieres = frappe.get_all("Course Field of study level item", filters={"parent": tu.name}, pluck="filiere")
			filiere = filieres[0] if filieres else None
			yield _attente("saisie_retard", _("Saisies de notes en retard"),
						   _("{0} — {1} non confirmé").format(tu.intitule_cours or tu.name, p.type_evaluation.lower()),
						   ("Teaching Unit", tu.name), enseignants_du_cours(tu.name) + coordination(filiere),
						   p.fermeture, "/desk/note-udshed", escalade=doyens(filiere))


def _ues_de_la_periode(p):
	for tu in frappe.get_all("Teaching Unit", filters={"academic_year": p.academic_year, "semestre": p.semestre},
							 fields=["name", "intitule_cours"]):
		if p.faculte:
			filieres = frappe.get_all("Course Field of study level item", filters={"parent": tu.name}, pluck="filiere")
			if not any(frappe.db.get_value("Field of study", f, "faculte") == p.faculte for f in filieres):
				continue
		yield tu


def _sessions_a_publier():
	for s in frappe.get_all("Session Examen", filters={"statut": "Brouillon", "date_de_fin": ["<", nowdate()]},
							fields=["name", "date_de_fin", "type_dexamen", "semestre", "publier_le"]):
		if s.publier_le:
			continue  # publication programmée : la décision est prise
		total = frappe.db.count("Session Examen Note", {"session_examen": s.name})
		if not total or frappe.db.count("Session Examen Note", {"session_examen": s.name,
																"statut": ["not in", ["Validé", "Publié"]]}):
			continue
		filieres = frappe.get_all("Session Examen Field of study level", filters={"parent": s.name}, pluck="filiere")
		resp, esc = [], []
		for f in set(filieres):
			resp += coordination(f) + perimetre.destinataires(("Registration Manager",), f)
			esc += doyens(f)
		yield _attente("session_a_publier", _("Sessions prêtes à publier"),
					   _("{0} ({1}) : notes validées, publication à décider").format(s.type_dexamen, s.semestre),
					   ("Session Examen", s.name), resp, s.date_de_fin, f"/app/session-examen/{s.name}", escalade=esc,
					   critique=True)


def _deliberations():
	for d in frappe.get_all("Deliberation Jury", filters={"statut": "Brouillon"},
							fields=["name", "filiere", "niveau", "creation", "date_deliberation"]):
		niveau = frappe.db.get_value("Field of study Level", d.niveau, "level") or d.niveau
		nom = frappe.db.get_value("Field of study", d.filiere, "name_of_field") or d.filiere
		yield _attente("deliberation_a_tenir", _("Délibérations à tenir"), _("Jury : {0} — {1}").format(nom, niveau),
					   ("Deliberation Jury", d.name), doyens(d.filiere), d.creation,
					   f"/app/deliberation-jury/{d.name}", escalade=daa(), critique=True)


def _stages():
	for s in frappe.get_all("Stage Etudiant", filters={"statut": "Proposé"},
							fields=["name", "filiere", "sujet", "creation"]):
		yield _attente("stage_a_valider", _("Stages et mémoires à valider"), _("Sujet : {0}").format(s.sujet),
					   ("Stage Etudiant", s.name), coordination(s.filiere), s.creation,
					   f"/app/stage-etudiant/{s.name}", escalade=doyens(s.filiere), critique=True)


def _impayes():
	for e in frappe.get_all("Echeance Etudiant", filters={"statut": "En retard"},
							fields=["name", "student", "libelle", "reste", "date_echeance"]):
		yield _attente("frais_impaye", _("Frais de scolarité en retard"),
					   _("{0} : reste {1}").format(e.libelle, frappe.format(e.reste, {"fieldtype": "Currency"})),
					   ("Echeance Etudiant", e.name), [utilisateur_etudiant(e.student)], e.date_echeance,
					   "/app/mon-espace-etudiant")


FOURNISSEURS = [_requetes, _actes, _derogations, _corrections, _candidatures, _saisies_en_retard,
				_sessions_a_publier, _deliberations, _stages, _impayes]


def toutes():
	res = []
	for f in FOURNISSEURS:
		try:
			res.extend(f())
		except Exception:
			frappe.log_error(title=f"udshed: attentes {f.__name__}")
	return res


# ---------------------------------------------------------------------- #
#  File « À faire »
# ---------------------------------------------------------------------- #
def a_faire(user=None):
	"""Groupes d'actions en attente pour l'utilisateur : les siennes, puis celles
	de son équipe qui ont dépassé le délai d'escalade."""
	user = user or frappe.session.user
	aujourdhui = getdate(nowdate())
	groupes = {}
	for a in toutes():
		age = (aujourdhui - a.depuis).days
		r = regle(a.code) or {}
		mien = user in a.responsables
		escalade = (not mien and user in a.escalade and cint(r.get("escalade_jours"))
					and age >= cint(r.get("escalade_jours")))
		if not (mien or escalade):
			continue
		cle = (a.groupe, bool(escalade))
		g = groupes.setdefault(cle, {"groupe": a.groupe if mien else _("{0} (en retard dans votre périmètre)").format(a.groupe),
									  "nombre": 0, "en_retard": 0, "plus_ancien": 0, "critique": a.critique,
									  "escalade": bool(escalade), "elements": []})
		g["nombre"] += 1
		delai = cint(r.get("delai_relance_jours"))
		g["en_retard"] += 1 if delai and age >= delai else 0
		g["plus_ancien"] = max(g["plus_ancien"], age)
		if len(g["elements"]) < 8:
			g["elements"].append({"titre": a.titre, "lien": a.lien, "age": age})
	return sorted(groupes.values(), key=lambda g: (g["escalade"], not g["critique"], -g["plus_ancien"]))


# ---------------------------------------------------------------------- #
#  Relances et escalades (tâche quotidienne)
# ---------------------------------------------------------------------- #
def relancer(jour=None):
	aujourdhui = getdate(jour or nowdate())
	envoyes = 0
	for a in toutes():
		r = regle(a.code)
		if not r or not cint(r.actif):
			continue
		age = (aujourdhui - a.depuis).days
		delai, maxi, esc = cint(r.delai_relance_jours), cint(r.max_relances), cint(r.escalade_jours)
		ref = f"{a.reference[0]}:{a.reference[1]}"
		if delai and maxi and age >= delai:
			n = min(age // delai, maxi)
			envoyes += emettre(a.code, a.responsables, _("Rappel : {0}").format(a.titre),
							   _("Cette action vous attend depuis {0} jour(s).").format(age), reference=a.reference,
							   lien=a.lien, cle=f"relance:{ref}:{n}", relance=n)
		if esc and age >= esc and a.escalade:
			envoyes += emettre(a.code, a.escalade, _("En attente depuis {0} jours : {1}").format(age, a.titre),
							   _("Cette action relève de votre périmètre et n'a pas été faite malgré les relances."),
							   reference=a.reference, lien=a.lien, cle=f"escalade:{ref}", relance=99)
	return envoyes
