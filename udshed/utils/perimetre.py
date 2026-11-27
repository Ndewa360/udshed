"""Périmètre de travail de chaque utilisateur, par filière.

- Agent de scolarité : les filières dont il est agent (fiche filière, tableau « Agents de
  scolarité »). Sans filière attribuée, il ne voit rien.
- Doyen / vice-doyen : toutes les filières de la (des) faculté(s) qu'il dirige (fiche faculté).
- Rôles d'établissement (System Manager, Registration Manager, Directeur des Affaires
  Académiques, Comptable, Responsable Diplomation, Responsable des partenariats) : aucune
  restriction.
Un utilisateur qui cumule un rôle d'établissement n'est pas restreint ; qui cumule plusieurs
rôles restreints obtient l'union de leurs périmètres.

`filieres(user)` renvoie None (aucune restriction) ou la liste des filières autorisées.
Ce périmètre s'applique aux listes Frappe (hooks de permission, voir udshed.permissions) et
aux API des écrans (`exiger_filiere`, `exiger_etudiant`, `filtre`).
"""

import frappe
from frappe import _

ROLES_ETABLISSEMENT = {"System Manager", "Registration Manager", "Directeur des Affaires Académiques", "Comptable",
					   "Responsable Diplomation", "Responsable des partenariats"}
ROLE_AGENT = "Agent de scolarité"
ROLES_DOYEN = {"Doyen", "Vice-Doyen"}


def _roles(user):
	return set(frappe.get_roles(user))


def facultes_dirigees(user=None):
	"""Facultés dont `user` est doyen ou vice-doyen (fiche faculté)."""
	user = user or frappe.session.user
	if not user or user in ("Guest",):
		return []
	if not frappe.db.has_column("Faculty", "doyen"):
		return []
	return sorted(set(frappe.get_all("Faculty", filters={"doyen": user}, pluck="name")
					  + frappe.get_all("Faculty", filters={"vice_doyen": user}, pluck="name")))


def filieres_agent(user=None):
	user = user or frappe.session.user
	if not frappe.db.table_exists("Agent Scolarite Filiere"):
		return []
	return sorted(set(frappe.get_all("Agent Scolarite Filiere", filters={"utilisateur": user, "parenttype": "Field of study"},
									 pluck="parent")))


def filieres(user=None):
	"""None = aucune restriction ; sinon la liste (éventuellement vide) des filières autorisées."""
	user = user or frappe.session.user
	if user == "Administrator":
		return None
	roles = _roles(user)
	if roles & ROLES_ETABLISSEMENT or not (roles & ({ROLE_AGENT} | ROLES_DOYEN)):
		resultat = None
	else:
		autorisees = set()
		if ROLE_AGENT in roles:
			autorisees.update(filieres_agent(user))
		if roles & ROLES_DOYEN:
			facs = facultes_dirigees(user)
			if facs:
				autorisees.update(frappe.get_all("Field of study", filters={"faculte": ["in", facs]}, pluck="name"))
		resultat = sorted(autorisees)
	return resultat


def restreint(user=None):
	return filieres(user) is not None


def autorisee(filiere, user=None):
	liste = filieres(user)
	return liste is None or (filiere in liste)


def message_vide(user=None):
	roles = _roles(user or frappe.session.user)
	if roles & ROLES_DOYEN:
		return _("Aucune faculté ne vous est attribuée (fiche faculté : doyen / vice-doyen).")
	return _("Aucune filière ne vous est attribuée (fiche filière : agents de scolarité).")


def exiger_filiere(filiere, user=None):
	"""Refuse si `filiere` est hors du périmètre (ne fait rien si filière vide ou sans restriction)."""
	if filiere and not autorisee(filiere, user):
		frappe.throw(_("La filière {0} n'est pas dans votre périmètre.").format(
			frappe.db.get_value("Field of study", filiere, "name_of_field") or filiere), frappe.PermissionError)


def filiere_etudiant(student):
	return frappe.db.get_value("Student", student, "filiere") if student else None


def exiger_etudiant(student, user=None):
	if not restreint(user):
		return
	filiere = filiere_etudiant(student)
	if not filiere or not autorisee(filiere, user):
		frappe.throw(_("Cet étudiant n'est pas dans votre périmètre."), frappe.PermissionError)


def filtre(filters, champ="filiere", user=None):
	"""Ajoute aux filtres (dict) la restriction de périmètre. Une filière demandée hors périmètre est refusée."""
	liste = filieres(user)
	if liste is None:
		return filters
	demande = filters.get(champ)
	if isinstance(demande, str) and demande:
		exiger_filiere(demande, user)
		return filters
	filters[champ] = ["in", liste or ["∅"]]
	return filters


def condition_sql(table, champ="filiere", user=None):
	"""Condition SQL (hooks permission_query_conditions) ; "" sans restriction."""
	liste = filieres(user)
	if liste is None:
		return ""
	if not liste:
		return "1=0"
	return f"`tab{table}`.`{champ}` in ({', '.join(frappe.db.escape(f) for f in liste)})"


def condition_sql_etudiant(table, champ="student", user=None):
	"""Condition SQL pour un DocType lié à l'étudiant (filière de sa fiche)."""
	liste = filieres(user)
	if liste is None:
		return ""
	if not liste:
		return "1=0"
	valeurs = ", ".join(frappe.db.escape(f) for f in liste)
	return f"`tab{table}`.`{champ}` in (select `name` from `tabStudent` where `filiere` in ({valeurs}))"


def destinataires(roles, filiere=None):
	"""Utilisateurs actifs ayant l'un des rôles, limités à ceux dont le périmètre couvre la filière."""
	users = set()
	for role in roles:
		users.update(frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent"))
	res = []
	for user in sorted(users):
		if user in ("Administrator", "Guest") or not frappe.db.get_value("User", user, "enabled"):
			continue
		if filiere and not autorisee(filiere, user):
			continue
		res.append(user)
	return res


def faculte_de_filiere(filiere):
	return frappe.db.get_value("Field of study", filiere, "faculte") if filiere else None


def est_doyen_de(faculte, user=None):
	user = user or frappe.session.user
	return bool(faculte) and faculte in facultes_dirigees(user)
