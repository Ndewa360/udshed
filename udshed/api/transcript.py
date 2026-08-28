import frappe
from frappe import _

from udshed.grade_calculation import get_grade_scale


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

        ue_list = []
        for ue in ue_results:
            tu = frappe.get_cached_value(
                "Teaching Unit", ue.teaching_unit,
                ["course", "intitule_cours", "credits", "semestre"],
                as_dict=True,
            ) or {}

            credits_val = frappe.db.get_value(
                "Course Field of study level item",
                {"parent": ue.teaching_unit, "niveau": doc.get("niveau_actuel")},
                "course_poid",
            )
            if not credits_val:
                credits_val = tu.get("credits", 0)

            ue_list.append({
                "code": tu.get("course", "") or "",
                "intitule": ue.ue_name or tu.get("intitule_cours", "") or ue.teaching_unit,
                "credits": int(credits_val or 0),
                "note_finale": ue.note_finale,
                "note_pct": ue.note_pct,
                "grade": ue.grade or "",
                "point": ue.point or 0,
                "mention": ue.mention or "",
                "statut": ue.statut or "",
                "est_rattrapage": ue.est_rattrapage or 0,
                "session": _("Rattrapage") if ue.est_rattrapage else _("Normale"),
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
            "total_credits": sem.total_credits,
            "credits_obtenus": sem.credits_obtenus,
            "mention": sem.mention or "",
            "decision": sem.decision or "",
            "ues": ue_list,
            "backlogs": backlogs,
        })

    prev_mpc = semesters[-1].mpc if semesters else 0
    prev_credits = semesters[-1].credits_obtenus if semesters else 0

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

    overall_decision = semesters[-1].decision if semesters else ""
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
        "overall_decision": overall_decision,
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
