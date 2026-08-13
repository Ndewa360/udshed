import frappe

frappe.set_user("Administrator")

filters = {
    "academic_year": "2025-2026",
    "filiere": "IRT",
    "niveau": "Licence 1",
    "semestre": "Semestre 1",
    "teaching_unit": "MAT101-0047",
}
try:
    from udshed.api.saisie_notes import charger_data
    d = charger_data(**filters)
    print("KEY:", list(d.keys()))
    print("students:", len(d.get("students") or []))
    for s in (d.get("students") or []):
        print("  -", s.get("student"), s.get("matricule"), s.get("nom"), s.get("prenom"))
    print("notes:", list((d.get("notes") or {}).keys()))
    print("sessions:", d.get("sessions"))
    print("ue_info:", {k: v for k, v in (d.get("ue_info") or {}).items() if k != "enseignants"})
except Exception as e:
    import traceback
    traceback.print_exc()
    print("ERR:", type(e).__name__, str(e)[:800])