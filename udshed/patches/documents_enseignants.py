"""Documents des enseignants.

- modèles par défaut des documents enseignants (progression, règlement des vacations,
  convention, attestation d'enseignement) ; un modèle existant n'est jamais modifié ;
- un modèle par défaut par type de document (le plus ancien modèle actif du type) ;
- sujet « Étudiant » des modèles existants ;
- anciens contrats de la fiche enseignant repris en conventions de vacation.
"""

import frappe

from udshed.utils.actes import SUJET_ETUDIANT, TYPES_ENSEIGNANT, creer_modeles_defaut


def execute():
	frappe.reload_doc("udshed", "doctype", "modele_acte")
	frappe.reload_doc("udshed", "doctype", "convention_vacation")
	frappe.reload_doc("udshed", "doctype", "document_enseignant")
	for nom, type_acte in frappe.get_all("Modele Acte", fields=["name", "type_acte"], as_list=True):
		if type_acte not in TYPES_ENSEIGNANT and not frappe.db.get_value("Modele Acte", nom, "sujet"):
			frappe.db.set_value("Modele Acte", nom, "sujet", SUJET_ETUDIANT, update_modified=False)
	creer_modeles_defaut()
	for type_acte in {t for t in frappe.get_all("Modele Acte", pluck="type_acte") if t}:
		if not frappe.db.exists("Modele Acte", {"type_acte": type_acte, "par_defaut": 1}):
			nom = frappe.db.get_value("Modele Acte", {"type_acte": type_acte, "actif": 1}, "name", order_by="creation asc")
			if nom:
				frappe.db.set_value("Modele Acte", nom, "par_defaut", 1, update_modified=False)
	reprendre_contrats()


def reprendre_contrats():
	if not frappe.db.table_exists("Teacher Academic Contract"):
		return
	for c in frappe.get_all("Teacher Academic Contract", filters={"parenttype": "Teacher"},
							fields=["parent", "academic_year", "have_signed_contract", "signed_contract"]):
		if not c.academic_year or not frappe.db.exists("Teacher", c.parent):
			continue
		if frappe.db.exists("Convention Vacation", {"teacher": c.parent, "academic_year": c.academic_year}):
			continue
		signee = bool(c.have_signed_contract and c.signed_contract)
		doc = frappe.get_doc({"doctype": "Convention Vacation", "teacher": c.parent, "academic_year": c.academic_year,
							  "statut": "Signée" if signee else "Brouillon", "convention_signee": c.signed_contract,
							  "observations": "Reprise de l'ancien contrat de la fiche enseignant."})
		doc.flags.ignore_permissions = True
		doc.insert()
