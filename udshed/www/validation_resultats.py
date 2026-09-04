import frappe
from frappe import _


def get_context(context):
    context.title = "Validation des résultats"

    # Vérifier les permissions
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login"
        raise frappe.Redirect

    context.academic_years = frappe.get_all("Academic Year", fields=["name"], order_by="name desc")
    context.semestres = ["Semestre 1", "Semestre 2"]

    # Filtres par défaut
    context.selected_year = frappe.form_dict.get("year", "")
    context.selected_semestre = frappe.form_dict.get("semestre", "")
    context.selected_level = frappe.form_dict.get("level", "")

    # Récupérer les étudiants avec leurs notes
    context.students = _get_students_with_notes(
        context.selected_year,
        context.selected_semestre,
        context.selected_level
    )


def _get_students_with_notes(year, semestre, level):
    """Récupère les étudiants avec leurs notes pour validation."""
    if not year:
        return []

    filters = {"academic_year": year}
    if semestre:
        filters["semestre"] = semestre

    # Récupérer les résultats
    results = frappe.get_all(
        "Resultat Academique",
        filters=filters,
        fields=["student", "student_name", "teaching_unit", "ue_name", "note_finale", "statut"],
        order_by="student asc"
    )

    # Grouper par étudiant
    students_map = {}
    for r in results:
        sname = r.student
        if sname not in students_map:
            student = frappe.get_doc("Student", sname)
            students_map[sname] = {
                "name": sname,
                "matricule": sname,
                "nom": student.nom or "",
                "prenom": student.prenom or "",
                "notes": []
            }
        students_map[sname]["notes"].append({
            "teaching_unit": r.teaching_unit,
            "ue_name": r.ue_name,
            "note_finale": r.note_finale,
            "statut": r.statut
        })

    return list(students_map.values())
