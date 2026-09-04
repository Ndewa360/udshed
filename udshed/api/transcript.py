import frappe
from frappe import _

from udshed.api.proces_verbal import _credits_ue
from udshed.grade_calculation import get_grade_info, get_grade_scale, get_seuil_validation, get_student_cycle


def pdf_body_html(template, args, **kwargs):
    """Hook `pdf_body_html`: injects `data` (transcript context) into the
    "Releve Notes" print format, then delegates to Frappe's default renderer."""
    from frappe.utils.pdf import pdf_body_html as _default_pdf_body_html

    print_format = kwargs.get("print_format")
    doc = args.get("doc")
    if print_format and print_format.name == "Releve Notes" and doc:
        args = dict(args)
        args["data"] = get_transcript_data(doc)
    return _default_pdf_body_html(template, args, **kwargs)


@frappe.whitelist()
def download_releve_pdf(student):
    """Génère et télécharge le relevé de notes (PDF) d'un étudiant.

    Construit le corps HTML via le même pipeline que /printview (le hook
    `pdf_body_html` injecte `data`), puis le convertit en PDF avec WeasyPrint.
    """
    try:
        doc = frappe.get_doc("Student", student)
        doc.check_permission("print")

        from frappe.www.printview import get_rendered_template

        print_format = frappe.get_doc("Print Format", "Releve Notes")
        body = get_rendered_template(
            doc,
            print_format=print_format,
            meta=frappe.get_meta("Student"),
            no_letterhead=1,
            trigger_print=False,
        )

        html = (
            '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'
            + body
            + "</body></html>"
        )

        from weasyprint import HTML

        pdf = HTML(string=html, base_url=frappe.utils.get_url()).write_pdf()
    except Exception:
        frappe.log_error(" transcript download_releve_pdf")
        frappe.throw(_("Erreur lors de la génération du relevé de notes."))

    frappe.response["filename"] = "Releve_{0}.pdf".format(student.replace("/", "-"))
    frappe.response["filecontent"] = pdf
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/pdf"


