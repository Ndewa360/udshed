"""Jeu de démonstration TEMPORAIRE pour vérifier les écrans dans un navigateur (test.localhost).

creer()    : crée les données (comptes demo-*@udshed.demo) et note l'heure de début.
supprimer(): supprime tout ce qui a été créé depuis cette heure dans les DocTypes concernés.
"""
import json
import pathlib

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime
from frappe.utils.password import update_password

TRACE = pathlib.Path(frappe.get_site_path("private", "demo_claude.json"))
MDP = "Demo!2026udshed"
DOCTYPES = ["Planning Item", "Teaching Unit", "Course", "Field of study", "Teacher", "Calendar Planing", "Faculty",
			"Building", "Room", "Academic Year"]


def _teacher(prenom, nom, grade="Dr", email=None, statut="Permanent"):
	doc = frappe.get_doc({"doctype": "Teacher", "grade": grade, "first_name": prenom, "last_name": nom,
						  "email": email or f"{prenom.lower()}.{nom.lower()}@udshed.demo", "status": statut})
	return doc.insert(ignore_permissions=True)


def _user(email, prenom, roles):
	if not frappe.db.exists("User", email):
		u = frappe.get_doc({"doctype": "User", "email": email, "first_name": prenom, "send_welcome_email": 0,
							"user_type": "System User"})
		u.flags.no_welcome_mail = True
		u.insert(ignore_permissions=True)
		u.add_roles(*roles)
	update_password(email, MDP)
	return email


def creer():
	debut = str(now_datetime())
	TRACE.write_text(json.dumps({"debut": debut}))
	frappe.flags.in_test = False
	for a, b in (("2025", "2026"), ("2026", "2027")):
		if not frappe.db.exists("Academic Year", f"{a}-{b}"):
			frappe.get_doc({"doctype": "Academic Year", "start_year": a, "end_year": b, "start_month": "Septembre",
							"end_month": "Juin"}).insert(ignore_permissions=True)
	annee = "2025-2026"
	frappe.db.set_single_value("Udshed Setting", "current_year", annee)

	cal = frappe.get_doc({"doctype": "Calendar Planing", "nom_du_planing": "Calendrier Licence (démo)"})
	cal.append("heure_planification", {"libelle": "Matin", "heure_de_debut": "08:00:00", "heure_de_fin": "12:00:00"})
	cal.append("heure_planification", {"libelle": "Après-midi", "heure_de_debut": "13:00:00", "heure_de_fin": "17:00:00"})
	cal.insert(ignore_permissions=True)
	fac = frappe.get_doc({"doctype": "Faculty", "faculty_name": "Faculté des Sciences", "faculty_code": "FSDEMO"}).insert(
		ignore_permissions=True)

	coord = _teacher("Brigitte", "Ngono", "Pr", email="demo-coord@udshed.demo")
	profs = [_teacher("Paul", "Mbarga"), _teacher("Aline", "Fotso", "Dr", statut="Vacataire"),
			 _teacher("Jean", "Kamga", "M.", statut="Vacataire")]

	def filiere(nom, code, niveaux, coordinateur):
		fos = frappe.get_doc({"doctype": "Field of study", "name_of_field": nom, "field_of_study_code": code,
							  "faculte": fac.name, "department_coordinator": coordinateur.name})
		for i, n in enumerate(niveaux, 1):
			fos.append("field_of_study_level", {"level": n, "order": i, "coordonateur": coordinateur.name,
												"calendrier": cal.name, "cycle": "Licence"})
		return fos.insert(ignore_permissions=True)

	inf = filiere("Informatique", "INFDEMO", ["Licence 1", "Licence 2"], coord)
	mat = filiere("Mathématiques", "MATDEMO", ["Licence 1"], profs[0])

	cours = []
	for fos, niv, intitule, prof in (
		(inf, inf.field_of_study_level[0], "Algorithmique", profs[0]),
		(inf, inf.field_of_study_level[0], "Programmation en C", profs[1]),
		(inf, inf.field_of_study_level[0], "Mathématiques discrètes", profs[2]),
		(inf, inf.field_of_study_level[1], "Bases de données", profs[1]),
		(mat, mat.field_of_study_level[0], "Analyse I", profs[0]),
	):
		c = frappe.get_doc({"doctype": "Course", "code": "D" + frappe.generate_hash(length=5).upper(), "intitule": intitule,
							"semestre": "Semestre 1", "nombre_dheure_cm": 30, "nombre_dheure_td": 15}).insert(ignore_permissions=True)
		tu = frappe.get_doc({"doctype": "Teaching Unit", "course": c.name, "academic_year": annee, "mode": "En présentiel",
							 "semestre": "Semestre 1", "credits": 4, "type_ue": "Sans TP", "intitule_cours": intitule})
		tu.append("course_levels", {"filiere": fos.name, "niveau": niv.name, "course_poid": 4})
		tu.append("table_enseignant", {"enseignant": prof.name, "type_de_cours": "Cours Magistral (CM)"})
		cours.append(tu.insert(ignore_permissions=True))

	lundi = getdate(now_datetime())
	lundi = add_days(lundi, -lundi.weekday())
	matin, aprem = cal.heure_planification[0].name, cal.heure_planification[1].name
	for i, (tu, jour, periode) in enumerate(((cours[0], 0, matin), (cours[1], 0, aprem), (cours[2], 1, matin),
											 (cours[0], 2, aprem), (cours[3], 3, matin), (cours[4], 1, aprem))):
		frappe.get_doc({"doctype": "Planning Item", "cours": tu.name, "type": "Cours Magistral (CM)",
						"date": get_datetime(f"{add_days(lundi, jour)} 08:00:00"), "period": periode,
						"academic_year": annee, "mode": "En présentiel", "status": "Fait" if i < 3 else "Non fait"}
					   ).insert(ignore_permissions=True)

	# Vacations : tarif horaire du titre des vacataires (retiré par supprimer() s'il a été ajouté ici).
	titre = frappe.get_meta("Financial Payment Grade Config").get_field("grade").options.split("\n")[0]
	s = frappe.get_single("Udshed Setting")
	if not any(r.grade == titre for r in s.configuration_des_paiements_par_grade):
		s.append("configuration_des_paiements_par_grade", {"grade": titre, "prix_heure": 6500})
		s.save(ignore_permissions=True)
		trace = json.loads(TRACE.read_text())
		trace["tarif_ajoute"] = titre
		TRACE.write_text(json.dumps(trace))
	for p in profs:
		frappe.db.set_value("Teacher", p.name, "titre", titre)

	_user("demo-coord@udshed.demo", "Brigitte", ["Coordonateur", "Teacher"])
	_user("demo-scol@udshed.demo", "Agent", ["Agent de scolarité"])
	_user("demo-admin@udshed.demo", "Admin", ["System Manager"])
	_user("demo-part@udshed.demo", "Partenariats", ["Responsable des partenariats"])
	_user(profs[1].email, "Aline", ["Teacher"])  # vacataire
	frappe.db.commit()
	print("démo créée depuis", debut)


