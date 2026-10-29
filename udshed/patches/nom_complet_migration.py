import frappe


def execute():
    students = frappe.get_all("Student", fields=["name", "matricule", "nom", "prenom"])
    count = 0
    for s in students:
        nom_complet = f"{s.matricule or ''} - {s.nom or ''} {s.prenom or ''}".strip()
        frappe.db.set_value("Student", s.name, "nom_complet", nom_complet)
        count += 1
    frappe.db.commit()
    print(f"Nom complet mis a jour pour {count} etudiants")
