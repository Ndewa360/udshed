import frappe


def has_reregistered(student, academic_year=None):
	"""Vérifie si un étudiant s'est déjà réinscrit (Academic Reregistration validée).

	Args:
		student: name/ID du Student
		academic_year: name/ID de l'Academic Year (optionnel ; défaut = année en cours)

	Returns:
		tuple (bool, doc): (réinscrit ? , Academic Reregistration validée éventuel)
	"""
	if not student:
		return False, None

	if not academic_year:
		academic_year = frappe.db.get_single_value("Udshed Setting", "current_year")
		if not academic_year:
			academic_year = frappe.db.get_value(
				"Academic Year", {}, "name", order_by="creation desc"
			)

	row = frappe.get_all(
		"Academic Reregistration",
		filters={"student": student, "statut": "Validée"},
		fields=["name", "academic_year", "statut"],
		order_by="creation desc",
		limit_page_length=1,
	)
	if row:
		return True, frappe.get_doc("Academic Reregistration", row[0].name)

	return False, None


def get_current_academic_year():
	"""Année académique en cours depuis Udshed Setting ou dernière créée."""
	current = frappe.db.get_single_value("Udshed Setting", "current_year")
	if current:
		return current
	return frappe.db.get_value("Academic Year", {}, "name", order_by="creation desc")
