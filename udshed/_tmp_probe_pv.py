def run():
    import frappe
    from udshed.api.proces_verbal import get_proces_verbal_data

    print("== Session Examen Note sample ==")
    for n in frappe.get_all(
        "Session Examen Note",
        fields=["student", "teaching_unit", "note_pct", "grade", "point",
                "statut", "mention", "academic_year" if False else "session_examen"],
        limit=8,
    ):
        print(n)

    print("== PV data IRT 2025-2026 Licence 1 Semestre 1 ==")
    data = get_proces_verbal_data("2025-2026", "IRT", "Licence 1", "Semestre 1")
    print("context:", data["context"])
    print("ues:", [(u["code"], u["credits"]) for u in data["ues"]])
    print("nb etudiants:", len(data["etudiants"]))
    for et in data["etudiants"][:3]:
        print(et["matricule"], et["nom"], et["prenom"],
              "mps", et["mps"], "mpc", et["mpc"],
              "tci", et["total_credits"], "tcc", et["credits_obtenus"],
              "pct", et["pct_validation"], "statut", et["statut"])
        for ue in data["ues"][:2]:
            r = et["resultats"].get(ue["name"] or {})
            print("    ", ue["code"], {k: r.get(k) for k in ("grade", "note_pct", "point", "valide")})
    print("statistiques:", data["statistiques"])