import frappe


def execute():
    ay = frappe.get_all("Academic Year", fields=["name"])
    print("Academic Years trouves: %d" % len(ay))
    for a in ay:
        print("  - %s" % a.name)

    sessions = frappe.get_all("Session Examen", fields=["name", "type_dexamen", "academic_year"])
    print("\nSessions Examen: %d" % len(sessions))
    for s in sessions:
        print("  - %s | %s | %s" % (s.name, s.type_dexamen, s.academic_year))

    notes = frappe.get_all("Session Examen Note", fields=["name", "student", "statut"], limit=5)
    print("\nSession Examen Notes (5 max): %d" % len(notes))
    for n in notes:
        print("  - %s | %s | %s" % (n.name, n.student, n.statut))