def installation_terminee():
	"""L'assistant d'installation n'a jamais été fait sur le site de test : on le marque terminé
	(état d'origine noté pour être restauré par supprimer())."""
	trace = json.loads(TRACE.read_text())
	if "setup" not in trace:
		trace["setup"] = {
			"system": frappe.db.get_single_value("System Settings", "setup_complete"),
			"apps": frappe.get_all("Installed Application", fields=["name", "is_setup_complete"], as_list=True),
		}
		TRACE.write_text(json.dumps(trace, default=str))
	frappe.db.set_single_value("System Settings", "setup_complete", 1)
	frappe.db.sql("update `tabInstalled Application` set is_setup_complete = 1")
	frappe.db.commit()
	frappe.clear_cache()
	print("installation marquée terminée")


def supprimer():
	if not TRACE.exists():
		print("aucune démo")
		return
	trace = json.loads(TRACE.read_text())
	debut = trace["debut"]
	if "setup" in trace:
		frappe.db.set_single_value("System Settings", "setup_complete", trace["setup"]["system"] or 0)
		for nom, etat in trace["setup"]["apps"]:
			frappe.db.set_value("Installed Application", nom, "is_setup_complete", etat or 0, update_modified=False)
	for dt in DOCTYPES:
		for nom in frappe.get_all(dt, filters={"creation": [">=", debut]}, pluck="name"):
			frappe.delete_doc(dt, nom, force=True, ignore_permissions=True, delete_permanently=True)
	if trace.get("tarif_ajoute"):
		s = frappe.get_single("Udshed Setting")
		s.set("configuration_des_paiements_par_grade",
			  [r for r in s.configuration_des_paiements_par_grade if r.grade != trace["tarif_ajoute"]])
		s.save(ignore_permissions=True)
	for dt in ("Document Enseignant", "Convention Vacation"):
		for nom in frappe.get_all(dt, filters={"creation": [">=", debut]}, pluck="name"):
			frappe.delete_doc(dt, nom, force=True, ignore_permissions=True, delete_permanently=True)
	for email in ("demo-coord@udshed.demo", "demo-scol@udshed.demo", "demo-admin@udshed.demo",
				  "demo-part@udshed.demo", "aline.fotso@udshed.demo"):
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True, delete_permanently=True)
	TRACE.unlink()
	frappe.db.commit()
	print("démo supprimée (créations depuis", debut, ")")
