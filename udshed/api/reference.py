"""Petites lectures de référentiel pour les écrans, sans exiger la lecture du DocType.

Un enseignant n'a que la sélection sur les référentiels (Filière, Année…) et aucun accès aux
réglages : ces écrans passent donc par ici plutôt que par frappe.db.get_value.
"""

import frappe
from frappe import _


@frappe.whitelist()
def annee_courante():
	return frappe.db.get_single_value("Udshed Setting", "current_year")


@frappe.whitelist()
def libelle_filiere(filiere):
	return frappe.db.get_value("Field of study", filiere, "name_of_field") or filiere


def _exiger_personnel():
	if frappe.session.user == "Guest" or frappe.session.data.get("user_type") == "Website User":
		frappe.throw(_("Connectez-vous pour continuer."), frappe.PermissionError)


def _valeur_filtre(valeur):
	"""Un filtre de Link peut arriver sous la forme "x", ["=", "x"] ou ["in", [...]]."""
	if isinstance(valeur, (list, tuple)) and len(valeur) == 2:
		operateur, valeur = valeur
		if operateur == "in":
			return list(valeur or [])
	return valeur


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def niveaux_query(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	"""Recherche standard des niveaux de filière (hook standard_queries).

	« Field of study Level » est une table enfant de la filière : Frappe refuse la recherche
	directe aux utilisateurs non administrateurs (erreur d'autorisation sur les champs
	« niveau »). Seuls des libellés sont renvoyés, filtrables par filière (`parent`).
	"""
	_exiger_personnel()
	niveau = frappe.qb.DocType("Field of study Level")
	filiere = frappe.qb.DocType("Field of study")
	requete = (
		frappe.qb.from_(niveau)
		.join(filiere).on(filiere.name == niveau.parent)
		.select(niveau.name, niveau.level, filiere.name_of_field)
		.where(niveau.parenttype == "Field of study")
	)
	parent = _valeur_filtre((filters or {}).get("parent")) if isinstance(filters, dict) else None
	if isinstance(parent, list):
		requete = requete.where(niveau.parent.isin(parent or [""]))
	elif parent:
		requete = requete.where(niveau.parent == parent)
	if txt:
		motif = f"%{txt}%"
		requete = requete.where((niveau.name == txt) | niveau.level.like(motif) | filiere.name_of_field.like(motif))
	return requete.orderby(filiere.name_of_field).orderby(niveau.order).limit(page_len).offset(start).run()


@frappe.whitelist()
def niveaux_filiere(filiere):
	"""Niveaux d'une filière (libellés seulement), pour les sélecteurs des écrans."""
	_exiger_personnel()
	return frappe.get_all("Field of study Level", filters={"parent": filiere, "parenttype": "Field of study"},
						  fields=["name", "level"], order_by="idx asc")
