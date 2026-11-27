"""Périodes de saisie des notes, confirmation et dérogations.

Période en vigueur pour une évaluation (contrôle continu, examen de session normale, rattrapage),
dans cet ordre :
  1. la période propre à la session d'examen (Session Examen : ouverture / date limite) ;
  2. la période de la faculté de la filière (Periode Saisie Notes, faculté renseignée : doyen) ;
  3. la période de l'établissement (Periode Saisie Notes sans faculté : Directeur des Affaires
     Académiques) ;
  4. aucune période : saisie libre.

Sont soumis à la période les enseignants. La coordination, la scolarité et la direction
(doyen, vice-doyen, DAA) n'y sont pas soumis (reprise des PV papier, corrections).
Pendant la période, l'enseignant saisit et confirme librement. Après la date limite, il ne peut
plus enregistrer sans une dérogation accordée par le doyen ou le vice-doyen de la faculté.
"""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, now_datetime

TYPES = {"cc": "Contrôle continu", "examen": "Examen de session normale", "rattrapage": "Rattrapage"}
EXEMPTS = {"System Manager", "Coordonateur", "Planning Manager", "Registration Manager", "Agent de scolarité",
		   "Doyen", "Vice-Doyen", "Directeur des Affaires Académiques"}


def type_evaluation(mode):
	return TYPES.get(mode) or TYPES["examen"]


def soumis(user=None):
	user = user or frappe.session.user
	if user in ("Administrator", "Guest"):
		return False
	roles = set(frappe.get_roles(user))
	return "Teacher" in roles and not roles & EXEMPTS


def _jolie(dt):
	from udshed.utils.actes import date_longue

	d = get_datetime(dt)
	return f"{date_longue(d)} à {d.strftime('%H:%M')}"


def periode(academic_year, semestre, type_eval, filiere=None, session=None):
	"""{ouverture, fermeture, source} ou None (pas de période : saisie libre)."""
	if session and frappe.db.has_column("Session Examen", "saisie_ouverture"):
		s = frappe.db.get_value("Session Examen", session, ["saisie_ouverture", "saisie_fermeture"], as_dict=True)
		if s and s.saisie_ouverture and s.saisie_fermeture:
			return frappe._dict(ouverture=s.saisie_ouverture, fermeture=s.saisie_fermeture, source=_("session d'examen"))
	base = {"academic_year": academic_year, "semestre": semestre, "type_evaluation": type_eval}
	faculte = frappe.db.get_value("Field of study", filiere, "faculte") if filiere else None
	champs = ["ouverture", "fermeture"]
	if faculte:
		p = frappe.db.get_value("Periode Saisie Notes", {**base, "faculte": faculte}, champs, as_dict=True)
		if p:
			return frappe._dict(**p, source=_("faculté"))
	p = frappe.db.get_value("Periode Saisie Notes", {**base, "faculte": ["is", "not set"]}, champs, as_dict=True)
	if p:
		return frappe._dict(**p, source=_("établissement"))
	return None


def _enseignant(user=None):
	from udshed.api.planning_permission import _teacher_name

	return _teacher_name(user or frappe.session.user)


def derogation_active(academic_year, semestre, teaching_unit, type_eval, user=None):
	teacher = _enseignant(user)
	if not teacher:
		return None
	return frappe.db.get_value("Derogation Saisie", {
		"statut": "Accordée", "enseignant": teacher, "teaching_unit": teaching_unit, "type_evaluation": type_eval,
		"academic_year": academic_year, "semestre": semestre, "valable_jusqu_au": [">=", now_datetime()],
	}, ["name", "valable_jusqu_au"], as_dict=True)


def demande_en_cours(academic_year, semestre, teaching_unit, type_eval, user=None):
	teacher = _enseignant(user)
	if not teacher:
		return None
	return frappe.db.get_value("Derogation Saisie", {
		"statut": "Demandée", "enseignant": teacher, "teaching_unit": teaching_unit, "type_evaluation": type_eval,
		"academic_year": academic_year, "semestre": semestre}, "name")


def confirmation(academic_year, semestre, teaching_unit, type_eval, filiere=None, niveau=None):
	filtres = {"academic_year": academic_year, "semestre": semestre, "teaching_unit": teaching_unit,
			   "type_evaluation": type_eval}
	if filiere:
		filtres["filiere"] = filiere
	if niveau:
		filtres["niveau"] = niveau
	return frappe.db.get_value("Confirmation Saisie", filtres, ["name", "confirme_par", "confirme_le"], as_dict=True)


