"""Année académique de travail, fixée pour toute la session de l'utilisateur.

Le personnel choisit l'année une fois, juste après la connexion (l'année courante des
réglages est proposée ; choisie d'office s'il n'y en a qu'une). Elle vaut pour toute la
session : écrans, listes (sessions d'examen, anonymats, résultats, progressions…),
nouveaux documents. Pour changer d'année, on se déconnecte puis on se reconnecte.

Elle est rangée dans le cache par identifiant de session : la déconnexion l'efface.

`contexte_filtres()` donne les facultés, filières et niveaux du périmètre de l'utilisateur :
un écran ne laisse choisir un filtre que s'il offre plusieurs options.
"""

import frappe
from frappe import _

CLE = "udshed:annee_session"
# Rôles qui travaillent sur tout l'établissement (pas de périmètre par classe).
ROLES_GLOBAUX = {"System Manager", "Registration Manager", "Agent de scolarité", "Comptable",
				 "Responsable Diplomation", "Responsable des partenariats"}


def _sid():
	if frappe.session.user in (None, "Guest"):
		return None
	return getattr(frappe.session, "sid", None)


def annee_courante_reglages():
	return frappe.db.get_single_value("Udshed Setting", "current_year") or ""


def annee_choisie():
	sid = _sid()
	return (frappe.cache.hget(CLE, sid) or "") if sid else ""


def annee_session():
	"""Année de travail de la session (à défaut : l'année courante des réglages)."""
	return annee_choisie() or annee_courante_reglages()


def annees_disponibles():
	return frappe.get_all("Academic Year", pluck="name", order_by="name desc")


@frappe.whitelist()
def choisir_annee(annee):
	"""Fixe l'année de travail pour la session ; refuse d'en changer sans se reconnecter."""
	from udshed.utils.securite import est_personnel

	sid = _sid()
	if not sid or not est_personnel():
		frappe.throw(_("Réservé au personnel connecté."), frappe.PermissionError)
	if not annee or not frappe.db.exists("Academic Year", annee):
		frappe.throw(_("Année académique introuvable : {0}").format(annee or "—"))
	deja = annee_choisie()
	if deja and deja != annee:
		frappe.throw(_("L'année {0} est fixée pour cette session. Pour travailler sur une autre année, "
					   "déconnectez-vous puis reconnectez-vous.").format(deja))
	frappe.cache.hset(CLE, sid, annee)
	return annee


def effacer_session(*args, **kwargs):
	"""Hook on_logout : la prochaine connexion redemande l'année."""
	sid = _sid()
	if sid:
		frappe.cache.hdel(CLE, sid)


def _options(rows, cle_label, parent=None):
	vus, out = set(), []
	for r in rows:
		if r.name in vus:
			continue
		vus.add(r.name)
		item = {"value": r.name, "label": r.get(cle_label) or r.name}
		if parent:
			item[parent] = r.get(parent)
		out.append(item)
	return out


@frappe.whitelist()
def contexte_filtres():
	"""Année de la session et options de filtres du périmètre de l'utilisateur."""
	from udshed.api import planning_permission
	from udshed.utils.securite import est_personnel

	if not est_personnel():
		frappe.throw(_("Réservé au personnel."), frappe.PermissionError)
	user = frappe.session.user
	roles = set(frappe.get_roles(user))
	global_ = user == "Administrator" or bool(roles & ROLES_GLOBAUX)
	niveau = frappe.qb.DocType("Field of study Level")
	filiere = frappe.qb.DocType("Field of study")
	faculte = frappe.qb.DocType("Faculty")
	requete = (
		frappe.qb.from_(niveau)
		.join(filiere).on(filiere.name == niveau.parent)
		.left_join(faculte).on(faculte.name == filiere.faculte)
		.select(niveau.name.as_("niveau"), niveau.level, filiere.name.as_("filiere"), filiere.name_of_field,
				filiere.faculte, faculte.name.as_("fac_name"))
		.where(niveau.parenttype == "Field of study")
		.orderby(filiere.name_of_field).orderby(niveau.idx)
	)
	if not global_:
		scope = planning_permission.get_scope(user)
		niveaux = scope.get("niveaux") or []
		if not niveaux:
			return {"annee": annee_session(), "global": False, "facultes": [], "filieres": [], "niveaux": []}
		requete = requete.where(niveau.name.isin(niveaux))
	lignes = requete.run(as_dict=True)
	libelles_fac = dict(frappe.get_all("Faculty", fields=["name", _champ_libelle_faculte()], as_list=True))
	facultes = [{"value": f, "label": libelles_fac.get(f) or f}
				for f in dict.fromkeys(r.faculte for r in lignes if r.faculte)]
	filieres = _options([frappe._dict(name=r.filiere, label=r.name_of_field, faculte=r.faculte) for r in lignes],
						"label", "faculte")
	niveaux = _options([frappe._dict(name=r.niveau, label=r.level, filiere=r.filiere) for r in lignes], "label", "filiere")
	return {"annee": annee_session(), "global": global_, "facultes": facultes, "filieres": filieres, "niveaux": niveaux}


def _champ_libelle_faculte():
	meta = frappe.get_meta("Faculty")
	for champ in ("faculty_name", "nom", "name_of_faculty", "intitule", "title"):
		if meta.has_field(champ):
			return champ
	return meta.title_field or "name"


def boot(bootinfo):
	"""Hook extend_bootinfo : année de la session pour le navigateur et valeur par défaut des formulaires."""
	from udshed.utils.securite import est_personnel

	if frappe.session.user in ("Guest", None) or not est_personnel():
		return
	try:
		annee = annee_session()
		annees = annees_disponibles()
		bootinfo.udshed_session = {
			"annee": annee,
			"choisie": bool(annee_choisie()),
			"annees": annees,
			"annee_courante": annee_courante_reglages(),
		}
		# Valeur par défaut des champs « Année académique » des nouveaux documents.
		defaults = (bootinfo.get("user") or {}).get("defaults")
		if annee and isinstance(defaults, dict):
			defaults["academic_year"] = annee
	except Exception:
		frappe.log_error(title="udshed: année de la session")
