# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, today

TYPE_CC = "Controlle Continue (CC)"
TYPE_NORMALE = "Examen de session normal"
TYPE_RATTRAPAGE = "Examen de rattrapage"

TYPES_EVAL = [TYPE_CC, TYPE_NORMALE, TYPE_RATTRAPAGE]

NOTE_MAX = 20


def _get_enseignant_courant():
    """Enseignant (Teacher) lié à l'utilisateur connecté, ou None."""
    if frappe.session.user == "Administrator":
        return None
    return frappe.db.get_value("Teacher", {"email": frappe.session.user}, "name")


def _get_enseignant_full_name(enseignant):
    if not enseignant:
        return ""
    return frappe.db.get_value("Teacher", enseignant, "full_name") or enseignant


def _get_config():
    setting = frappe.get_single("Udshed Setting")
    return {
        "methode_calcul_cc": setting.methode_calcul_cc or "Moyenne arithmétique",
        "nb_meilleures_notes_cc": setting.nb_meilleures_notes_cc or 2,
        "exiger_programmation": bool(setting.exiger_programmation),
        "note_max": 20,
        "seuil_licence": setting.seuil_validation_licence or 50,
        "seuil_master": setting.seuil_validation_master or 60,
    }


def _get_niveau_name(filiere, niveau_label):
    """Retourne le name (ID) d'un niveau depuis son label, pour un niveau donné."""
    if not niveau_label:
        return None
    filiere_doc = frappe.get_doc("Field of study", filiere)
    for row in filiere_doc.field_of_study_level:
        if row.level == niveau_label:
            return row.name
    return None


def _get_calendar_defaut():
    calendar = frappe.db.get_value("Calendar Planing", {}, "name")
    if calendar:
        return calendar
    doc = frappe.new_doc("Calendar Planing")
    doc.nom_du_planing = "Défaut"
    doc.insert(ignore_permissions=True)
    return doc.name


def _get_or_create_session(args, type_dexamen):
    """Retrouve ou crée la Session Examen d'un type donné pour (année, semestre, filière, niveau)."""
    academic_year = args["academic_year"]
    semestre = args.get("semestre")
    filiere = args["filiere"]
    niveau = _get_niveau_name(filiere, args["niveau"])
    if not niveau:
        frappe.throw(_("Le niveau {0} est introuvable pour la filière {1}.").format(args["niveau"], filiere))

    sessions = frappe.get_all(
        "Session Examen",
        filters={"academic_year": academic_year, "semestre": semestre, "type_dexamen": type_dexamen},
        fields=["name"],
    )

    for session in sessions:
        if frappe.db.exists(
            "Session Examen Field of study Level",
            {"parent": session.name, "filiere": filiere, "niveau": niveau},
        ):
            return session.name

    if sessions:
        # Cherche une session existante qui concerne déjà cette filière/niveau
        for session in sessions:
            if frappe.db.exists(
                "Session Examen Field of study Level",
                {"parent": session.name, "filiere": filiere, "niveau": niveau},
            ):
                return session.name
        # Aucune session ne couvre encore cette filière/niveau : on l'ajoute à la première
        doc = frappe.get_doc("Session Examen", sessions[0].name)
        doc.append("classes_concernees", {"filiere": filiere, "niveau": niveau})
        doc.save(ignore_permissions=True)
        return doc.name

    doc = frappe.new_doc("Session Examen")
    doc.academic_year = academic_year
    doc.calendar = _get_calendar_defaut()
    doc.type_dexamen = type_dexamen
    doc.semestre = semestre
    doc.date_debut = today()
    doc.date_de_fin = today()
    doc.append("classes_concernees", {"filiere": filiere, "niveau": niveau})
    doc.insert(ignore_permissions=True)
    return doc.name


def _verifier_programmation(academic_year, teaching_unit):
    from frappe.query_builder import DocType

    planning = DocType("Planning Item")
    query = (
        frappe.qb.from_(planning)
        .select(planning.name)
        .where(
            (planning.cours == teaching_unit)
            & (planning.academic_year == academic_year)
            & (planning.type.isin(TYPES_EVAL))
        )
        .limit(1)
    )
    return bool(query.run())


def _verifier_programmation_requise(academic_year, teaching_unit):
    """Lève une erreur si la configuration exige que l'évaluation soit programmée."""
    config = _get_config()
    if config["exiger_programmation"] and not _verifier_programmation(academic_year, teaching_unit):
        frappe.throw(
            _(
                "L'UE {0} n'a aucune évaluation (CC, examen ou rattrapage) programmée pour {1} "
                "dans le planning académique."
            ).format(teaching_unit, academic_year)
        )


