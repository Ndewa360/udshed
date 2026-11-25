import frappe


def nettoyer(depuis="2026-11-25 00:00:00"):
	"""Supprime les données commitées par erreur par les tests du jour (site de test uniquement)."""
	assert frappe.local.site == "test.localhost", frappe.local.site
	ordre = ["Notification Log", "Academic Reregistration", "Inscription Academique", "Student",
			 "Session Inscription Candidate", "Teaching Unit", "Course", "Session Inscription",
			 "Field of study", "Faculty", "Teacher", "User"]
	for dt in ordre:
		noms = frappe.get_all(dt, filters={"creation": [">=", depuis]}, pluck="name")
		echecs = 0
		for nom in noms:
			if dt == "User" and nom in ("Administrator", "Guest"):
				continue
			try:
				frappe.delete_doc(dt, nom, force=True, ignore_permissions=True, ignore_on_trash=True)
			except Exception as e:
				echecs += 1
				print("échec", dt, nom, str(e)[:100])
		print(dt, len(noms), "supprimés", "échecs", echecs)
	if frappe.db.get_single_value("Udshed Setting", "school_name") == "Université de Test":
		frappe.db.set_single_value("Udshed Setting", "school_name", "")
	print("current_year", frappe.db.get_single_value("Udshed Setting", "current_year"),
		  "| année marquée courante", frappe.db.get_value("Academic Year", {"is_current_year": 1}, "name"))
	frappe.db.commit()
