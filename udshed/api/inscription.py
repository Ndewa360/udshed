import frappe


@frappe.whitelist()
def get_inscription_report(inscription_session=None, filiere=None, candidature_status=None):
	"""
	Rapport combiné des inscriptions et réinscriptions :
	liste détaillée + statistiques par statut, filière et niveau.

	Args:
		inscription_session: name/ID de la Session Inscription (optionnel)
		filiere: name/ID de la Field of study (optionnel)
		candidature_status: En attente | Dossier en cours d'examen | Accepté | Refusé | Inscrit (optionnel)

	Returns:
		dict: {rows, total, par_statut, par_filiere, par_niveau, par_type}
	"""
	filters = {}
	if inscription_session:
		filters["inscription_session"] = inscription_session
	if filiere:
		filters["filiere"] = filiere
	if candidature_status:
		filters["candidature_status"] = candidature_status

	candidates = frappe.get_all(
		"Session Inscription Candidate",
		filters=filters,
		fields=[
			"name", "first_name", "last_name", "full_name", "email",
			"filiere", "niveau", "candidature_status", "examination_centre",
			"inscription_session", "creation"
		],
		order_by="creation desc"
	)

	filiere_names = list(set(r.get("filiere") for r in candidates if r.get("filiere")))
	filiere_map = {}
	for f_name in filiere_names:
		filiere_map[f_name] = (
			frappe.db.get_value("Field of study", f_name, "name_of_field") or f_name
		)

	rows = []
	for c in candidates:
		rows.append({
			"name": c.get("name"),
			"nom_complet": c.get("full_name") or f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
			"email": c.get("email", ""),
			"filiere_label": filiere_map.get(c.get("filiere"), c.get("filiere") or "Non défini"),
			"niveau": c.get("niveau") or "Non défini",
			"candidature_status": c.get("candidature_status") or "En attente",
			"examination_centre": c.get("examination_centre") or "Non défini",
			"inscription_session": c.get("inscription_session") or "",
			"creation": str(c.get("creation", ""))
		})

	par_statut = {}
	par_filiere = {}
	par_niveau = {}
	for r in rows:
		statut = r.get("candidature_status") or "En attente"
		par_statut[statut] = par_statut.get(statut, 0) + 1
		label = r.get("filiere_label") or "Non défini"
		par_filiere[label] = par_filiere.get(label, 0) + 1
		niveau = r.get("niveau") or "Non défini"
		par_niveau[niveau] = par_niveau.get(niveau, 0) + 1

	return {
		"rows": rows,
		"total": len(rows),
		"par_statut": par_statut,
		"par_filiere": par_filiere,
		"par_niveau": par_niveau,
	}