def etat(academic_year, semestre, teaching_unit, filiere, mode, session=None, niveau=None, user=None):
	"""État de la saisie pour l'écran et pour le contrôle serveur."""
	type_eval = type_evaluation(mode)
	p = periode(academic_year, semestre, type_eval, filiere, session)
	maintenant = now_datetime()
	est_soumis = soumis(user)
	res = frappe._dict(type_evaluation=type_eval, soumis=est_soumis, ouverte=True, fermee_apres_limite=False,
					   ouverture=p.ouverture if p else None, fermeture=p.fermeture if p else None,
					   source=p.source if p else None, derogation=None, demande=None,
					   confirmation=confirmation(academic_year, semestre, teaching_unit, type_eval, filiere, niveau))
	if not p:
		res.message = _("Aucune période de saisie n'est fixée pour cette évaluation : la saisie est libre.")
		return res
	if maintenant < get_datetime(p.ouverture):
		res.ouverte = False
		res.message = _("La saisie ({0}) ouvrira le {1}.").format(type_eval.lower(), _jolie(p.ouverture))
	elif maintenant > get_datetime(p.fermeture):
		res.ouverte = False
		res.fermee_apres_limite = True
		res.message = _("La saisie ({0}) est fermée depuis le {1}.").format(type_eval.lower(), _jolie(p.fermeture))
		if est_soumis:
			d = derogation_active(academic_year, semestre, teaching_unit, type_eval, user)
			if d:
				res.ouverte = True
				res.derogation = d
				res.message = _("Saisie rouverte par dérogation jusqu'au {0}.").format(_jolie(d.valable_jusqu_au))
			else:
				res.demande = demande_en_cours(academic_year, semestre, teaching_unit, type_eval, user)
	else:
		res.message = _("Saisie ouverte jusqu'au {0}.").format(_jolie(p.fermeture))
	if not est_soumis and not res.ouverte:
		res.ouverte = True
		res.message += " " + _("Votre rôle n'est pas soumis à la période de saisie.")
	return res


def exiger_saisie_ouverte(academic_year, semestre, teaching_unit, filiere, mode, session=None, user=None):
	e = etat(academic_year, semestre, teaching_unit, filiere, mode, session, user=user)
	if not e.ouverte:
		suite = _(" Demandez une réouverture au doyen ou au vice-doyen de la faculté.") if e.fermee_apres_limite else ""
		frappe.throw(e.message + suite, title=_("Saisie fermée"))
	return e


# ---------------------------------------------------------------------------
# Rappel quotidien : enseignants sans confirmation, période qui ferme sous 3 jours
# ---------------------------------------------------------------------------
def rappel_saisie():
	"""Rappels J-3 et J-1 : voir udshed.notifications.taches.saisie_rappels."""
	from udshed.notifications.taches import saisie_rappels

	return saisie_rappels()


def _ancien_rappel_saisie():
	maintenant = now_datetime()
	periodes = frappe.get_all("Periode Saisie Notes", filters={"fermeture": ["between", [maintenant, add_days(maintenant, 3)]]},
							  fields=["academic_year", "semestre", "type_evaluation", "faculte", "fermeture"])
	a_prevenir = {}
	for p in periodes:
		filtres_tu = {"academic_year": p.academic_year, "semestre": p.semestre}
		for tu in frappe.get_all("Teaching Unit", filters=filtres_tu, fields=["name", "intitule_cours"]):
			if p.faculte:
				filieres = frappe.get_all("Course Field of study level item", filters={"parent": tu.name}, pluck="filiere")
				if not any(frappe.db.get_value("Field of study", f, "faculte") == p.faculte for f in filieres):
					continue
			if frappe.db.exists("Confirmation Saisie", {"teaching_unit": tu.name, "type_evaluation": p.type_evaluation,
														"academic_year": p.academic_year, "semestre": p.semestre}):
				continue
			for teacher in set(frappe.get_all("Course Teacher Item", filters={"parent": tu.name}, pluck="enseignant")):
				email = frappe.db.get_value("Teacher", teacher, "email")
				if email:
					a_prevenir.setdefault(email, []).append(
						f"{tu.intitule_cours or tu.name} — {p.type_evaluation.lower()} (date limite : {_jolie(p.fermeture)})")
	for email, lignes in a_prevenir.items():
		_envoyer_rappel(email, lignes)
	return len(a_prevenir)


def _envoyer_rappel(email, lignes):
	try:
		frappe.sendmail(
			recipients=[email], subject=_("Rappel : saisie des notes à confirmer"),
			message="<p>" + _("Bonjour,") + "</p><p>" + _(
				"La période de saisie des notes ferme bientôt pour les évaluations suivantes, dont la saisie n'est pas "
				"encore confirmée :") + "</p><ul>" + "".join(f"<li>{frappe.utils.escape_html(l)}</li>" for l in lignes)
			+ "</ul><p>" + _("Après la date limite, toute nouvelle saisie demandera une dérogation du doyen.") + "</p>",
		)
	except Exception:
		frappe.log_error(title="udshed: rappel de saisie des notes")