def _valider_lignes(rows):
    """Valide les lignes avant enregistrement : note dans [0,20], aucune ligne en double."""
    vus = set()
    for row in rows:
        student = row.get("student")
        if not student:
            frappe.throw(_("Une ligne d'étudiant est vide : impossible d'enregistrer."))
        if student in vus:
            frappe.throw(
                _("L'étudiant <b>{0}</b> apparaît plusieurs fois dans les notes à enregistrer.").format(student)
            )
        vus.add(student)

        for item in row.get("notes_cc") or []:
            valeur = item.get("note_cc")
            if valeur in (None, ""):
                continue
            valeur = flt(valeur)
            if valeur < 0 or valeur > NOTE_MAX:
                frappe.throw(
                    _("La note CC <b>{0}</b> de l'étudiant <b>{1}</b> doit être comprise entre 0 et {2}.").format(
                        item.get("cc_label") or "CC", student, NOTE_MAX
                    )
                )

        for champ in ("note_examen", "note_tp", "note_examen_rattrapage"):
            valeur = row.get(champ)
            if valeur in (None, ""):
                continue
            valeur = flt(valeur)
            if valeur < 0 or valeur > NOTE_MAX:
                frappe.throw(
                    _("La note <b>{0}</b> de l'étudiant <b>{1}</b> doit être comprise entre 0 et {2}.").format(
                        champ.replace("_", " "), student, NOTE_MAX
                    )
                )


def _get_ue_info(teaching_unit):
    tu = frappe.get_doc("Teaching Unit", teaching_unit)
    course = {}
    if tu.course:
        course_doc = frappe.get_value("Course", tu.course, ["code", "intitule"], as_dict=True)
        course = course_doc or {}

    enseignants = []
    for row in tu.table_enseignant or []:
        if not row.enseignant:
            continue
        nom = frappe.db.get_value("Teacher", row.enseignant, "full_name") or ""
        enseignants.append({"name": row.enseignant, "full_name": nom})

    return {
        "name": tu.name,
        "code": course.get("code") or "",
        "intitule": course.get("intitule") or tu.intitule_cours or tu.name,
        "credits": tu.credits,
        "type_ue": tu.type_ue,
        "semestre": tu.semestre,
        "enseignants": enseignants,
    }


def _get_etudiants(academic_year, filiere, niveau_label, teaching_unit):
    """Étudiants réinscrits (Validée), inscrits à l'UE (Inscrit, hors dispensés/reportés)."""
    regs = frappe.get_all(
        "Academic Reregistration",
        filters={
            "academic_year": academic_year,
            "filiere": filiere,
            "niveau": niveau_label,
            "statut": "Validée",
        },
        fields=["name", "student"],
    )
    if not regs:
        return []

    parents = [r.name for r in regs]
    inscrits = frappe.get_all(
        "Reregistration Course Item",
        filters={"parent": ["in", parents], "teaching_unit": teaching_unit, "statut": "Inscrit"},
        fields=["parent"],
    )
    parents_inscrits = {i.parent for i in inscrits}

    students = [r.student for r in regs if r.name in parents_inscrits]

    resultats = []
    for student in students:
        info = frappe.db.get_value("Student", student, ["matricule", "nom", "prenom"], as_dict=True)
        if not info:
            continue
        resultats.append(
            {
                "student": student,
                "matricule": info.matricule or student,
                "nom": info.nom or "",
                "prenom": info.prenom or "",
            }
        )

    resultats.sort(key=lambda s: (s["matricule"] or s["student"]).lower())
    return resultats


def _get_or_create_note(session, student, args):
    teaching_unit = args["teaching_unit"]
    existing = frappe.db.get_value(
        "Session Examen Note",
        {"session_examen": session, "student": student, "teaching_unit": teaching_unit},
        "name",
    )
    if existing:
        return frappe.get_doc("Session Examen Note", existing)

    doc = frappe.new_doc("Session Examen Note")
    doc.session_examen = session
    doc.student = student
    doc.teaching_unit = teaching_unit
    doc.filiere = args["filiere"]
    doc.niveau = _get_niveau_name(args["filiere"], args["niveau"])
    doc.type_ue = frappe.db.get_value("Teaching Unit", teaching_unit, "type_ue")
    doc.insert(ignore_permissions=True)
    return doc