@frappe.whitelist()
def get_transcript_data(doc):
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)

    student = doc.get("name")
    if not student:
        return {}

    student_doc = frappe.get_doc("Student", student)
    settings = frappe.get_single("Udshed Setting")

    semesters = frappe.get_all(
        "Resultat Semestre",
        filters={"student": student},
        fields=[
            "name", "semestre", "academic_year", "semester_index",
            "mps", "mpc", "total_credits", "credits_obtenus", "mention", "decision",
        ],
        order_by="semester_index asc",
    )

    semester_data = []
    total_credits_all = 0
    total_credits_obtenus = 0
    mpc_sur_4 = None
    highest_gpa = None
    position = 0

    for sem in semesters:
        year_label = frappe.get_cached_value(
            "Academic Year", sem.academic_year, "year_name"
        ) or sem.academic_year

        ue_results = frappe.get_all(
            "Resultat Academique",
            filters={
                "student": student,
                "semestre": sem.semestre,
                "academic_year": sem.academic_year,
            },
            fields=[
                "name", "teaching_unit", "ue_name", "note_finale", "note_pct",
                "grade", "point", "mention", "statut", "est_rattrapage",
                "decision_annee",
            ],
        )

        # Résolution des crédits par Teaching Unit pour cet étudiant.
        ues_credits = {}
        for ue in ue_results:
            ues_credits[ue.teaching_unit] = _credits_ue(
                ue.teaching_unit, student_doc.filiere,
                doc.get("niveau_actuel"),
            )

        # ── MPS / MPC au niveau UV (inchangé) ──────────────────────
        # Moyenne des points de la grille (sur 4) pondérée par crédits.
        credits_points_uv = sum(
            ues_credits[ue.teaching_unit] * (ue.point or 0)
            for ue in ue_results
        )
        credits_sem_uv = sum(
            ues_credits[ue.teaching_unit] for ue in ue_results
        )
        mps_sur_4 = (
            round(credits_points_uv / credits_sem_uv, 2)
            if credits_sem_uv > 0 else None
        )

        # MPC sur 4 (cumulative) : MPC(i) = (MPC(i-1)*(i-1) + MPS(i)) / i.
        position += 1
        if mps_sur_4 is not None:
            if mpc_sur_4 is None:
                mpc_sur_4 = mps_sur_4
            else:
                mpc_sur_4 = round(
                    (mpc_sur_4 * (position - 1) + mps_sur_4) / position, 2
                )
        if mps_sur_4 is not None:
            highest_gpa = (
                mps_sur_4 if highest_gpa is None else max(highest_gpa, mps_sur_4)
            )

        # ── Agrégation par UE (via unite_de_valeur) ─────────────────
        seuil = get_seuil_validation(get_student_cycle(student))

        ues_par_uv = {}
        for ue in ue_results:
            tu = frappe.get_cached_value(
                "Teaching Unit", ue.teaching_unit,
                ["course", "intitule_cours", "credits",
                 "semestre", "unite_de_valeur"],
                as_dict=True,
            ) or {}

            # Code / intitulé de l'UE depuis la UV (Teaching Unit Value)
            uv_code = tu.get("course", "") or ""
            uv_intitule = (
                ue.ue_name or tu.get("intitule_cours", "") or ue.teaching_unit
            )
            if tu.get("unite_de_valeur"):
                uv = frappe.get_cached_value(
                    "Teaching Unit Value", tu.unite_de_valeur,
                    ["code", "intitule"], as_dict=True,
                ) or {}
                uv_code = uv.get("code", uv_code)
                uv_intitule = uv.get("intitule", uv_intitule)

            credits_val = ues_credits.get(ue.teaching_unit, 0)

            if uv_code not in ues_par_uv:
                ues_par_uv[uv_code] = {
                    "code": uv_code,
                    "intitule": uv_intitule,
                    "total_credits": 0,
                    "items": [],
                    "has_rattrapage": False,
                }
            ues_par_uv[uv_code]["total_credits"] += credits_val
            ues_par_uv[uv_code]["items"].append({
                "note_pct": ue.note_pct or 0,
                "credits": credits_val,
                "est_rattrapage": ue.est_rattrapage or 0,
            })
            if ue.est_rattrapage:
                ues_par_uv[uv_code]["has_rattrapage"] = True

        # Note UE = Σ(note_pct_i × credits_i) / Σ(credits_i)
        ue_list = []
        for uv_code, groupe in ues_par_uv.items():
            tc = groupe["total_credits"]
            somme = sum(
                item["note_pct"] * item["credits"] for item in groupe["items"]
            )
            note_pct_ue = round(somme / tc, 2) if tc > 0 else 0
            info = get_grade_info(note_pct_ue, echelle=100) or {}

            ue_list.append({
                "code": groupe["code"],
                "intitule": groupe["intitule"],
                "credits": int(tc),
                "note_finale": round(note_pct_ue * 20 / 100, 2),
                "note_pct": note_pct_ue,
                "grade": info.get("grade", ""),
                "point": info.get("point", 0),
                "mention": info.get("mention", ""),
                "statut": (
                    "Validé" if note_pct_ue >= seuil else "Non Validé"
                ),
                "est_rattrapage": 1 if groupe["has_rattrapage"] else 0,
                "session": (
                    _("Rattrapage") if groupe["has_rattrapage"]
                    else _("Normale")
                ),
            })

        backlogs = [ue for ue in ue_list if ue["statut"] == "Non Validé"]

        total_credits_all += sem.total_credits or 0
        total_credits_obtenus += sem.credits_obtenus or 0

        semester_data.append({
            "label": sem.semestre,
            "academic_year": year_label,
            "academic_year_name": sem.academic_year,
            "index": sem.semester_index,
            "mps": sem.mps,
            "mpc": sem.mpc,
            "mps_sur_4": mps_sur_4,
            "mpc_sur_4": mpc_sur_4,
            "highest_gpa": highest_gpa,
            "cum_credits_inscrits": total_credits_all,
            "cum_credits_valides": total_credits_obtenus,
            "total_credits": sem.total_credits,
            "credits_obtenus": sem.credits_obtenus,
            "mention": sem.mention or "",
            "decision": sem.decision or "",
            "ues": ue_list,
            "backlogs": backlogs,
        })

    prev_mpc = semesters[-1].mpc if semesters else 0
    prev_credits = semesters[-1].credits_obtenus if semesters else 0

    # ── Décision annuelle LMD ───────────────────────────────────────
    # L'étudiant est ADMIS si le taux de crédits validés sur l'année
    # atteint le seuil de validation de son cycle (Udshed Setting /
    # Grade Formula). Ex : seuil 50 % sur 60 crédits -> 30 crédits min.
    if semester_data:
        derniere_annee = semester_data[-1]["academic_year_name"]
        sem_annee = [
            s for s in semester_data
            if s["academic_year_name"] == derniere_annee
        ]
        annee_credits_inscrits = sum(s["total_credits"] or 0 for s in sem_annee)
        annee_credits_valides = sum(s["credits_obtenus"] or 0 for s in sem_annee)
        annee_pct_validation = (
            round(annee_credits_valides / annee_credits_inscrits * 100, 2)
            if annee_credits_inscrits > 0 else 0
        )
        _cycle = get_student_cycle(student)
        _seuil = get_seuil_validation(_cycle)  # en %
        credits_min = annee_credits_inscrits * _seuil / 100.0
        decision_annuelle = "Admis" if annee_credits_valides >= credits_min else "Ajourné"
    else:
        annee_credits_inscrits = 0
        annee_credits_valides = 0
        annee_pct_validation = 0
        decision_annuelle = ""

    grade_scale = [
        {
            "note_min": g["note_min_pct"],
            "note_max": g["note_max_pct"],
            "grade": g["grade"],
            "point": g["point"],
            "mention": g["mention"],
        }
        for g in get_grade_scale()
    ]

    filiere_name = ""
    if student_doc.filiere:
        filiere_name = frappe.get_cached_value(
            "Field of study", student_doc.filiere, "name_of_field"
        ) or student_doc.filiere

    overall_decision = decision_annuelle
    profil = next(
        (s.mention for s in reversed(semesters) if s.mention), ""
    )
    pct_validation = (
        round(total_credits_obtenus / total_credits_all * 100, 2)
        if total_credits_all > 0
        else 0
    )

    cycle = "Licence"
    if hasattr(student_doc, "cycle") and student_doc.cycle:
        cycle = student_doc.cycle
    elif hasattr(student_doc, "niveau_actuel") and student_doc.niveau_actuel:
        niv = student_doc.niveau_actuel.lower()
        if "master" in niv or "m" in niv[:1]:
            cycle = "Master"

    return {
        "semesters": semester_data,
        "total_credits": total_credits_all,
        "total_credits_obtenus": total_credits_obtenus,
        "pct_validation": pct_validation,
        "grade_scale": grade_scale,
        "school_name": settings.school_name or "",
        "school_logo": settings.school_logo or "",
        "logo_file": "file://"
        + frappe.get_app_path("udshed", "public", "images", "logo.png"),
        "prev_mpc": prev_mpc,
        "prev_credits": prev_credits,
        "cumulative_gpa": mpc_sur_4,
        "highest_gpa": highest_gpa,
        "profil": profil,
        "overall_decision": overall_decision,
        "annee_credits_inscrits": annee_credits_inscrits,
        "annee_credits_valides": annee_credits_valides,
        "annee_pct_validation": annee_pct_validation,
        "filiere_name": filiere_name,
        "niveau_label": student_doc.niveau_actuel or "",
        "cycle": cycle,
        "date_emission": frappe.utils.today(),
        "reference_no": "TSCR-{}-{}".format(
            student, frappe.utils.today().replace("-", "")
        ),
        "student": {
            "name": student,
            "matricule": student_doc.matricule or "",
            "nom": student_doc.nom or "",
            "prenom": student_doc.prenom or "",
            "birth_date": student_doc.birth_date,
            "birth_place": student_doc.birth_place or "",
            "filiere": filiere_name,
            "niveau": student_doc.niveau_actuel or "",
            "cycle": cycle,
        },
    }
