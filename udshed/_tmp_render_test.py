def run():
    import frappe
    from weasyprint import HTML

    from udshed.api.proces_verbal import get_proces_verbal_data

    data = get_proces_verbal_data("2025-2026", "IRT", "Licence 1", "Semestre 1")
    print("context:", {
        "filiere_code": data["context"]["filiere_code"],
        "semestre_numero": data["context"]["semestre_numero"],
        "year_label": data["context"]["year_label"],
    })
    print("nb_ues", len(data["ues"]), "nb_etudiants", len(data["etudiants"]))

    grades = ["A", "B+", "C", "B", "C-", "A-", "B", "C+", "F", "D", "B+", "A"]
    for ei, et in enumerate(data["etudiants"]):
        et["sem_ant_mpc"] = 2.8 + ei * 0.1
        et["sem_ant_tcc"] = 30
        et["mpc"] = 2.7 + ei * 0.05
        et["mention_short"] = ["TB", "AB", "P"][ei % 3]
        et["cycle_tci"] = 30 * 3
        et["cycle_tcc"] = 30 * 3 - ei * 3
        et["cycle_pct"] = round(et["cycle_tcc"] / et["cycle_tci"] * 100, 2)
        for uei, ue in enumerate(data["ues"]):
            if (ei + uei) % 4 == 3:
                et["resultats"][ue["name"]] = {"grade": "C-", "valide": False}
            else:
                et["resultats"][ue["name"]] = {"grade": grades[uei], "valide": True}
        et["mps"] = 68.5 + ei

    with open(
        frappe.get_app_path("udshed", "public", "print_templates", "proces_verbal.html"),
        encoding="utf-8",
    ) as fh:
        tpl = fh.read()
    html = frappe.render_template(tpl, {"data": data})
    pdf = HTML(string=html, base_url=frappe.utils.get_url()).write_pdf()
    print("PV pdf bytes", len(pdf))
    with open("/tmp/pv_model_test.pdf", "wb") as fh:
        fh.write(pdf)