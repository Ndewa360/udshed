"""Passage aux campagnes d'admission dynamiques.

- Campagnes existantes : titre, délai de confirmation, date limite
  d'inscription des admis (90 jours après la clôture) et centres d'examen
  (ceux déjà choisis par les candidats de la campagne ; sinon les centres
  historiques, auparavant codés en dur dans le formulaire).
- Ancien Web Form « session-de-2025 » supprimé (remplacé par « candidature »).
- Anciennes pages du dépôt en plusieurs étapes dépubliées.
"""

import frappe
from frappe.utils import add_days

CENTRES_HISTORIQUES = ["Bangangté", "Bafoussam", "Yaoundé", "Douala"]
PAGES_OBSOLETES = ["suivi-candidature", "document-dossier", "information-candidat",
				   "candidate-choice", "success-candidature"]


def execute():
	frappe.reload_doc("udshed", "doctype", "session_inscription")
	frappe.reload_doc("udshed", "doctype", "session_inscription_candidate")

	for c in frappe.get_all("Session Inscription", fields=["name", "academic_year", "closing_date", "titre",
														   "delai_finalisation", "date_limite_inscription",
														   "centres_examen"]):
		valeurs = {}
		if not c.titre:
			valeurs["titre"] = f"Candidatures {c.academic_year}"
		if not c.delai_finalisation:
			valeurs["delai_finalisation"] = 15
		if not c.date_limite_inscription and c.closing_date:
			valeurs["date_limite_inscription"] = add_days(c.closing_date, 90)
		if not c.centres_examen:
			centres = [x for x in frappe.get_all(
				"Session Inscription Candidate",
				filters={"session_inscription": c.name, "examination_centre": ["is", "set"]},
				pluck="examination_centre", distinct=True,
			) if x]
			valeurs["centres_examen"] = "\n".join(sorted(set(centres)) or CENTRES_HISTORIQUES)
		if valeurs:
			frappe.db.set_value("Session Inscription", c.name, valeurs, update_modified=False)

	if frappe.db.exists("Web Form", "session-de-2025"):
		frappe.delete_doc("Web Form", "session-de-2025", ignore_permissions=True, force=True)

	# Fiche d'inscription : « Fiche Officielle UDM » renommée « Fiche Inscription ».
	if frappe.db.exists("Print Format", "Fiche Officielle UDM"):
		for ps in frappe.get_all("Property Setter", filters={"value": "Fiche Officielle UDM"}, pluck="name"):
			frappe.db.set_value("Property Setter", ps, "value", "Fiche Inscription")
		frappe.delete_doc("Print Format", "Fiche Officielle UDM", ignore_permissions=True, force=True)

	for route in PAGES_OBSOLETES:
		for nom in frappe.get_all("Web Page", filters={"route": route}, pluck="name"):
			frappe.db.set_value("Web Page", nom, "published", 0)

	# Nom et logo de l'établissement repris par la page de connexion Frappe.
	from udshed.udshed.doctype.udshed_setting.udshed_setting import synchroniser_identite_site

	synchroniser_identite_site()

	from frappe.website.utils import clear_cache

	clear_cache()