def _charger_notes(students, teaching_unit, sessions):
    resultats = {"CC": {}, "Examen": {}, "TP": {}, "Rattrapage": {}}
    if not students:
        return resultats

    student_names = [s["student"] for s in students]
    session_names = list(sessions.values())
    notes = frappe.get_all(
        "Session Examen Note",
        filters={
            "session_examen": ["in", session_names],
            "student": ["in", student_names],
            "teaching_unit": teaching_unit,
        },
        fields=[
            "name",
            "session_examen",
            "student",
            "note_cc_moyenne",
            "cc_saisi",
            "note_examen",
            "examen_saisi",
            "note_tp",
            "tp_saisi",
            "note_examen_rattrapage",
            "rattrapage_saisi",
            "date_rattrapage",
            "note_examen_active",
            "note_finale",
            "grade",
            "point",
            "mention",
        ],
    )
    if not notes:
        return resultats

    note_names = [n.name for n in notes]
    items_cc = frappe.get_all(
        "Note CC Item",
        filters={"parent": ["in", note_names]},
        fields=["parent", "cc_label", "cc_weight", "note_cc"],
    )
    items_by_note = {}
    for item in items_cc:
        items_by_note.setdefault(item.parent, []).append(
            {
                "cc_label": item.cc_label,
                "cc_weight": item.cc_weight,
                "note_cc": item.note_cc,
            }
        )

    par_session = {}
    for n in notes:
        par_session.setdefault(n.session_examen, {})[n.student] = n

    for s in students:
        nom = s["student"]

        cc_note = (par_session.get(sessions["cc"]) or {}).get(nom)
        if cc_note:
            resultats["CC"][nom] = {
                "notes_cc": items_by_note.get(cc_note.name, []),
                "note_cc_moyenne": cc_note.note_cc_moyenne,
                "cc_saisi": cc_note.cc_saisi,
                "note_finale": cc_note.note_finale,
                "grade": cc_note.grade,
                "point": cc_note.point,
                "mention": cc_note.mention,
            }

        normale = (par_session.get(sessions["normale"]) or {}).get(nom)
        if normale:
            resultats["Examen"][nom] = {
                "note_examen": normale.note_examen,
                "examen_saisi": normale.examen_saisi,
                "note_examen_active": normale.note_examen_active,
                "note_finale": normale.note_finale,
                "grade": normale.grade,
                "point": normale.point,
                "mention": normale.mention,
            }
            resultats["TP"][nom] = {
                "note_tp": normale.note_tp,
                "tp_saisi": normale.tp_saisi,
            }

        rattrapage = (par_session.get(sessions["rattrapage"]) or {}).get(nom)
        initiale = normale.note_examen if normale else None
        if rattrapage:
            resultats["Rattrapage"][nom] = {
                "note_examen": rattrapage.note_examen
                if rattrapage.note_examen is not None
                else initiale,
                "note_examen_rattrapage": rattrapage.note_examen_rattrapage,
                "rattrapage_saisi": rattrapage.rattrapage_saisi,
                "date_rattrapage": rattrapage.date_rattrapage,
                "note_examen_active": rattrapage.note_examen_active,
                "note_finale": rattrapage.note_finale,
                "grade": rattrapage.grade,
                "point": rattrapage.point,
                "mention": rattrapage.mention,
            }
        elif initiale is not None:
            resultats["Rattrapage"][nom] = {
                "note_examen": initiale,
                "note_examen_rattrapage": None,
                "rattrapage_saisi": 0,
                "date_rattrapage": None,
                "note_examen_active": initiale,
                "note_finale": None,
                "grade": None,
                "point": None,
                "mention": None,
            }

    return resultats


def _verifier_non_publiee(session):
    statut = frappe.db.get_value("Session Examen", session, "statut")
    if statut == "Publiée":
        frappe.throw(_("La session {0} est publiée : les notes sont verrouillées.").format(session))


def _passer_saisi(note):
    """Fait passer une note au statut « Saisi » dès qu'une saisie est enregistrée.

    Le statut ne recule jamais : une note « Validé » ou « Publié » le reste.
    """
    if note.statut in (None, "", "Brouillon"):
        note.statut = "Saisi"


def _verifier_cc_modifiable(note):
    """Le CC validé ou publié ne peut plus être modifié (immutabilité du CC)."""
    if note.statut in ("Validé", "Publié"):
        frappe.throw(
            _("Les notes de CC de l'étudiant <b>{0}</b> sont {1} : elles ne peuvent plus être modifiées. "
              "Ne validez les notes de CC que lorsque la saisie est terminée.").format(
                note.student, note.statut.lower()
            )
        )


def _copier_cc_dans_note(args, student, note):
    """Reproduit le CC (lecture seule) de la session CC sur la note cible.

    Le CC est saisi dans sa propre session (Contrôle Continu) ; pour que la
    note de matière de la session normale soit complète (CC + Examen + TP),
    ses notes de CC sont synchronisées depuis la session CC. La session CC
    reste la seule source : on ne modifie jamais la note source.
    """
    if note.notes_cc:
        return
    session_cc = frappe.db.get_value(
        "Session Examen",
        {
            "academic_year": args["academic_year"],
            "semestre": args.get("semestre"),
            "type_dexamen": TYPE_CC,
        },
        "name",
    )
    if not session_cc:
        return
    source = frappe.db.get_value(
        "Session Examen Note",
        {
            "session_examen": session_cc,
            "student": student,
            "teaching_unit": args["teaching_unit"],
        },
        "name",
    )
    if not source:
        return
    source_doc = frappe.get_doc("Session Examen Note", source)
    for cc in source_doc.notes_cc:
        if cc.note_cc is not None:
            note.append(
                "notes_cc",
                {
                    "cc_label": cc.cc_label,
                    "cc_weight": cc.cc_weight,
                    "note_cc": cc.note_cc,
                },
            )


