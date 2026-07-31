import frappe
import json


@frappe.whitelist()
def get_students_for_grade_entry(planning_item_name):
    planning = frappe.get_doc("Planning Item", planning_item_name)
    tu_name = planning.cours
    academic_year = planning.academic_year

    tu = frappe.get_doc("Teaching Unit", tu_name)
    course = frappe.get_doc("Course", tu.course) if tu.course else None

    students = frappe.db.sql("""
        SELECT DISTINCT s.name AS student, s.matricule, s.nom, s.prenom
        FROM `tabAcademic Reregistration` ar
        INNER JOIN `tabReregistration Course Item` rci
            ON rci.parent = ar.name AND rci.parenttype = 'Academic Reregistration'
        INNER JOIN `tabStudent` s ON s.name = ar.student
        WHERE ar.academic_year = %(academic_year)s
            AND ar.statut = 'Validée'
            AND rci.teaching_unit = %(teaching_unit)s
        ORDER BY s.nom, s.prenom
    """, {
        "academic_year": academic_year,
        "teaching_unit": tu_name,
    }, as_dict=True)

    existing_session = frappe.db.get_value(
        "Session Examen",
        {"planning_item": planning_item_name},
        "name",
    )

    existing_notes = {}
    if existing_session:
        notes = frappe.get_all(
            "Session Examen Note",
            {"session_examen": existing_session},
            ["student", "note_cc", "note_examen", "note_examen_rattrapage", "name"],
        )
        for n in notes:
            existing_notes[n.student] = n

    result = []
    for s in students:
        entry = {
            "student": s.student,
            "matricule": s.matricule,
            "nom": f"{s.nom} {s.prenom}".strip(),
            "credits": tu.credits,
            "note_entry_name": None,
            "note_cc": None,
            "note_examen": None,
            "note_examen_rattrapage": None,
        }
        if s.student in existing_notes:
            en = existing_notes[s.student]
            entry["note_entry_name"] = en.name
            entry["note_cc"] = en.note_cc
            entry["note_examen"] = en.note_examen
            entry["note_examen_rattrapage"] = en.note_examen_rattrapage
        result.append(entry)

    return {
        "planning": {
            "name": planning.name,
            "type": planning.type,
            "teaching_unit": tu_name,
            "intitule_cours": tu.intitule_cours or course.intitule if course else tu_name,
            "academic_year": academic_year,
            "credits": tu.credits,
            "semestre": tu.semestre,
        },
        "students": result,
        "existing_session": existing_session,
    }


@frappe.whitelist()
def save_bulk_grades(planning_item_name, grades):
    if isinstance(grades, str):
        grades = json.loads(grades)

    planning = frappe.get_doc("Planning Item", planning_item_name)
    tu_name = planning.cours
    planning_type = planning.type
    is_cc = "CC" in planning_type or planning_type == "Controlle Continue (CC)"
    is_rattrapage = "rattrapage" in planning_type.lower()

    session_examen = frappe.db.get_value(
        "Session Examen",
        {"planning_item": planning_item_name},
        "name",
    )
    if not session_examen:
        session_examen = _create_session_examen(planning)

    tu = frappe.get_doc("Teaching Unit", tu_name)
    has_tp = any(t.type_de_cours == "TP" for t in tu.table_enseignant)
    type_ue = "Avec TP" if has_tp else "Sans TP"

    created_notes = []
    errors = []

    for g in grades:
        student = g.get("student")
        note_value = g.get("note")

        if note_value is None or note_value == "":
            continue

        try:
            note_value = float(note_value)
            if note_value < 0 or note_value > 20:
                errors.append(f"Note {note_value} invalide pour {student} (0-20)")
                continue

            existing_note_name = g.get("note_entry_name")
            if existing_note_name:
                note_doc = frappe.get_doc("Session Examen Note", existing_note_name)
            else:
                existing = frappe.db.get_value(
                    "Session Examen Note",
                    {
                        "session_examen": session_examen,
                        "student": student,
                        "teaching_unit": tu_name,
                    },
                    "name",
                )
                if existing:
                    note_doc = frappe.get_doc("Session Examen Note", existing)
                else:
                    note_doc = frappe.new_doc("Session Examen Note")
                    note_doc.session_examen = session_examen
                    note_doc.student = student
                    note_doc.teaching_unit = tu_name
                    note_doc.type_ue = type_ue

            if not note_doc.statut:
                note_doc.statut = "Brouillon"

            if is_cc:
                note_doc.note_cc = note_value
            elif is_rattrapage:
                note_doc.note_examen_rattrapage = note_value
            else:
                note_doc.note_examen = note_value

            note_doc.save(ignore_permissions=True)

            created_notes.append({
                "name": note_doc.name,
                "student": student,
                "note_finale": note_doc.note_finale,
                "note_pct": note_doc.note_pct,
                "grade": note_doc.grade,
                "mention": note_doc.mention,
                "statut": note_doc.statut,
            })

        except Exception as e:
            errors.append(f"{student}: {str(e)}")

    frappe.db.commit()

    return {
        "status": "success" if not errors else "partial",
        "session_examen": session_examen,
        "created_notes": created_notes,
        "errors": errors,
    }


def _create_session_examen(planning):
    tu = frappe.get_doc("Teaching Unit", planning.cours)

    calendar_name = None
    for cls in tu.course_levels:
        if cls.niveau:
            try:
                level_doc = frappe.get_doc("Field of study Level", cls.niveau)
                if level_doc.calendrier:
                    calendar_name = level_doc.calendrier
                    break
            except Exception:
                continue

    if not calendar_name:
        calendar_name = frappe.db.get_value("Calendar Planing", {}, "name")

    session = frappe.new_doc("Session Examen")
    session.academic_year = planning.academic_year
    session.calendar = calendar_name
    session.type_dexamen = planning.type
    session.planning_item = planning.name
    session.date_debut = planning.date
    session.date_de_fin = planning.date
    session.semestre = tu.semestre

    seen = set()
    for cls in tu.course_levels:
        key = (cls.filiere, cls.niveau)
        if key not in seen:
            seen.add(key)
            session.append("classes_concernees", {
                "filiere": cls.filiere,
                "niveau": cls.niveau,
            })

    session.insert(ignore_permissions=True)
    return session.name
