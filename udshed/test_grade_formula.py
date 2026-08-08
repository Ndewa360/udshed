import frappe
from udshed.grade_calculation import (
    get_active_formula,
    calculer_moyenne_cc,
    calculer_note_finale_ue,
    appliquer_arrondi,
    est_valide
)


def test_grade_formula():
    """Test complet du système de formules de notes."""

    # 1. Créer une formule Licence active
    frappe.db.delete("Grade Formula", {"cycle": "Licence"})
    frappe.db.delete("Grade Formula", {"cycle": "Master"})

    formule_licence = frappe.get_doc({
        "doctype": "Grade Formula",
        "cycle": "Licence",
        "active": 1,
        "poids_cc": 40,
        "poids_examen": 60,
        "methode_calcul_cc": "Moyenne arithmétique",
        "nombre_min_cc_requis": 2,
        "methode_arrondi": "Au plus proche",
    }).insert()

    formule_master = frappe.get_doc({
        "doctype": "Grade Formula",
        "cycle": "Master",
        "active": 1,
        "poids_cc": 30,
        "poids_examen": 50,
        "composantes_supplementaires": [
            {"nom": "TP", "poids": 10},
            {"nom": "Projet", "poids": 10},
        ],
        "methode_calcul_cc": "Moyenne des N meilleures notes",
        "nombre_min_cc_requis": 2,
        "methode_arrondi": "Au supérieur",
    }).insert()

    # 2. Simuler un étudiant Licence
    #    (pas besoin de créer un vrai Student, on teste juste le calcul)
    cycle = "Licence"
    notes_cc = [12, 15, 8, 17]
    note_examen = 11

    f = get_active_formula(cycle)
    moy_cc = calculer_moyenne_cc(notes_cc, f.methode_calcul_cc, f.nombre_min_cc_requis)
    note_finale = calculer_note_finale_ue(note_cc=moy_cc, note_examen=note_examen, formula=f)
    valide = est_valide(note_finale, cycle)

    print(f"\n=== ÉTUDIANT LICENCE ===")
    print(f"Notes CC: {notes_cc}")
    print(f"Moyenne CC ({f.methode_calcul_cc}): {moy_cc}/20")
    print(f"Examen: {note_examen}/20")
    print(f"Note finale: {note_finale}/20 ({note_finale/20*100:.1f}%)")
    print(f"Seuil validation: {f.seuil_validation}%")
    print(f"Statut: {'✅ VALIDÉE' if valide else '❌ NON VALIDÉE'}")

    # 3. Simuler un étudiant Master avec TP et Projet
    cycle_m = "Master"
    notes_cc_m = [14, 10, 16, 8]

    fm = get_active_formula(cycle_m)
    moy_cc_m = calculer_moyenne_cc(notes_cc_m, fm.methode_calcul_cc, fm.nombre_min_cc_requis)
    note_finale_m = calculer_note_finale_ue(
        note_cc=moy_cc_m,
        note_examen=13,
        notes_complementaires={"TP": 16, "Projet": 14},
        formula=fm
    )
    valide_m = est_valide(note_finale_m, cycle_m)

    print(f"\n=== ÉTUDIANT MASTER (avec TP + Projet) ===")
    print(f"Notes CC: {notes_cc_m}")
    print(f"Moyenne CC ({fm.methode_calcul_cc}): {moy_cc_m}/20")
    print(f"Examen: 13/20, TP: 16/20, Projet: 14/20")
    print(f"Note finale: {note_finale_m}/20 ({note_finale_m/20*100:.1f}%)")
    print(f"Seuil validation: {fm.seuil_validation}%")
    print(f"Statut: {'✅ VALIDÉE' if valide_m else '❌ NON VALIDÉE'}")

    # 4. Nettoyage
    formule_licence.delete()
    formule_master.delete()
    print(f"\n✅ Test terminé.")


if __name__ == "__main__":
    test_grade_formula()