def _sauvegarder_cc(args, rows):
    _valider_lignes(rows)
    _verifier_programmation_requise(args["academic_year"], args["teaching_unit"])
    session = _get_or_create_session(args, TYPE_CC)
    _verifier_non_publiee(session)
    for row in rows:
        note = _get_or_create_note(session, row["student"], args)
        _verifier_cc_modifiable(note)
        note.set("notes_cc", [])
        for item in row.get("notes_cc") or []:
            note.append(
                "notes_cc",
                {
                    "cc_label": item.get("cc_label"),
                    "cc_weight": item.get("cc_weight"),
                    "note_cc": item.get("note_cc"),
                },
            )
        notes_saisies = [i for i in (row.get("notes_cc") or []) if i.get("note_cc") not in (None, "")]
        note.cc_saisi = 1 if notes_saisies else 0
        _passer_saisi(note)
        note.save(ignore_permissions=True)
    return len(rows)


def _sauvegarder_examen(args, rows):
    _valider_lignes(rows)
    _verifier_programmation_requise(args["academic_year"], args["teaching_unit"])
    session = _get_or_create_session(args, TYPE_NORMALE)
    _verifier_non_publiee(session)
    for row in rows:
        note = _get_or_create_note(session, row["student"], args)
        _copier_cc_dans_note(args, row["student"], note)
        note.note_examen = row.get("note_examen")
        note.examen_saisi = 1 if row.get("note_examen") not in (None, "") else 0
        _passer_saisi(note)
        note.save(ignore_permissions=True)
    return len(rows)


def _sauvegarder_tp(args, rows):
    _valider_lignes(rows)
    _verifier_programmation_requise(args["academic_year"], args["teaching_unit"])
    session = _get_or_create_session(args, TYPE_NORMALE)
    _verifier_non_publiee(session)
    for row in rows:
        note = _get_or_create_note(session, row["student"], args)
        _copier_cc_dans_note(args, row["student"], note)
        note.note_tp = row.get("note_tp")
        note.tp_saisi = 1 if row.get("note_tp") not in (None, "") else 0
        _passer_saisi(note)
        note.save(ignore_permissions=True)
    return len(rows)


def _sauvegarder_rattrapage(args, rows):
    _valider_lignes(rows)
    _verifier_programmation_requise(args["academic_year"], args["teaching_unit"])
    session = _get_or_create_session(args, TYPE_RATTRAPAGE)
    session_normale = _get_or_create_session(args, TYPE_NORMALE)
    _verifier_non_publiee(session)
    for row in rows:
        note = _get_or_create_note(session, row["student"], args)
        note.note_examen_rattrapage = row.get("note_examen_rattrapage")
        note.rattrapage_saisi = 1 if row.get("note_examen_rattrapage") not in (None, "") else 0

        # Conserver la note d'examen initiale sur la note de rattrapage afin que
        # la note retenue (note_examen_active = max(initiale, rattrapage)) soit correcte.
        initiale = frappe.db.get_value(
            "Session Examen Note",
            {
                "session_examen": session_normale,
                "student": row["student"],
                "teaching_unit": args["teaching_unit"],
            },
            "name",
        )
        if initiale:
            normale_doc = frappe.get_doc("Session Examen Note", initiale)
            note.note_examen = normale_doc.note_examen
            if normale_doc.note_examen is not None:
                note.examen_saisi = 1

            # Les composantes acquises en session normale sont conservées :
            # CC, TP, Rapport et Compétence ne sont pas à ressaisir au rattrapage.
            note.note_tp = normale_doc.note_tp
            if normale_doc.note_tp is not None:
                note.tp_saisi = 1
            note.note_rapport = normale_doc.note_rapport
            note.note_competence = normale_doc.note_competence

            note.notes_cc = []
            for cc in normale_doc.notes_cc:
                note.append(
                    "notes_cc",
                    {
                        "cc_label": cc.cc_label,
                        "cc_weight": cc.cc_weight,
                        "note_cc": cc.note_cc,
                    },
                )

        if row.get("date_rattrapage"):
            note.date_rattrapage = row.get("date_rattrapage")
        _passer_saisi(note)
        note.save(ignore_permissions=True)
    return len(rows)


@frappe.whitelist()
def charger_data(academic_year, filiere, niveau, semestre, teaching_unit):
    """Charge la configuration, l'UE, les étudiants et toutes les notes pour la page de saisie."""
    config = _get_config()

    if config["exiger_programmation"] and not _verifier_programmation(academic_year, teaching_unit):
        frappe.throw(
            _(
                "L'UE {0} n'a aucune évaluation (CC, examen ou rattrapage) programmée pour {1} "
                "dans le planning académique."
            ).format(teaching_unit, academic_year)
        )

    ue_info = _get_ue_info(teaching_unit)
    students = _get_etudiants(academic_year, filiere, niveau, teaching_unit)

    sessions = {
        "cc": _get_or_create_session(
            {"academic_year": academic_year, "semestre": semestre, "filiere": filiere, "niveau": niveau},
            TYPE_CC,
        ),
        "normale": _get_or_create_session(
            {"academic_year": academic_year, "semestre": semestre, "filiere": filiere, "niveau": niveau},
            TYPE_NORMALE,
        ),
        "rattrapage": _get_or_create_session(
            {"academic_year": academic_year, "semestre": semestre, "filiere": filiere, "niveau": niveau},
            TYPE_RATTRAPAGE,
        ),
    }

    sessions_meta = {}
    for cle, session in sessions.items():
        sessions_meta[cle] = {
            "name": session,
            "statut": frappe.db.get_value("Session Examen", session, "statut"),
        }

    notes = _charger_notes(students, teaching_unit, sessions)

    return {
        "config": config,
        "ue_info": ue_info,
        "students": students,
        "sessions": sessions_meta,
        "notes": notes,
    }


@frappe.whitelist()
def get_ues(academic_year, filiere, niveau, semestre=None, teacher=None):
    """Retourne les UE d'un (année, filière, niveau, semestre) pour les filtres de la page."""
    from frappe.query_builder import DocType

    filiere_doc = frappe.get_doc("Field of study", filiere)
    niveau_names = [row.name for row in filiere_doc.field_of_study_level if row.level == niveau]
    if not niveau_names:
        return []

    TeachingUnit = DocType("Teaching Unit")
    CourseLevel = DocType("Course Field of study level item")
    query = (
        frappe.qb.from_(TeachingUnit)
        .join(CourseLevel)
        .on(CourseLevel.parent == TeachingUnit.name)
        .select(
            TeachingUnit.name,
            TeachingUnit.intitule_cours,
            TeachingUnit.course,
            TeachingUnit.semestre,
            TeachingUnit.credits,
        )
        .where(
            (TeachingUnit.academic_year == academic_year)
            & (CourseLevel.filiere == filiere)
            & (CourseLevel.niveau.isin(niveau_names))
        )
        .distinct()
    )
    if semestre:
        query = query.where(TeachingUnit.semestre == semestre)
    if teacher:
        CourseTeacherItem = DocType("Course Teacher Item")
        query = (
            query.join(CourseTeacherItem)
            .on(CourseTeacherItem.parent == TeachingUnit.name)
            .where(CourseTeacherItem.enseignant == teacher)
        )

    resultats = []
    for ue in query.run(as_dict=True):
        code = ""
        if ue.course:
            code = frappe.db.get_value("Course", ue.course, "code") or ""
        resultats.append(
            {
                "name": ue.name,
                "intitule": ue.intitule_cours or ue.name,
                "code": code,
                "semestre": ue.semestre,
                "credits": ue.credits,
            }
        )
    resultats.sort(key=lambda u: (u["intitule"] or u["name"]).lower())
    return resultats


@frappe.whitelist()
def get_enseignant_courant():
    """Infos sur l'enseignant lié à l'utilisateur connecté (filtre Enseignant / droits)."""
    enseignant = _get_enseignant_courant()
    if not enseignant:
        return None
    return {"name": enseignant, "full_name": _get_enseignant_full_name(enseignant)}


@frappe.whitelist()
def get_enseignants(academic_year, filiere, niveau, semestre=None):
    """Liste les enseignants qui dispensent une UE dans le contexte sélectionné."""
    ues = get_ues(academic_year, filiere, niveau, semestre)
    if not ues:
        return []

    noms = [u["name"] for u in ues]
    rows = frappe.get_all(
        "Course Teacher Item",
        filters={"parent": ["in", noms]},
        fields=["parent", "enseignant"],
        distinct=True,
    )
    par_enseignant = {}
    for row in rows:
        if not row.enseignant:
            continue
        par_enseignant.setdefault(row.enseignant, set()).add(row.parent)

    resultats = [
        {"name": e, "full_name": _get_enseignant_full_name(e), "nb_ues": len(ues_p)}
        for e, ues_p in par_enseignant.items()
    ]
    resultats.sort(key=lambda t: (t["full_name"] or t["name"]).lower())
    return resultats


@frappe.whitelist()
def enregistrer_cc(academic_year, filiere, niveau, semestre, teaching_unit, rows):
    """Enregistre les notes de contrôle continu pour tous les étudiants."""
    args = {"academic_year": academic_year, "filiere": filiere, "niveau": niveau, "semestre": semestre, "teaching_unit": teaching_unit}
    n = _sauvegarder_cc(args, rows)
    return {"saved": n}


@frappe.whitelist()
def enregistrer_examen(academic_year, filiere, niveau, semestre, teaching_unit, rows):
    """Enregistre les notes de l'examen de session normale."""
    args = {"academic_year": academic_year, "filiere": filiere, "niveau": niveau, "semestre": semestre, "teaching_unit": teaching_unit}
    n = _sauvegarder_examen(args, rows)
    return {"saved": n}


@frappe.whitelist()
def enregistrer_tp(academic_year, filiere, niveau, semestre, teaching_unit, rows):
    """Enregistre les notes de travaux pratiques."""
    args = {"academic_year": academic_year, "filiere": filiere, "niveau": niveau, "semestre": semestre, "teaching_unit": teaching_unit}
    n = _sauvegarder_tp(args, rows)
    return {"saved": n}


@frappe.whitelist()
def enregistrer_rattrapage(academic_year, filiere, niveau, semestre, teaching_unit, rows):
    """Enregistre les notes de rattrapage."""
    args = {"academic_year": academic_year, "filiere": filiere, "niveau": niveau, "semestre": semestre, "teaching_unit": teaching_unit}
    n = _sauvegarder_rattrapage(args, rows)
    return {"saved": n}


@frappe.whitelist()
def valider_notes(session):
    """Valide toutes les notes d'une session d'examen (statut -> « Validé »).

    Étape obligatoire avant la publication : une session ne peut être
    publiée que si toutes ses notes sont validées.

    Args:
        session: Nom du document Session Examen

    Returns:
        dict: {"session": ..., "validated": n}
    """
    statut_session = frappe.db.get_value("Session Examen", session, "statut")
    if statut_session == "Publiée":
        frappe.throw(_("La session {0} est publiée : impossible de valider les notes.").format(session))

    names = frappe.get_all(
        "Session Examen Note",
        filters={"session_examen": session, "statut": ["in", ["Brouillon", "Saisi"]]},
        pluck="name",
    )
    for name in names:
        frappe.db.set_value("Session Examen Note", name, "statut", "Validé")

    return {"session": session, "validated": len(names)}


@frappe.whitelist()
def publier_session(session):
    """Publie une session d'examen.

    Toutes les notes de la session doivent d'abord être validées
    (statut « Validé »). Elles passent alors au statut « Publié » et
    deviennent consultables au babillard public. La session est clôturée.

    Args:
        session: Nom du document Session Examen

    Returns:
        dict: {"name", "statut", "date_publication"}
    """
    doc = frappe.get_doc("Session Examen", session)
    if doc.statut == "Publiée":
        return {"name": doc.name, "statut": doc.statut, "date_publication": doc.date_publication}

    non_validees = frappe.db.count(
        "Session Examen Note",
        {"session_examen": session, "statut": ["not in", ["Validé", "Publié"]]},
    )
    if non_validees:
        frappe.throw(
            _("Impossible de publier : {0} note(s) de la session {1} ne sont pas validées. "
              "Validez d'abord les notes avant de publier.").format(non_validees, session)
        )

    frappe.db.set_value(
        "Session Examen Note",
        {"session_examen": session, "statut": "Validé"},
        "statut",
        "Publié",
    )
    doc.db_set("statut", "Publiée")
    doc.db_set("date_publication", today())
    return {"name": doc.name, "statut": doc.statut, "date_publication": doc.date_publication}


def _colonnes_cc(cc_columns):
    """Normalise la liste des colonnes CC envoyee par le client (labels [+ poids])."""
    if isinstance(cc_columns, str):
        try:
            cc_columns = frappe.parse_json(cc_columns)
        except Exception:
            cc_columns = None
    return [
        c if isinstance(c, dict) else {"label": c, "weight": 1}
        for c in (cc_columns or [])
    ]


def _en_tetes(type_dexamen, cc_columns):
    colonnes = [_("Matricule"), _("Nom"), _("Prénom"), _("Crédit")]
    if type_dexamen == "CC":
        return colonnes + [c.get("label") for c in cc_columns] + [_("Moyenne CC")]
    if type_dexamen == "Examen":
        return colonnes + [_("Note d'examen")]
    if type_dexamen == "TP":
        return colonnes + [_("Note de TP")]
    if type_dexamen == "Rattrapage":
        return [_("Matricule"), _("Nom"), _("Prénom"), _("Note d'examen initiale"), _("Note de rattrapage"), _("Note retenue")]
    return colonnes


def _repondre_xlsx(rows, filename):
    from frappe.utils.xlsxutils import make_xlsx

    xlsx = make_xlsx(rows, "Notes")
    frappe.response["filename"] = filename
    frappe.response["filecontent"] = xlsx.getvalue()
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _lire_xlsx(file_url):
    from frappe.utils.file_manager import get_local_filename
    from openpyxl import load_workbook

    filename = get_local_filename(file_url)
    workbook = load_workbook(filename=filename, data_only=True)
    sheet = workbook.active
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def _valeur_note(valeur):
    if valeur in (None, ""):
        return None
    try:
        return flt(valeur)
    except Exception:
        return None


@frappe.whitelist()
def export_modele(type_dexamen, cc_columns=None):
    """Télécharge un modèle Excel vierge pour la saisie des notes."""
    cc_columns = _colonnes_cc(cc_columns)
    _repondre_xlsx([_en_tetes(type_dexamen, cc_columns)], "modele_{0}.xlsx".format(type_dexamen.lower()))


def _html_modele_pdf(titre, entetes, lignes):
    """Construit le HTML d'un modèle PDF imprimable (tableau avec bordures)."""
    entetes_html = "".join("<th>{0}</th>".format(frappe.utils.escape_html(h)) for h in entetes)
    lignes_html = ""
    for ligne in lignes:
        cellules = "".join("<td>{0}</td>".format(frappe.utils.escape_html(c or "")) for c in ligne)
        lignes_html += "<tr>{0}</tr>".format(cellules)
    if not lignes_html:
        lignes_html = "<tr><td colspan='{0}' style='text-align:center;color:#888;'>Aucun étudiant</td></tr>".format(
            len(entetes)
        )
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{ size: A4 landscape; margin: 18mm 14mm; }}
            body {{ font-family: Helvetica, Arial, sans-serif; color: #1d273b; }}
            .entete {{ margin-bottom: 18px; }}
            .entete h1 {{ font-size: 18px; margin: 0 0 4px; color: #1d273b; }}
            .entete p {{ margin: 0; font-size: 12px; color: #687178; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
            th, td {{ border: 1px solid #c4c9d1; padding: 6px 8px; text-align: left; }}
            th {{ background: #f4f6f9; font-weight: 600; }}
            td {{ height: 26px; }}
        </style>
    </head>
    <body>
        <div class="entete">
            <h1>{0}</h1>
            <p>Notes exprimées sur 20 — feuille de saisie à imprimer.</p>
        </div>
        <table>
            <thead><tr>{1}</tr></thead>
            <tbody>{2}</tbody>
        </table>
    </body>
    </html>
    """.format(frappe.utils.escape_html(titre), entetes_html, lignes_html)


@frappe.whitelist()
def export_modele_pdf(
    type_dexamen,
    cc_columns=None,
    academic_year=None,
    filiere=None,
    niveau=None,
    semestre=None,
    teaching_unit=None,
):
    """Télécharge un modèle PDF imprimable, étudiants pré-remplis si un contexte est fourni."""
    from frappe.utils.pdf import get_pdf

    cc_columns = _colonnes_cc(cc_columns)
    entetes = _en_tetes(type_dexamen, cc_columns)

    students = []
    credit = ""
    if teaching_unit and academic_year and filiere and niveau:
        students = _get_etudiants(academic_year, filiere, niveau, teaching_unit)
        credit = frappe.db.get_value("Teaching Unit", teaching_unit, "credits") or ""

    lignes = []
    for s in students:
        cellule = []
        for h in entetes:
            if h == "Matricule":
                cellule.append(s.get("matricule") or s.get("student") or "")
            elif h == "Nom":
                cellule.append(s.get("nom") or "")
            elif h == "Prénom":
                cellule.append(s.get("prenom") or "")
            elif h == "Crédit":
                cellule.append(credit)
            else:
                cellule.append("")
        lignes.append(cellule)

    titre = _("Modèle de saisie des notes — {0}").format(type_dexamen)
    html = _html_modele_pdf(titre, entetes, lignes)

    frappe.response["filename"] = "modele_{0}.pdf".format(type_dexamen.lower())
    frappe.response["filecontent"] = get_pdf(html)
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/pdf"


@frappe.whitelist()
def export_notes(academic_year, filiere, niveau, semestre, teaching_unit, type_dexamen, cc_columns=None):
    """Exporte les notes déjà saisies au format Excel."""
    cc_columns = _colonnes_cc(cc_columns)
    args = {"academic_year": academic_year, "filiere": filiere, "niveau": niveau, "semestre": semestre, "teaching_unit": teaching_unit}
    students = _get_etudiants(academic_year, filiere, niveau, teaching_unit)

    sessions = {
        "cc": _get_or_create_session(args, TYPE_CC),
        "normale": _get_or_create_session(args, TYPE_NORMALE),
        "rattrapage": _get_or_create_session(args, TYPE_RATTRAPAGE),
    }
    notes = _charger_notes(students, teaching_unit, sessions)
    credit = frappe.db.get_value("Teaching Unit", teaching_unit, "credits")

    lignes = [_en_tetes(type_dexamen, cc_columns)]
    for s in students:
        nom = s["student"]
        if type_dexamen == "CC":
            cc = notes["CC"].get(nom, {})
            valeurs = {}
            for item in cc.get("notes_cc", []):
                valeurs[item.get("cc_label")] = item.get("note_cc")
            lignes.append(
                [s["matricule"], s["nom"], s["prenom"], credit]
                + [valeurs.get(c.get("label")) for c in cc_columns]
                + [cc.get("note_cc_moyenne")]
            )
        elif type_dexamen == "Examen":
            ex = notes["Examen"].get(nom, {})
            lignes.append([s["matricule"], s["nom"], s["prenom"], credit, ex.get("note_examen")])
        elif type_dexamen == "TP":
            tp = notes["TP"].get(nom, {})
            lignes.append([s["matricule"], s["nom"], s["prenom"], credit, tp.get("note_tp")])
        elif type_dexamen == "Rattrapage":
            rt = notes["Rattrapage"].get(nom, {})
            lignes.append(
                [s["matricule"], s["nom"], s["prenom"], rt.get("note_examen"), rt.get("note_examen_rattrapage"), rt.get("note_examen_active")]
            )

    _repondre_xlsx(lignes, "notes_{0}_{1}.xlsx".format(teaching_unit.replace("/", "-"), type_dexamen.lower()))


@frappe.whitelist()
def importer_notes(file_url, type_dexamen, academic_year, filiere, niveau, semestre, teaching_unit, cc_columns=None):
    """Importe des notes depuis un fichier Excel (modèle exporté)."""
    cc_columns = _colonnes_cc(cc_columns)
    args = {"academic_year": academic_year, "filiere": filiere, "niveau": niveau, "semestre": semestre, "teaching_unit": teaching_unit}
    students = _get_etudiants(academic_year, filiere, niveau, teaching_unit)
    par_matricule = {s["matricule"]: s["student"] for s in students}

    lignes = _lire_xlsx(file_url)
    if not lignes or not lignes[0]:
        frappe.throw(_("Le fichier Excel est vide."))

    entetes = [str(h).strip() if h is not None else "" for h in lignes[0]]
    idx_matricule = entetes.index("Matricule") if "Matricule" in entetes else 0

    erreurs = []
    a_sauver = []

    for ligne in lignes[1:]:
        if not ligne or not any(l not in (None, "") for l in ligne):
            continue
        matricule = str(ligne[idx_matricule]).strip() if idx_matricule < len(ligne) and ligne[idx_matricule] is not None else ""
        student = par_matricule.get(matricule)
        if not student:
            erreurs.append(_("Matricule inconnu : {0}").format(matricule))
            continue

        if type_dexamen == "CC":
            items = []
            for i, c in enumerate(cc_columns):
                col = entetes.index(c.get("label")) if c.get("label") in entetes else None
                if col is None:
                    continue
                valeur = _valeur_note(ligne[col]) if col < len(ligne) else None
                if valeur is None:
                    continue
                items.append({"cc_label": c.get("label"), "cc_weight": c.get("weight"), "note_cc": valeur})
            if items:
                a_sauver.append({"student": student, "notes_cc": items})
        else:
            col_note = {
                "Examen": "Note d'examen",
                "TP": "Note de TP",
                "Rattrapage": "Note de rattrapage",
            }[type_dexamen]
            idx = entetes.index(col_note) if col_note in entetes else None
            valeur = _valeur_note(ligne[idx]) if idx is not None and idx < len(ligne) else None
            if valeur is None:
                continue
            champ = {"Examen": "note_examen", "TP": "note_tp", "Rattrapage": "note_examen_rattrapage"}[type_dexamen]
            a_sauver.append({"student": student, champ: valeur})

    if erreurs:
        frappe.throw(_("Import impossible :\n- {0}").format("\n- ".join(erreurs[:50])))

    if type_dexamen == "CC":
        n = _sauvegarder_cc(args, a_sauver)
    elif type_dexamen == "Examen":
        n = _sauvegarder_examen(args, a_sauver)
    elif type_dexamen == "TP":
        n = _sauvegarder_tp(args, a_sauver)
    else:
        n = _sauvegarder_rattrapage(args, a_sauver)

    return {"saved": n}
