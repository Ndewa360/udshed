# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import re
import unicodedata

import frappe
from frappe import _
from frappe.utils import flt, today

from udshed.grade_calculation import (
    combinaison_detectee,
    combinaison_type_ue,
    get_formula,
    get_seuil_validation,
)

TYPE_CC = "Controlle Continue (CC)"
TYPE_NORMALE = "Examen de session normal"
TYPE_RATTRAPAGE = "Examen de rattrapage"

TYPES_EVAL = [TYPE_CC, TYPE_NORMALE, TYPE_RATTRAPAGE]

NOTE_MAX = 20

# Libellés du « Type d'évaluation » choisi côté interface -> mode interne de la
# fonction d'enregistrement (cc / examen / rattrapage).
TYPE_SAISIE_ALIASES = {
    "Contrôle continu (CC)": "cc",
    "Controle continue (CC)": "cc",
    "Controle continu (CC)": "cc",
    "Contrôle continu": "cc",
    "CC": "cc",
    "Examen normal": "examen",
    "Examen": "examen",
    "Rattrapage": "rattrapage",
}

# Clé de session (« cc » / « normale » / « rattrapage ») -> libellé interne du
# type d'évaluation, et mode de saisie correspondant. Le sélecteur de session
# de la page utilise ces clés pour router la session choisie vers le bon type.
TYPE_DE_SESSION = {
    "cc": TYPE_CC,
    "normale": TYPE_NORMALE,
    "rattrapage": TYPE_RATTRAPAGE,
}
SESSION_DE_MODE = {"cc": "cc", "normale": "examen", "rattrapage": "rattrapage"}


def _mode_saisie(type_dexamen=None):
    """Normalise le type d'évaluation choisi côté interface en un mode interne.

    Les libellés internes aux sessions (« Examen de session normal », « Examen
    de rattrapage », « Controlle Continue (CC) ») sont aussi reconnus : sans
    cela, un appel passé avec `TYPE_RATTRAPAGE` retombait sur « examen » et
    produisait la fiche de report — et les codes — de la session normale.

    Repli sur « examen » si le libellé est inconnu ou absent afin de préserver
    le comportement historique de la saisie unifiée (CC + CCTP + EXAMTP + EXAM).
    """
    cle = (type_dexamen or "").strip()
    if cle in TYPE_SAISIE_ALIASES:
        return TYPE_SAISIE_ALIASES[cle]
    if cle == TYPE_RATTRAPAGE:
        return "rattrapage"
    if cle == TYPE_CC:
        return "cc"
    return "examen"


def _cle_session(type_dexamen):
    """Clé de session (« cc » / « normale » / « rattrapage ») depuis un libellé d'interface."""
    mode = _mode_saisie(type_dexamen)
    if mode == "cc":
        return "cc"
    if mode == "rattrapage":
        return "rattrapage"
    return "normale"


def _cycle_pour_niveau(niveau_label):
    """Cycle (Licence / BTS / Master) déduit du libellé d'un niveau.

    Les libellés de niveau sont normalisés par la grille de la filière
    (ex : « Licence 1 », « Master 2 », « BTS 1 »). Repli sur Licence.
    """
    label = (niveau_label or "").lower()
    if label.startswith("master"):
        return "Master"
    if label.startswith("bts"):
        return "BTS"
    return "Licence"


def _serialiser_formule(formula, cycle, combinaison):
    """Représentation lisible d'une Grade Formula pour la page de saisie.

    Source de vérité des poids : les composantes de la formule active.
    Aucun poids n'est saisi manuellement dans la saisie des notes.
    """
    composantes = [
        {"composante": c.composante, "pourcentage": float(c.pourcentage or 0)}
        for c in formula.components
        if (c.pourcentage or 0) > 0
    ]
    return {
        "nom": formula.name,
        "cycle": cycle,
        "combinaison": combinaison,
        "composantes": composantes,
        "methode_calcul_cc": formula.methode_calcul_cc,
        "nb_meilleures_notes_cc": formula.nb_meilleures_notes_cc,
        "seuil_validation": formula.seuil_validation,
        "methode_arrondi": formula.methode_arrondi,
    }


def _formule_pour_ue(teaching_unit, filiere=None, niveau=None):
    """Formule active attendue pour une UE (cycle du niveau + combinaison du type d'UE).

    Returns:
        dict | None: formule sérialisée, ou None si aucune formule active.
    """
    type_ue = frappe.db.get_value("Teaching Unit", teaching_unit, "type_ue") or "Sans TP"
    cycle = _cycle_pour_niveau(niveau or "")
    combinaison = combinaison_type_ue(type_ue)
    formula = get_formula(cycle, combinaison)
    if not formula:
        return None
    return _serialiser_formule(formula, cycle, combinaison)


def _formule_detectee(teaching_unit, filiere, niveau, notes, students):
    """Formule correspondant à la combinaison détectée des notes réellement saisies.

    La combinaison est l'union des évaluations renseignées dans la session
    normale (CC, CCTP, EXAMTP, EXAM). Sans aucune note saisie, on retombe sur
    la formule attendue du type d'UE.

    Returns:
        dict | None: formule sérialisée, ou None si aucune formule active.
    """
    remplis = set()
    for s in students or []:
        ex = (notes or {}).get("Examen", {}).get(s["student"], {})
        # Drapeaux *saisi : le stockage Currency ramène les champs non
        # saisis à 0.0, ils ne comptent donc jamais comme remplis.
        if ex.get("cc_saisi"):
            remplis.add("Controle Continu(CC)")
        if ex.get("cctp_saisi"):
            remplis.add("Controle Continu Travaux Pratiques(CCTP)")
        if ex.get("examtp_saisi"):
            remplis.add("Examen Travaux Pratiques(EXAMTP)")
        if ex.get("examen_saisi") or ex.get("rattrapage_saisi"):
            remplis.add("Examen")
    if remplis:
        cycle = _cycle_pour_niveau(niveau or "")
        combinaison = combinaison_detectee(remplis)
        formula = get_formula(cycle, combinaison)
        if formula:
            return _serialiser_formule(formula, cycle, combinaison)
    return _formule_pour_ue(teaching_unit, filiere, niveau)


def _get_enseignant_courant():
    """Enseignant (Teacher) lié à l'utilisateur connecté, ou None."""
    if frappe.session.user == "Administrator":
        return None
    return frappe.db.get_value("Teacher", {"email": frappe.session.user}, "name")


def _get_enseignant_full_name(enseignant):
    if not enseignant:
        return ""
    return frappe.db.get_value("Teacher", enseignant, "full_name") or enseignant


def _semestre_effectif(args):
    """Semestre demandé, ou celui de l'UE si le client n'en a pas transmis."""
    semestre = args.get("semestre")
    if semestre:
        return semestre
    return frappe.db.get_value("Teaching Unit", args["teaching_unit"], "semestre")


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


def _sessions_du_contexte(args, type_dexamen):
    """Sessions d'un type pour (année, semestre), de la plus ancienne à la plus récente.

    `order_by="creation asc"` est explicite et indispensable : sans tri, Frappe
    renvoie la dernière session *modifiée*, si bien qu'enregistrer une note
    ailleurs suffisait à faire basculer la page de saisie sur une autre
    session. Le tri par création rend le choix stable et reproductible.
    """
    return frappe.get_all(
        "Session Examen",
        filters={
            "academic_year": args["academic_year"],
            "semestre": args.get("semestre"),
            "type_dexamen": type_dexamen,
        },
        fields=["name", "statut", "date_debut", "date_de_fin", "date_publication", "creation"],
        order_by="creation asc",
    )


def _sessions_couvrant(args, type_dexamen):
    """Sessions d'un type couvrant réellement la filière/niveau du contexte."""
    filiere = args.get("filiere")
    if not filiere:
        return _sessions_du_contexte(args, type_dexamen)
    niveau = _get_niveau_name(filiere, args.get("niveau"))
    if not niveau:
        return []
    return [
        s
        for s in _sessions_du_contexte(args, type_dexamen)
        if frappe.db.exists(
            "Session Examen Field of study Level",
            {"parent": s["name"], "filiere": filiere, "niveau": niveau},
        )
    ]


def _valider_session_cible(args, session_examen, type_dexamen):
    """Contrôle la session fournie par le sélecteur avant de l'utiliser.

    Sans ce contrôle, un client pourrait écrire dans la session d'une autre
    filière, d'un autre semestre ou d'un autre type d'évaluation.
    """
    if not session_examen or session_examen in ("auto", "Nouvelle", ""):
        return None
    if not frappe.db.exists("Session Examen", session_examen):
        frappe.throw(
            _("La session d'examen {0} est introuvable.").format(session_examen)
        )
    data = frappe.db.get_value(
        "Session Examen", session_examen, ["academic_year", "semestre", "type_dexamen"], as_dict=True
    )
    if data.academic_year != args["academic_year"] or data.semestre != args.get("semestre"):
        frappe.throw(
            _("La session {0} n'appartient pas à {1} / {2}.").format(
                session_examen, args["academic_year"], args.get("semestre")
            )
        )
    if data.type_dexamen != type_dexamen:
        frappe.throw(
            _("La session {0} n'est pas une session « {1} ».").format(session_examen, type_dexamen)
        )
    filiere = args.get("filiere")
    if filiere:
        niveau = _get_niveau_name(filiere, args.get("niveau"))
        if niveau and not frappe.db.exists(
            "Session Examen Field of study Level",
            {"parent": session_examen, "filiere": filiere, "niveau": niveau},
        ):
            frappe.throw(
                _("La session {0} ne couvre pas la classe {1} / {2}.").format(
                    session_examen, filiere, niveau
                )
            )
    return session_examen


def _get_or_create_session(args, type_dexamen, session_examen=None):
    """Retrouve ou crée la Session Examen d'un type pour (année, semestre, filière, niveau).

    `session_examen` permet de forcer une session existante (sélecteur de
    session de la page de saisie). Elle est validée avant usage.
    """
    session_cible = _valider_session_cible(args, session_examen, type_dexamen)
    if session_cible:
        return session_cible
    academic_year = args["academic_year"]
    semestre = args.get("semestre")
    filiere = args["filiere"]
    niveau = _get_niveau_name(filiere, args["niveau"])
    if not niveau:
        frappe.throw(_("Le niveau {0} est introuvable pour la filière {1}.").format(args["niveau"], filiere))

    sessions = _sessions_du_contexte(args, type_dexamen)

    for session in sessions:
        if frappe.db.exists(
            "Session Examen Field of study Level",
            {"parent": session.name, "filiere": filiere, "niveau": niveau},
        ):
            return session.name

    if sessions:
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


def _chercher_session(args, type_dexamen):
    """Retrouve (sans la créer) la Session Examen d'un type pour la filière/niveau.

    La plus ancienne l'emporte : c'est la session d'origine du couple
    (année, semestre, filière, niveau, type). Le sélecteur de session de la
    page permet d'afficher et de saisir les autres.
    """
    candidates = _sessions_couvrant(args, type_dexamen)
    if candidates:
        return candidates[0]["name"]
    toutes = _sessions_du_contexte(args, type_dexamen)
    return toutes[0]["name"] if toutes else None


def _verifier_programmation(academic_year, teaching_unit, type_dexamen=None):
    """Vérifie l'existence d'une programmation (Planning Item) pour une UE.

    Sans ``type_dexamen``, accepte n'importe quelle évaluation (CC, examen,
    rattrapage). Avec ``type_dexamen``, la programmation doit correspondre
    exactement au type d'examen passé.
    """
    from frappe.query_builder import DocType

    planning = DocType("Planning Item")
    query = (
        frappe.qb.from_(planning)
        .select(planning.name)
        .where(
            (planning.cours == teaching_unit)
            & (planning.academic_year == academic_year)
        )
    )
    if type_dexamen:
        query = query.where(planning.type == type_dexamen)
    else:
        query = query.where(planning.type.isin(TYPES_EVAL))
    return bool(query.limit(1).run())


def _verifier_programmation_sessions(session):
    """Bloque la validation / publication si l'examen n'est pas programmé.

    Règle métier : une session d'examen ne peut être validée ni publiée que
    si chaque UE ayant des notes dans la session dispose d'une programmation
    (Planning Item) du même type d'examen dans le planning académique.
    """
    doc = frappe.get_doc("Session Examen", session)
    teaching_units = frappe.db.sql_list(
        """SELECT DISTINCT teaching_unit
           FROM `tabSession Examen Note`
           WHERE session_examen = %s AND teaching_unit IS NOT NULL""",
        session,
    )
    if not teaching_units:
        return
    non_programmees = [
        tu
        for tu in teaching_units
        if not _verifier_programmation(doc.academic_year, tu, doc.type_dexamen)
    ]
    if non_programmees:
        frappe.throw(
            _("Impossible de valider ou publier : l'examen « {0} » n'est pas programmé "
              "dans le planning académique pour l'UE {1} (année {2}).").format(
                doc.type_dexamen,
                ", ".join(non_programmees),
                doc.academic_year,
            )
        )


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


def _verifier_acces_enseignant(teaching_unit):
    """Vérifie que l'utilisateur connecté a le droit de gérer les notes d'une UE.

    - Administrateur / System Manager : accès total
    - Coordonnateur / Gestionnaire de planning : accès (gestion de filière)
    - Enseignant : uniquement les UE qu'il dispense (Course Teacher Item)
    """
    user = frappe.session.user
    roles = frappe.get_roles(user)
    if user == "Administrator" or "System Manager" in roles:
        return
    if (
        "Planning Manager" in roles
        or "Coordonateur" in roles
        or "Coordinateur" in roles
    ):
        return
    if "Teacher" in roles:
        enseignant = _get_enseignant_courant()
        if enseignant and frappe.db.exists(
            "Course Teacher Item",
            {"parent": teaching_unit, "enseignant": enseignant},
        ):
            return
        frappe.throw(
            _(
                "Vous n'êtes pas autorisé(e) à gérer les notes de l'UE <b>{0}</b> "
                "(cet enseignant ne dispense pas ce cours)."
            ).format(teaching_unit)
        )
    frappe.throw(frappe.PermissionError)


def _valider_lignes(rows):
    """Valide les lignes avant enregistrement : note dans [0,20], aucune ligne en double.

    Retourne la liste des lignes normalisées (accepte aussi une chaîne JSON).
    """
    if isinstance(rows, str):
        try:
            rows = frappe.parse_json(rows) or []
        except Exception:
            frappe.throw(_("Les lignes de notes envoyées ne sont pas valides (format JSON)."))
    if not isinstance(rows, list):
        frappe.throw(_("Les lignes de notes doivent être une liste."))
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

        for champ in ("note_examen", "note_tp", "note_examen_rattrapage", "note_cctp", "note_examtp", "cc"):
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
    return rows


def _credits_ue(teaching_unit, filiere=None, niveau=None):
    """Crédits d'une UE : priorité à la grille de matière (course_poid filière/niveau), sinon le champ Teaching Unit."""
    if filiere and niveau:
        fos_doc = frappe.get_doc("Field of study", filiere)
        niveau_name = None
        for row in fos_doc.field_of_study_level or []:
            if row.level == niveau:
                niveau_name = row.name
                break
        if niveau_name:
            poid = frappe.db.get_value(
                "Course Field of study level item",
                {"parent": teaching_unit, "filiere": filiere, "niveau": niveau_name},
                "course_poid",
            )
            if poid:
                return poid
    credits = frappe.db.get_value("Teaching Unit", teaching_unit, "credits")
    return credits or 0


def _get_ue_info(teaching_unit, filiere=None, niveau=None):
    tu = frappe.get_doc("Teaching Unit", teaching_unit)
    course = {}
    if tu.course:
        course_doc = frappe.get_value("Course", tu.course, ["code", "intitule"], as_dict=True)
        course = course_doc or {}

    enseignants = []
    vus = set()
    for row in tu.table_enseignant or []:
        if not row.enseignant or row.enseignant in vus:
            continue
        vus.add(row.enseignant)
        nom = frappe.db.get_value("Teacher", row.enseignant, "full_name") or ""
        enseignants.append({"name": row.enseignant, "full_name": nom})

    return {
        "name": tu.name,
        "code": course.get("code") or "",
        "intitule": course.get("intitule") or tu.intitule_cours or tu.name,
        "credits": _credits_ue(teaching_unit, filiere, niveau),
        "type_ue": tu.type_ue,
        "semestre": tu.semestre,
        "enseignants": enseignants,
    }


def _get_etudiants(academic_year, filiere, niveau_label, teaching_unit):
    """Tous les étudiants de la classe (filière/niveau) présents sur le cours.

    La liste est construite depuis les réinscriptions académiques validées de la
    filière/niveau (Semestre 1, Semestre 2 ou Les deux), pour prendre en compte
    toute la classe : dès qu'une grille est importée, tous les étudiants inscrits
    dans la classe apparaissent sur les cours, sauf ceux explicitement marqués
    « Dispensé » ou « Reporté » sur ce cours.
    """
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
    exclus = frappe.get_all(
        "Reregistration Course Item",
        filters={
            "parent": ["in", parents],
            "teaching_unit": teaching_unit,
            "statut": ["in", ["Dispensé", "Reporté"]],
        },
        fields=["parent"],
    )
    exclus_parents = {e.parent for e in exclus}

    # Un même étudiant peut apparaître sur plusieurs réinscriptions validées
    # (saisie en double) : on déduplique pour ne renvoyer qu'une seule ligne.
    students = []
    vus = set()
    for r in regs:
        if r.name in exclus_parents:
            continue
        if r.student in vus:
            continue
        vus.add(r.student)
        students.append(r.student)

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

    def _cle_nom(s):
        norm = unicodedata.normalize("NFD", "{} {}".format(s["nom"] or "", s["prenom"] or ""))
        return norm.encode("ascii", "ignore").decode().lower()

    resultats.sort(key=lambda s: (_cle_nom(s), (s["matricule"] or s["student"]).lower()))
    return resultats


def _codes_fiches_anonymat(teaching_unit, type_dexamen=""):
    """Codes d'anonymat faisant foi, par étudiant, pour une matière et un type.

    L'anonymat est unique dans l'application : il est porté par le document
    « Examen Anonymat », c'est-à-dire par la fiche d'anonymat, au format
    AN0001, AN0002, AN0003…, et c'est ce code qui est écrit sur les copies.
    Toutes les feuilles qui doivent correspondre à ces copies (fiche de
    report, feuille de saisie, relevés, exports) lisent donc cette source.

    Aucun code n'est inventé ici : un code calculé localement donnait un
    numéro différent de celui des copies pour un même étudiant.

    Returns:
        dict[str, str]: ``{student: code}`` pour les fiches existantes.
    """
    if not teaching_unit:
        return {}

    # `Session Examen.type_dexamen` stocke le libellé long (« Examen de session
    # normal »), tandis que l'interface peut envoyer « Examen ». Toutes les
    # écritures possibles du type sont donc admises.
    mode = _mode_saisie(type_dexamen)
    if mode == "rattrapage":
        variantes = {TYPE_RATTRAPAGE, "Rattrapage", "RATTRAPAGE"}
    elif mode == "cc":
        variantes = {TYPE_CC, "CC", "Controle continu (CC)", "CONTROLE CONTINU (CC)"}
    else:
        variantes = {TYPE_NORMALE, "Examen", "Examen normal", "EXAMEN"}
    variantes = {v for v in variantes if v}

    conditions = " or ".join(
        "s.type_dexamen = %(v{0})s".format(i) for i in range(len(variantes))
    )
    params = {"teaching_unit": teaching_unit}
    params.update({"v{0}".format(i): v for i, v in enumerate(sorted(variantes))})

    sql = (
        "select a.student, a.code_anonymat "
        "from `tabExamen Anonymat` a "
        "inner join `tabSession Examen` s on s.name = a.session_examen "
        "where a.teaching_unit = %(teaching_unit)s "
        "and (" + conditions + ") "
        "order by s.creation desc"
    )

    fiches = frappe.db.sql(sql, params, as_dict=True)

    codes = {}
    for fiche in fiches:
        # Première fiche rencontrée (sessions les plus récentes) : une seule
        # valeur par étudiant.
        codes.setdefault(fiche.student, fiche.code_anonymat)
    return codes


def _codes_anonymes(students, teaching_unit=None, type_dexamen=""):
    """Code d'anonymat à afficher pour chaque étudiant (source unique).

    Ne renvoie que des codes réellement portés par une fiche d'anonymat. Un
    étudiant sans code n'est pas inventorié : aucun numéro n'est fabriqué à la
    volée, sinon la fiche imprimée ne correspondrait à aucune copie.
    """
    codes = _codes_fiches_anonymat(teaching_unit, type_dexamen)
    return {s["student"]: codes[s["student"]] for s in students or [] if s["student"] in codes}


def _exiger_codes_anonymes(students, teaching_unit, type_dexamen, libelle=""):
    """Codes d'anonymat de la matière, en refusant de travailler sans.

    Sans fiche d'anonymat, il n'existe aucun code : lTeacher doit d'abord
    lancer la génération des codes de la session, faute de quoi la fiche
    imprimée porterait des numéros qui ne correspondent à aucune copie.
    """
    codes = _codes_anonymes(students, teaching_unit, type_dexamen)
    manquants = [s for s in students or [] if not codes.get(s["student"])]
    if manquants:
        frappe.throw(
            _("Aucun code d'anonymat n'a été généré pour cette matière. Générez les "
              "codes d'anonymat de la session avant d'utiliser {0}, afin que les "
              "numéros imprimés correspondent aux copies.").format(
                libelle or _("ces codes d'anonymat")
            )
        )
    return codes


def _identite_export(s, anonymes, codes):
    """Cellules (Matricule, Nom, Prénom) d'un export, anonymisées si demandé."""
    if anonymes:
        return [codes.get(s["student"], ""), "", ""]
    return [s["matricule"], s["nom"], s["prenom"]]


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
    # Exclure les sessions inexistantes (None) pour éviter des requêtes invalides.
    session_names = [s for s in sessions.values() if s]
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
            "note_cctp",
            "cctp_saisi",
            "note_examtp",
            "examtp_saisi",
            "note_examen_rattrapage",
            "rattrapage_saisi",
            "date_rattrapage",
            "note_examen_active",
            "note_finale",
            "note_pct",
            "grade",
            "point",
            "mention",
            "statut",
        ],
    )
    if not notes:
        return resultats

    note_names = [n.name for n in notes]
    items_cc = frappe.get_all(
        "Note CC Item",
        filters={"parent": ["in", note_names]},
        fields=["parent", "cc_label", "cc_weight", "note_cc"],
        order_by="idx asc",
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
                "note_cc_moyenne": normale.note_cc_moyenne,
                "cc_saisi": normale.cc_saisi,
                "note_examen": normale.note_examen,
                "examen_saisi": normale.examen_saisi,
                "note_tp": normale.note_tp,
                "tp_saisi": normale.tp_saisi,
                "note_cctp": normale.note_cctp,
                "cctp_saisi": normale.cctp_saisi,
                "note_examtp": normale.note_examtp,
                "examtp_saisi": normale.examtp_saisi,
                "note_examen_active": normale.note_examen_active,
                "note_finale": normale.note_finale,
                "note_pct": normale.note_pct,
                "grade": normale.grade,
                "point": normale.point,
                "mention": normale.mention,
                "statut": normale.statut,
            }
            resultats["TP"][nom] = {
                "note_tp": normale.note_tp,
                "tp_saisi": normale.tp_saisi,
            }

        rattrapage = (par_session.get(sessions["rattrapage"]) or {}).get(nom)
        initiale = normale.note_examen if normale and normale.examen_saisi else None

        # Moyenne CC effective au rattrapage : celle portée par la note de
        # rattrapage (copiée à l'enregistrement), sinon la session CC, sinon le
        # CC conservé sur la note de la session normale.
        cc_moyenne = rattrapage.note_cc_moyenne if rattrapage and rattrapage.cc_saisi else None
        if cc_moyenne is None and cc_note and cc_note.cc_saisi:
            cc_moyenne = cc_note.note_cc_moyenne
        if cc_moyenne is None and normale and normale.cc_saisi:
            cc_moyenne = normale.note_cc_moyenne

        if rattrapage:
            resultats["Rattrapage"][nom] = {
                "note_examen": rattrapage.note_examen
                if rattrapage.examen_saisi
                else initiale,
                "note_examen_rattrapage": rattrapage.note_examen_rattrapage,
                "rattrapage_saisi": rattrapage.rattrapage_saisi,
                "date_rattrapage": rattrapage.date_rattrapage,
                "note_examen_active": rattrapage.note_examen_active,
                "note_finale": rattrapage.note_finale,
                "note_pct": rattrapage.note_pct,
                "grade": rattrapage.grade,
                "point": rattrapage.point,
                "mention": rattrapage.mention,
                "note_cc_moyenne": rattrapage.note_cc_moyenne
                if rattrapage.cc_saisi
                else cc_moyenne,
                "cc_saisi": rattrapage.cc_saisi,
            }
        elif initiale is not None:
            resultats["Rattrapage"][nom] = {
                "note_examen": initiale,
                "note_examen_rattrapage": None,
                "rattrapage_saisi": 0,
                "date_rattrapage": None,
                "note_examen_active": initiale,
                "note_finale": None,
                "note_pct": None,
                "grade": None,
                "point": None,
                "mention": None,
                "note_cc_moyenne": cc_moyenne,
                "cc_saisi": 1 if cc_moyenne is not None else 0,
            }

    return resultats


def _sessions_avec_choix(args, session_examen=None, type_dexamen=None):
    """Les trois sessions (CC / normale / rattrapage) en respectant le sélecteur.

    Sans `session_examen`, la résolution est automatique comme historiquement.
    Avec, la session choisie s'applique au type d'évaluation affiché et les
    deux autres restent résolus automatiquement : c'est ce qui permet à un
    PV ou à un export de refléter exactement la session affichée à l'écran.
    """
    sessions = {
        cle: _get_or_create_session(args, type_session)
        for cle, type_session in TYPE_DE_SESSION.items()
    }
    if session_examen:
        cle = _cle_session(type_dexamen)
        sessions[cle] = _get_or_create_session(args, TYPE_DE_SESSION[cle], session_examen)
    return sessions


def _verifier_non_publiee(session):
    """Publication non verrouillante.

    Une session publiée reste modifiable : des requêtes (réclamations) et des
    corrections de notes peuvent survenir après la publication. Ce contrôle ne
    bloque donc plus la saisie, quelle que soit l'état de la session.
    """


def _passer_saisi(note):
    """Fait passer une note au statut « Saisi » dès qu'une saisie est enregistrée.

    Le statut ne recule jamais : une note « Validé » ou « Publié » le reste.
    """
    if note.statut in (None, "", "Brouillon"):
        note.statut = "Saisi"


def _poser_note(note, champ, drapeau, valeur):
    """Noue une valeur de note + son drapeau de saisie (None = champ effacé)."""
    setattr(note, champ, None if valeur in (None, "") else flt(valeur))
    setattr(note, drapeau, 1 if valeur not in (None, "") else 0)


def _verifier_codes_anonymes(rows, args):
    """Vérifie l'association Code d'anonymat -> étudiant pour la matière.

    Le code attendu est celui de la fiche d'anonymat, qui fait foi : c'est lui,
    au format AN0001, qui est imprimé sur les copies. Un code absent, ou ne
    correspondant pas à la fiche d'anonymat de l'étudiant pour cette matière,
    est refusé : aucun code n'est calculé localement, donc aucun autre numéro
    ne peut être accepté.
    """
    students = _get_etudiants(
        args["academic_year"], args["filiere"], args["niveau"], args["teaching_unit"]
    )
    codes = _exiger_codes_anonymes(
        students, args["teaching_unit"], TYPE_NORMALE
    )
    for row in rows:
        valeur = (row.get("code_anonyme") or "").strip()
        if not valeur:
            frappe.throw(
                _("Le code d'anonymat de l'étudiant <b>{0}</b> est manquant pour l'examen.").format(
                    row["student"]
                )
            )
        if codes.get(row["student"]) != valeur:
            frappe.throw(
                _("Le code d'anonymat <b>{0}</b> ne correspond pas à l'étudiant <b>{1}</b> pour cette matière.").format(
                    valeur, row["student"]
                )
            )


def _verifier_cc_modifiable(note):
    """Le CC reste modifiable, même après validation/publication (requêtes)."""


def _copier_cc_dans_note(args, student, note):
    """Reproduit le CC (lecture seule) de la session CC sur la note cible.

    Le CC est saisi dans sa propre session (Contrôle Continu) ; pour que la
    note de matière de la session normale soit complète (CC + Examen + TP),
    ses notes de CC sont synchronisées depuis la session CC. La session CC
    reste la seule source : on ne modifie jamais la note source. La
    synchronisation est systématique (elle remplace les notes de CC déjà
    copiées) afin de refléter les dernières valeurs saisies.
    """
    session_cc = _chercher_session(args, TYPE_CC)
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
    note.set("notes_cc", [])
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
    rows = _valider_lignes(rows)
    _verifier_programmation_requise(args["academic_year"], args["teaching_unit"])
    session = _get_or_create_session(args, TYPE_CC)
    _verifier_non_publiee(session)
    for row in rows:
        note = _get_or_create_note(session, row["student"], args)
        _verifier_cc_modifiable(note)
        note.set("notes_cc", [])
        labels_vus = set()
        for item in row.get("notes_cc") or []:
            valeur = item.get("note_cc")
            if valeur in (None, ""):
                continue
            label = item.get("cc_label") or "CC"
            if label in labels_vus:
                continue
            labels_vus.add(label)
            # Les poids sont définis par la Grade Formula : la moyenne CC et la
            # pondération de la composante sont calculées par le moteur central.
            # Le poids par note CC est donc toujours 1 (moyenne arithmétique),
            # jamais fourni par l'enseignant.
            note.append(
                "notes_cc",
                {
                    "cc_label": label,
                    "cc_weight": 1,
                    "note_cc": flt(valeur),
                },
            )
        notes_saisies = [i for i in (row.get("notes_cc") or []) if i.get("note_cc") not in (None, "")]
        note.cc_saisi = 1 if notes_saisies else 0
        _passer_saisi(note)
        note.save(ignore_permissions=True)
    return len(rows)


def _sauvegarder_examen(args, rows):
    rows = _valider_lignes(rows)
    _verifier_programmation_requise(args["academic_year"], args["teaching_unit"])
    session = _get_or_create_session(args, TYPE_NORMALE)
    _verifier_non_publiee(session)
    for row in rows:
        note = _get_or_create_note(session, row["student"], args)
        _copier_cc_dans_note(args, row["student"], note)
        note.note_examen = row.get("note_examen")
        note.examen_saisi = 1 if row.get("note_examen") not in (None, "") else 0
        if "note_tp" in row:
            note.note_tp = row.get("note_tp")
            note.tp_saisi = 1 if row.get("note_tp") not in (None, "") else 0
        _passer_saisi(note)
        note.save(ignore_permissions=True)
    return len(rows)


def _sauvegarder_tp(args, rows):
    rows = _valider_lignes(rows)
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
    rows = _valider_lignes(rows)
    _verifier_programmation_requise(args["academic_year"], args["teaching_unit"])
    session = _get_or_create_session(args, TYPE_RATTRAPAGE, args.get("session_examen"))
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
            # TP, Rapport et Compétence ne sont pas à ressaisir au rattrapage.
            # Seul un drapeau *saisi (ou une valeur non nulle) compte : le
            # stockage Currency ramène les champs non saisis à 0.0.
            note.note_tp = normale_doc.note_tp
            if normale_doc.tp_saisi:
                note.tp_saisi = 1
            if normale_doc.note_rapport:
                note.note_rapport = normale_doc.note_rapport
            if normale_doc.note_competence:
                note.note_competence = normale_doc.note_competence

        # Le CC provient toujours de la session CC (source unique) ; à défaut
        # d'une session CC dédiée, on reprend le CC de la note de la session
        # normale afin que la moyenne CC soit conservée au rattrapage.
        _copier_cc_dans_note(args, row["student"], note)
        if not note.get("notes_cc") and initiale:
            for cc in normale_doc.notes_cc:
                if cc.note_cc is not None:
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
def lister_sessions(academic_year, filiere, niveau, semestre, teaching_unit=None):
    """Sessions d'examen disponibles pour le contexte de saisie.

    Alimente le sélecteur de session : sans lui, la page ne pouvait afficher
    qu'une session par type d'évaluation, et la création d'une nouvelle
    session rendait la précédente inaccessible alors que ses notes restaient
    en base.
    """
    if teaching_unit:
        _verifier_acces_enseignant(teaching_unit)
    args = {
        "academic_year": academic_year,
        "filiere": filiere,
        "niveau": niveau,
        "semestre": _semestre_effectif(
            {"academic_year": academic_year, "semestre": semestre, "teaching_unit": teaching_unit}
        )
        if teaching_unit
        else semestre,
    }
    resultat = {}
    for cle, type_dexamen in (
        ("cc", TYPE_CC),
        ("normale", TYPE_NORMALE),
        ("rattrapage", TYPE_RATTRAPAGE),
    ):
        items = []
        for s in _sessions_couvrant(args, type_dexamen):
            ues = frappe.get_all(
                "Session Examen Note",
                filters={"session_examen": s["name"]},
                fields=["teaching_unit"],
                distinct=True,
                pluck="teaching_unit",
            )
            items.append(
                {
                    "name": s["name"],
                    "statut": s["statut"],
                    "date_debut": s["date_debut"],
                    "date_de_fin": s["date_de_fin"],
                    "date_publication": s["date_publication"],
                    "nb_notes": frappe.db.count("Session Examen Note", {"session_examen": s["name"]}),
                    "nb_ues": len(ues),
                    "ues": sorted(ues),
                }
            )
        resultat[cle] = items
    return resultat


@frappe.whitelist()
def charger_data(academic_year, filiere, niveau, semestre, teaching_unit, type_dexamen=None, session_examen=None):
    """Charge la configuration, l'UE, les étudiants et toutes les notes pour la page de saisie.

    Les sessions existantes sont recherchées (sans création) afin d'éviter
    toute pollution de données lors d'un simple chargement de la page.
    La création de session n'a lieu qu'au moment de l'enregistrement effectif
    des notes (enregistrer_cc, enregistrer_examen, etc.).
    """
    _verifier_acces_enseignant(teaching_unit)
    config = _get_config()

    if config["exiger_programmation"] and not _verifier_programmation(academic_year, teaching_unit):
        frappe.throw(
            _(
                "L'UE {0} n'a aucune évaluation (CC, examen ou rattrapage) programmée pour {1} "
                "dans le planning académique."
            ).format(teaching_unit, academic_year)
        )

    ue_info = _get_ue_info(teaching_unit, filiere, niveau)
    students = _get_etudiants(academic_year, filiere, niveau, teaching_unit)

    semestre_effectif = _semestre_effectif({
        "academic_year": academic_year,
        "semestre": semestre,
        "teaching_unit": teaching_unit,
    })
    args = {
        "academic_year": academic_year,
        "semestre": semestre_effectif,
        "filiere": filiere,
        "niveau": niveau,
        "teaching_unit": teaching_unit,
    }

    # Lecture seule : on cherche les sessions existantes sans les créer.
    sessions_raw = {
        "cc": _chercher_session(args, TYPE_CC),
        "normale": _chercher_session(args, TYPE_NORMALE),
        "rattrapage": _chercher_session(args, TYPE_RATTRAPAGE),
    }

    # Session imposée par le sélecteur de session : elle ne concerne que le
    # type d'évaluation affiché, les autres restent résolus automatiquement.
    if session_examen:
        cle = _cle_session(type_dexamen)
        sessions_raw[cle] = _valider_session_cible(args, session_examen, TYPE_DE_SESSION[cle])

    sessions_meta = {}
    types_par_cle = {
        "cc": TYPE_CC,
        "normale": TYPE_NORMALE,
        "rattrapage": TYPE_RATTRAPAGE,
    }
    for cle, session in sessions_raw.items():
        meta = (
            frappe.db.get_value(
                "Session Examen",
                session,
                ["statut", "date_publication"],
                as_dict=True,
            )
            or {}
        ) if session else {}
        sessions_meta[cle] = {
            "name": session,
            "statut": meta.get("statut"),
            "date_publication": meta.get("date_publication"),
            "planifie": _verifier_programmation(
                academic_year, teaching_unit, types_par_cle[cle]
            ),
        }

    # _charger_notes accepte des valeurs None dans le dict sessions.
    notes = _charger_notes(students, teaching_unit, sessions_raw)

    return {
        "config": config,
        "ue_info": ue_info,
        "formule": _formule_detectee(teaching_unit, filiere, niveau, notes, students),
        "students": students,
        "sessions": sessions_meta,
        "sessions_liste": lister_sessions(
            academic_year, filiere, niveau, semestre_effectif, teaching_unit
        ),
        "notes": notes,
        "lignes": _lignes_unifiees(students, notes, teaching_unit),
    }


def _lignes_unifiees(students, notes, teaching_unit=None):
    """Lignes de la saisie unifiée : une ligne par étudiant inscrit.

    La source unique est la note de la session normale (CC, CCTP, EXAMTP,
    EXAM) ; à défaut de CC saisi directement sur la session normale, on
    retombe sur la note de la session CC (données historiques). Les valeurs
    ne sont présentées que si le drapeau *saisi est posé : le stockage
    Currency ramène les champs non saisis à 0.0.

    Chaque ligne expose les codes anonymes **propres à la matière** :
    ``code_anonyme`` pour l'examen normal et ``code_anonyme_rattrapage``
    pour la session de rattrapage (deux jeux distincts).
    """
    codes = _codes_anonymes(students, teaching_unit, TYPE_NORMALE)
    codes_rt = _codes_anonymes(students, teaching_unit, TYPE_RATTRAPAGE)
    notes_cc = (notes or {}).get("CC", {})
    lignes = []
    for s in students or []:
        nom = s["student"]
        ex = dict((notes or {}).get("Examen", {}).get(nom, {}))
        cc = notes_cc.get(nom, {})
        if not ex.get("cc_saisi") and cc.get("note_cc_moyenne"):
            ex["note_cc_moyenne"] = cc.get("note_cc_moyenne")
            ex["cc_saisi"] = 1
        lignes.append(
            {
                "matricule": s.get("matricule") or "",
                "nom": s.get("nom") or "",
                "prenom": s.get("prenom") or "",
                "code_anonyme": codes.get(nom, ""),
                "code_anonyme_rattrapage": codes_rt.get(nom, ""),
                "student": nom,
                "cc": ex.get("note_cc_moyenne") if ex.get("cc_saisi") else None,
                "cctp": ex.get("note_cctp") if ex.get("cctp_saisi") else None,
                "examtp": ex.get("note_examtp") if ex.get("examtp_saisi") else None,
                "examen": ex.get("note_examen") if ex.get("examen_saisi") else None,
                "note_finale": ex.get("note_finale"),
                "note_pct": ex.get("note_pct"),
                "grade": ex.get("grade"),
                "point": ex.get("point"),
                "mention": ex.get("mention"),
                "statut": ex.get("statut"),
            }
        )
    return lignes


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
def calculer_apercu(student, teaching_unit, notes_cc=None, note_examen=None, note_tp=None, note_examen_rattrapage=None, note_cctp=None, note_examtp=None):
    """Calcule à la volée (sans enregistrer) moyenne CC, note retenue, note finale, % et grade.

    La combinaison des évaluations renseignées est détectée automatiquement et
    la formule est résolue dans la Grade Formula (poids de la configuration).
    Utilise le même moteur central que l'enregistrement (Session Examen Note)
    afin que l'aperçu affiché au professeur soit strictement identique au
    résultat qui sera réellement enregistré.
    """
    _verifier_acces_enseignant(teaching_unit)
    from udshed.udshed.doctype.session_examen_note.session_examen_note import SessionExamenNote  # noqa: F401

    type_ue = frappe.db.get_value("Teaching Unit", teaching_unit, "type_ue") or "Sans TP"

    doc = frappe.new_doc("Session Examen Note")
    doc.student = student
    doc.teaching_unit = teaching_unit
    doc.type_ue = type_ue

    if isinstance(notes_cc, str):
        try:
            notes_cc = frappe.parse_json(notes_cc) or []
        except Exception:
            notes_cc = []
    for item in notes_cc or []:
        valeur = item.get("note_cc")
        if valeur in (None, ""):
            continue
        doc.append(
            "notes_cc",
            {
                "cc_label": item.get("cc_label") or "CC",
                "cc_weight": flt(item.get("cc_weight") or 1),
                "note_cc": flt(valeur),
            },
        )

    if note_examen not in (None, ""):
        doc.note_examen = flt(note_examen)
    if note_tp not in (None, ""):
        doc.note_tp = flt(note_tp)
    if note_cctp not in (None, ""):
        doc.note_cctp = flt(note_cctp)
    if note_examtp not in (None, ""):
        doc.note_examtp = flt(note_examtp)
    if note_examen_rattrapage not in (None, ""):
        doc.note_examen_rattrapage = flt(note_examen_rattrapage)

    doc.deriver_drapeaux_saisie()
    doc.calculer_note_cc_moyenne()
    doc.calculer_note_examen_active()
    doc.calculer_note_finale()
    doc.determiner_grade()

    from udshed.grade_calculation import get_student_cycle

    formula = doc._formule_note()
    cycle = get_student_cycle(student)
    formule = (
        _serialiser_formule(formula, cycle, doc.combinaison_detectee())
        if formula
        else None
    )

    return {
        "note_cc_moyenne": doc.note_cc_moyenne,
        "note_examen_active": doc.note_examen_active,
        "note_finale": doc.note_finale,
        "note_pct": doc.note_pct,
        "grade": doc.grade,
        "point": doc.point,
        "mention": doc.mention,
        "type_resultat": doc.type_resultat,
        "combinaison": doc.combinaison_detectee(),
        "formule_manquante": bool(doc.formule_manquante()),
        "formule": formule,
    }


@frappe.whitelist()
def enregistrer_cc(academic_year, filiere, niveau, semestre, teaching_unit, rows):
    """Enregistre les notes de contrôle continu pour tous les étudiants."""
    _verifier_acces_enseignant(teaching_unit)
    args = {"academic_year": academic_year, "filiere": filiere, "niveau": niveau, "semestre": _semestre_effectif({"academic_year": academic_year, "semestre": semestre, "teaching_unit": teaching_unit}), "teaching_unit": teaching_unit}
    n = _sauvegarder_cc(args, rows)
    return {"saved": n}


@frappe.whitelist()
def enregistrer_evaluations(academic_year, filiere, niveau, semestre, teaching_unit, rows, type_dexamen=None, session_examen=None):
    """Enregistre la saisie des évaluations d'une UE selon le type d'évaluation.

    Chaque ligne : {"student", ...}. Seuls les champs présents dans la ligne
    sont mis à jour (une saisie de CC ne touche jamais aux notes d'examen et
    réciproquement), et la note existante de la session normale est mise à
    jour — jamais dupliquée :
    - type_dexamen = "CC"      -> {"student", "cc", "note_cctp"} (Contrôle continu).
    - type_dexamen = "Examen"  -> {"student", "code_anonyme", "note_examen", "note_examtp"}.
    - type_dexamen = "Rattrapage" -> redirige vers enregistrer_rattrapage.
    - sans type_dexamen (appels historiques/tests) -> comportement unifié
      CC + CCTP + EXAMTP + EXAM conservé tel quel.
    """
    _verifier_acces_enseignant(teaching_unit)
    args = {"academic_year": academic_year, "filiere": filiere, "niveau": niveau, "semestre": _semestre_effectif({"academic_year": academic_year, "semestre": semestre, "teaching_unit": teaching_unit}), "teaching_unit": teaching_unit}
    mode = _mode_saisie(type_dexamen)
    if mode == "rattrapage":
        return enregistrer_rattrapage(
            academic_year, filiere, niveau, semestre, teaching_unit, rows, session_examen=session_examen
        )
    rows = _valider_lignes(rows)
    _verifier_programmation_requise(args["academic_year"], args["teaching_unit"])
    session = _get_or_create_session(args, TYPE_NORMALE, args.get("session_examen"))
    _verifier_non_publiee(session)
    if type_dexamen and mode == "examen":
        _verifier_codes_anonymes(rows, args)
    n = 0
    for row in rows:
        note = _get_or_create_note(session, row["student"], args)
        _copier_cc_dans_note(args, row["student"], note)
        if "cc" in row:
            cc = row.get("cc")
            if cc not in (None, ""):
                note.set("notes_cc", [])
                note.append("notes_cc", {"cc_label": "CC", "cc_weight": 1, "note_cc": flt(cc)})
            elif mode == "cc":
                note.set("notes_cc", [])
        if "note_cctp" in row:
            _poser_note(note, "note_cctp", "cctp_saisi", row.get("note_cctp"))
        if "note_examtp" in row:
            _poser_note(note, "note_examtp", "examtp_saisi", row.get("note_examtp"))
        if "note_examen" in row:
            _poser_note(note, "note_examen", "examen_saisi", row.get("note_examen"))
        _passer_saisi(note)
        note.save(ignore_permissions=True)
        n += 1
    return {"saved": n, "type_dexamen": mode}


@frappe.whitelist()
def enregistrer_examen(academic_year, filiere, niveau, semestre, teaching_unit, rows):
    """Enregistre les notes de l'examen de session normale."""
    _verifier_acces_enseignant(teaching_unit)
    args = {"academic_year": academic_year, "filiere": filiere, "niveau": niveau, "semestre": _semestre_effectif({"academic_year": academic_year, "semestre": semestre, "teaching_unit": teaching_unit}), "teaching_unit": teaching_unit}
    n = _sauvegarder_examen(args, rows)
    return {"saved": n}


@frappe.whitelist()
def enregistrer_tp(academic_year, filiere, niveau, semestre, teaching_unit, rows):
    """Enregistre les notes de travaux pratiques."""
    _verifier_acces_enseignant(teaching_unit)
    args = {"academic_year": academic_year, "filiere": filiere, "niveau": niveau, "semestre": _semestre_effectif({"academic_year": academic_year, "semestre": semestre, "teaching_unit": teaching_unit}), "teaching_unit": teaching_unit}
    n = _sauvegarder_tp(args, rows)
    return {"saved": n}


@frappe.whitelist()
def enregistrer_rattrapage(academic_year, filiere, niveau, semestre, teaching_unit, rows, session_examen=None):
    """Enregistre les notes de rattrapage."""
    _verifier_acces_enseignant(teaching_unit)
    args = {"academic_year": academic_year, "filiere": filiere, "niveau": niveau, "semestre": _semestre_effectif({"academic_year": academic_year, "semestre": semestre, "teaching_unit": teaching_unit}), "teaching_unit": teaching_unit, "session_examen": session_examen}
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
    _verifier_programmation_sessions(session)
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

    Toutes les notes de la session passent au statut « Publié » et
    deviennent consultables au babillard public. La publication n'est pas
    définitive : les notes restent modifiables (corrections / réclamations)
    après publication.

    La publication est **idempotente** : republier une session déjà
    marquée « Publiée » publie les notes restées en attente (saisies ou
    validées après une correction) sans planter ni re-valider l'ensemble.
    C'est volontaire pour réparer les sessions dont le champ statut avait
    été positionné sur « Publiée » à la main, sans publier leurs notes.

    Args:
        session: Nom du document Session Examen

    Returns:
        dict: {"name", "statut", "date_publication", "publied"}
    """
    doc = frappe.get_doc("Session Examen", session)
    deja_publiee = doc.statut == "Publiée"

    if not deja_publiee:
        _verifier_programmation_sessions(session)

    # Garde métier : une session jamais publiée ne se publie qu'avec des
    # notes validées. Sauf si le document est déjà étiqueté « Publiée » :
    # c'est alors une re-publication (notes corrigées/ajoutées ensuite).
    if not deja_publiee:
        non_validees = frappe.db.count(
            "Session Examen Note",
            {"session_examen": session, "statut": ["not in", ["Validé", "Publié"]]},
        )
        if non_validees:
            frappe.throw(
                _("Impossible de publier : {0} note(s) de la session {1} ne sont pas validées. "
                  "Validez d'abord les notes avant de publier.").format(non_validees, session)
            )

    notes = frappe.get_all(
        "Session Examen Note",
        filters={"session_examen": session, "statut": ["!=", "Publié"]},
        pluck="name",
    )
    for name in notes:
        frappe.db.set_value("Session Examen Note", name, "statut", "Publié")

    doc.db_set("statut", "Publiée")
    if not doc.date_publication:
        doc.db_set("date_publication", today())

    echecs = _declencher_calcul_resultats_post_publication(doc)
    _declencher_notification_publication(doc)

    if echecs:
        # La publication reste valide (les notes sont visibles au babillard),
        # mais le coordinateur doit voir que les résultats aval n'ont pas été
        # produits : sans ce retour, l'échec ne se lisait que dans l'Error Log.
        frappe.msgprint(
            _("Session publiée, mais le calcul des résultats a échoué pour {0} cas. "
              "Relancez « Calculer les résultats » une fois la cause corrigée.").format(
                len(echecs)
            ),
            title=_("Résultats incomplets"),
            indicator="orange",
        )

    return {
        "name": doc.name,
        "statut": doc.statut,
        "date_publication": doc.date_publication,
        "publied": len(notes),
        "echecs_resultats": echecs,
    }


def _declencher_notification_publication(session_doc):
    """Planifie l'envoi des e-mails de publication (après le commit).

    L'envoi est confié à un worker RQ déclenché uniquement après la
    validation du commit : les notes sont alors effectivement publiées,
    ce qui garantit qu'aucun e-mail ne part avant la publication.
    """
    try:
        frappe.enqueue(
            "udshed.api.note_notification.notifier_publication_matiere",
            session=session_doc.name,
            queue="short",
            enqueue_after_commit=True,
        )
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "udshed: planification notification publication {}".format(session_doc.name),
        )


def _declencher_calcul_resultats_post_publication(session_doc):
    """Déclenche le calcul des Resultat Académique / Resultat Semestre
    pour les étudiants dont les notes viennent d'être publiées.

    Chaque student × session_normale du semestre est traité séparément.
    Un échec est journalisé **et renvoyé** : l'appelant peut ainsi prévenir
    l'utilisateur au lieu de laisser une session « Publiée » dont les
    résultats n'existent pas.

    Returns:
        list[dict]: une entrée par échec {student, session, message}
    """
    from udshed.api.resultat_academique import calculer_resultat_session

    students = frappe.db.sql_list(
        """
        SELECT DISTINCT student
        FROM `tabSession Examen Note`
        WHERE session_examen = %s AND statut = 'Publié'
        """,
        session_doc.name,
    )
    if not students:
        return []

    sessions_normales = frappe.get_all(
        "Session Examen",
        filters={
            "academic_year": session_doc.academic_year,
            "semestre": session_doc.semestre,
            "type_dexamen": TYPE_NORMALE,
        },
        pluck="name",
    )

    echecs = []
    for student in students:
        for sess in sessions_normales:
            if not frappe.db.exists(
                "Session Examen Note",
                {"session_examen": sess, "student": student, "statut": "Publié"},
            ):
                continue
            try:
                calculer_resultat_session(student, sess)
            except Exception as exc:
                frappe.log_error(
                    frappe.get_traceback(),
                    "udshed: calcul résultat post-publication",
                )
                echecs.append({
                    "student": student,
                    "session": sess,
                    "message": str(exc),
                })
        # Persiste le Resultat Semestre (MPS / MPC) : c'est lui qui alimente
        # le relevé de notes et les résultats académiques du semestre.
        try:
            from udshed.api.resultat_academique import calculer_et_sauvegarder_mps_mpc

            calculer_et_sauvegarder_mps_mpc(
                student, session_doc.semestre, session_doc.academic_year
            )
        except Exception as exc:
            frappe.log_error(
                frappe.get_traceback(),
                "udshed: sauvegarde Resultat Semestre post-publication",
            )
            echecs.append({
                "student": student,
                "session": session_doc.name,
                "message": _("Resultat Semestre non enregistré — {0}").format(exc),
            })

    return echecs


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


def _ue_a_tp(teaching_unit):
    """Vrai si le cours (Teaching Unit) a des Travaux Pratiques (type UE « Avec TP »)."""
    if not teaching_unit:
        return False
    return (frappe.db.get_value("Teaching Unit", teaching_unit, "type_ue") or "") == "Avec TP"


def _entetes_avec_tp(entetes, type_dexamen, teaching_unit):
    """Insère la colonne « Note de TP » dans un modèle d'examen si le cours a un TP."""
    if type_dexamen != "Examen" or not _ue_a_tp(teaching_unit):
        return entetes
    entetes = list(entetes)
    if _("Note de TP") not in entetes:
        pos = entetes.index(_("Note d'examen")) if _("Note d'examen") in entetes else len(entetes)
        entetes.insert(pos, _("Note de TP"))
    return entetes


def _repondre_xlsx(rows, filename):
    from frappe.utils.xlsxutils import make_xlsx

    xlsx = make_xlsx(rows, "Notes")
    frappe.response["filename"] = filename
    frappe.response["filecontent"] = xlsx.getvalue()
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@frappe.whitelist()
def export_modele(type_dexamen, cc_columns=None):
    """Télécharge un modèle Excel vierge pour la saisie des notes."""
    cc_columns = _colonnes_cc(cc_columns)
    _repondre_xlsx([_en_tetes(type_dexamen, cc_columns)], "modele_{0}.xlsx".format(type_dexamen.lower()))


def _html_en_pdf(html):
    """Convertit du HTML en PDF (octets).

    Utilise d'abord le générateur standard de Frappe (wkhtmltopdf). S'il
    n'est pas installé, repli sur Playwright/Chromium (déjà présent dans
    l'environnement de développement) pour restituer la même page A4.
    """
    try:
        from frappe.utils.pdf import get_pdf

        return get_pdf(html)
    except Exception:
        pass

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle")
            pdf = page.pdf(format="A4", landscape=True, print_background=True, margin={"top": "18mm", "bottom": "14mm", "left": "14mm", "right": "14mm"})
            return pdf
        finally:
            browser.close()



def _fmt(v):
    if v is None or v == "":
        return ""
    return str(flt(v))


def _fmt_pct(v):
    if v is None or v == "":
        return ""
    return "{0} %".format(flt(v))


def _code_classe(fos_code, niveau_label):
    """Code de classe compact pour le bandeau du PV (ex : IRT + Licence 3 -> IRT3)."""
    match = re.search(r"(\d+)", niveau_label or "")
    if match and fos_code:
        return "{0}{1}".format(fos_code, match.group(1))
    return niveau_label or ""


def _code_semestre(semestre_label):
    """Code semestre compact pour le bandeau du PV (ex : Semestre 6 -> SEM6)."""
    match = re.search(r"(\d+)", semestre_label or "")
    if match:
        return "SEM{0}".format(match.group(1))
    return semestre_label or ""


def _html_pv_matiere_pdf(
    ecole,
    institut,
    departement,
    logo_html,
    logo_wm,
    classe,
    annee,
    semestre_label,
    matiere,
    code_matiere,
    inscrits,
    admis,
    echecs,
    taux,
    evaluations,
    lignes,
):
    """Construit le HTML du procès-verbal de la matière (modèle UDM, A4 paysage).

    Toutes les valeurs affichées proviennent du moteur central
    (Session Examen Note) : composantes CC/CCTP/EXAMTP/EXAM, moyenne %,
    grade et points. Aucune donnée n'est recalculée ici.
    """

    def esc(v):
        return frappe.utils.escape_html(str(v) if v is not None else "")

    def note(v):
        return esc(_fmt(v))

    eval_rows = ""
    for ev in evaluations or []:
        eval_rows += (
            "<tr>"
            "<td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td>"
            "</tr>"
        ).format(esc(ev.get("type")), esc(ev.get("code")), esc(ev.get("matiere")), esc(ev.get("date")))

    notes_rows = ""
    for i, ligne in enumerate(lignes or [], start=1):
        nom_complet = "{0} {1}".format(ligne.get("nom") or "", ligne.get("prenom") or "").strip()
        pct = ligne.get("note_pct")
        notes_rows += (
            "<tr>"
            "<td>{0}</td>"
            "<td>{1}</td>"
            "<td class='nom-cell'>{2}</td>"
            "<td>{3}</td>"
            "<td>{4}</td>"
            "<td>{5}</td>"
            "<td>{6}</td>"
            "<td>{7}</td>"
            "<td>{8}</td>"
            "<td>{9}</td>"
            "</tr>"
        ).format(
            i,
            esc(ligne.get("matricule")),
            esc(nom_complet),
            note(ligne.get("cc")),
            note(ligne.get("cctp")),
            note(ligne.get("examtp")),
            note(ligne.get("examen")),
            esc("{0:.2f}%".format(flt(pct))) if pct is not None else "",
            esc(ligne.get("grade")),
            note(ligne.get("point")),
        )

    if not notes_rows:
        notes_rows = "<tr><td colspan='10' style='padding:12px;color:#666;'>Aucun étudiant inscrit</td></tr>"

    titre_matiere = esc(matiere or "")
    if code_matiere:
        titre_matiere += "({0})".format(esc(code_matiere))

    # Filigrane : logo UDSHED en image (data-URI embarquée) si dispo,
    # sinon repli sur le nom de l'établissement en texte.
    wm_html = ""
    if logo_wm:
        wm_html = '<img src="{0}" alt="">'.format(esc(logo_wm))
    else:
        wm_html = esc(ecole)

    return """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    * {{ box-sizing: border-box; }}

    body {{
        margin: 0;
        padding: 0;
        background: #ffffff;
        font-family: "Times New Roman", Times, serif;
        color: #000;
    }}

    @page {{ size: A4 landscape; margin: 10mm 12mm; }}

    .page {{ position: relative; }}

    /* ================= HEADER ================= */
    .header {{
        border-bottom: 2px solid #999;
        position: relative;
        margin-bottom: 30px;
        padding-bottom: 8px;
        min-height: 85px;
    }}

    .universite {{
        position: absolute;
        left: 0;
        top: 0;
        color: #071c9d;
        line-height: 1.1;
    }}

    .universite .nom {{
        font-family: Arial, Helvetica, sans-serif;
        font-size: 21px;
        font-weight: bold;
    }}

    .universite .institut {{
        font-family: Arial, Helvetica, sans-serif;
        font-size: 14px;
        margin-top: 4px;
    }}

    .universite .departement {{
        font-family: Arial, Helvetica, sans-serif;
        font-size: 13px;
        margin-top: 3px;
    }}

    .logo {{
        position: absolute;
        right: 0;
        top: -5px;
        width: 110px;
        height: 95px;
        display: flex;
        align-items: center;
        justify-content: center;
    }}
    .logo img {{ max-width: 105px; max-height: 90px; }}

    /* ================= INFORMATIONS ================= */
    .info-header {{
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        margin-bottom: 0;
    }}

    .info-header td {{
        border: 2px solid #222;
        background: #dce2e8;
        text-align: center;
        vertical-align: middle;
        height: 52px;
        font-size: 19px;
        font-weight: bold;
    }}

    .info-header .annee {{ line-height: 1; }}
    .info-header .annee span {{ display: block; font-size: 19px; margin-top: 3px; }}

    /* ================= TITRE ================= */
    .titre {{
        border-left: 2px solid #222;
        border-right: 2px solid #222;
        border-bottom: 2px solid #222;
        text-align: center;
        height: 32px;
        font-size: 14px;
        font-weight: bold;
        padding-top: 6px;
    }}
    .titre span {{ font-weight: normal; }}

    /* ================= STATISTIQUES ================= */
    .stats-zone {{ display: flex; width: 100%; margin-top: 0; }}

    .credits {{ width: 58%; padding-top: 12px; }}
    .evaluations {{ width: 42%; padding-top: 0; }}

    .credits-title {{
        width: 145px;
        height: 20px;
        border: 1px solid #333;
        background: #eef1f3;
        text-align: center;
        color: #d00000;
        font-size: 12px;
        font-weight: bold;
        padding-top: 2px;
    }}

    .credits-table {{ border-collapse: collapse; width: 100%; table-layout: fixed; }}
    .credits-table th,
    .credits-table td {{
        border: 1px solid #555;
        text-align: center;
        height: 20px;
        font-size: 11px;
    }}
    .credits-table th {{ background: #eef1f3; color: #174a8b; font-weight: bold; }}
    .credits-table td {{ color: #174a8b; font-weight: bold; }}

    .evaluations-table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    .evaluations-table th,
    .evaluations-table td {{
        border: 1px solid #444;
        text-align: center;
        height: 19px;
        font-size: 10px;
    }}
    .evaluations-table .title {{
        color: #174a8b;
        background: #eef1f3;
        font-weight: bold;
        height: 18px;
    }}
    .evaluations-table th {{ background: #eef1f3; color: #174a8b; font-weight: bold; }}
    .evaluations-table td {{ color: #174a8b; }}

    /* ================= TABLEAU PRINCIPAL ================= */
    .notes-table {{
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        margin-top: 2px;
    }}

    .notes-table th,
    .notes-table td {{
        border: 1px solid #222;
        text-align: center;
        vertical-align: middle;
    }}

    .notes-table th {{
        height: 26px;
        color: #15519b;
        font-size: 12px;
        font-weight: bold;
        background: #fff;
    }}

    .notes-table td {{ height: 26px; font-size: 12px; }}

    .notes-table .numero {{ width: 42px; }}
    .notes-table .matricule {{ width: 85px; }}
    .notes-table .nom {{ width: 340px; }}
    .notes-table .note {{ width: 52px; }}
    .notes-table .moy {{ width: 58px; }}
    .notes-table .grd {{ width: 48px; }}
    .notes-table .pts {{ width: 50px; }}

    .nom-cell {{ text-align: left !important; padding-left: 8px; white-space: nowrap; }}

    /* ================= SIGNATURES ================= */
    .signatures {{
        width: 100%;
        display: flex;
        justify-content: space-between;
        margin-top: 26px;
    }}

    .signature {{
        width: 23%;
        height: 30px;
        border: 2px solid #222;
        text-align: center;
        font-size: 13px;
        font-weight: bold;
        padding-top: 6px;
    }}

    /* ================= FILIGRANE ================= */
    .watermark {{
        position: fixed;
        left: 50%;
        top: 55%;
        transform: translate(-50%, -50%) rotate(-28deg);
        font-family: Arial, Helvetica, sans-serif;
        font-size: 52px;
        font-weight: bold;
        color: rgba(130, 130, 130, 0.13);
        white-space: nowrap;
        pointer-events: none;
        z-index: 10;
    }}
    .watermark img {{
        width: 150mm;
        opacity: 0.08;
    }}
</style>
</head>
<body>

<div class="page">

    <div class="watermark">{14}</div>

    <div class="header">
        <div class="universite">
            <div class="nom">{0}</div>
            <div class="institut">{1}</div>
            <div class="departement">{2}</div>
        </div>
        <div class="logo">{3}</div>
    </div>

    <table class="info-header">
        <tr>
            <td>{4}</td>
            <td class="annee">
                Année Académique
                <span>{5}</span>
            </td>
            <td>{6}</td>
        </tr>
    </table>

    <div class="titre">
        <b>PROCES VERBAL DE LA MATIERE:</b>
        <span>{7}</span>
    </div>

    <div class="stats-zone">
        <div class="credits">
            <div class="credits-title">Credits:</div>
            <table class="credits-table">
                <tr>
                    <th>Inscrits</th>
                    <th>Admis</th>
                    <th>Echecs</th>
                    <th>Taux de réussite</th>
                </tr>
                <tr>
                    <td>{8}</td>
                    <td>{9}</td>
                    <td>{10}</td>
                    <td>{11}</td>
                </tr>
            </table>
        </div>

        <div class="evaluations">
            <table class="evaluations-table">
                <tr>
                    <td colspan="4" class="title">Evaluations effectuées:</td>
                </tr>
                <tr>
                    <th>Type</th>
                    <th>Code</th>
                    <th>Matière</th>
                    <th>Date</th>
                </tr>
                {12}
            </table>
        </div>
    </div>

    <table class="notes-table">
        <thead>
            <tr>
                <th class="numero">N°</th>
                <th class="matricule">Matricule</th>
                <th class="nom">Nom et Prénoms</th>
                <th class="note">CC</th>
                <th class="note">CCTP</th>
                <th class="note">EXAMTP</th>
                <th class="note">EXAM</th>
                <th class="moy">MOY</th>
                <th class="grd">GRD</th>
                <th class="pts">PTS</th>
            </tr>
        </thead>
        <tbody>
            {13}
        </tbody>
    </table>

    <div class="signatures">
        <div class="signature">VICE DOYEN</div>
        <div class="signature">COORDONATEUR</div>
        <div class="signature">RESP ACADEMIQUE</div>
        <div class="signature">CHEF UNITE</div>
    </div>

</div>

</body>
</html>
    """.format(
        esc(ecole),
        esc(institut),
        esc(departement),
        logo_html,
        esc(classe),
        esc(annee),
        esc(semestre_label),
        titre_matiere,
        inscrits,
        admis,
        echecs,
        taux,
        eval_rows,
        notes_rows,
        wm_html,
    )


@frappe.whitelist()
def generer_pdf(academic_year, filiere, niveau, semestre, teaching_unit, session_examen=None, type_dexamen=None):
    """Génère le procès-verbal de la matière au format PDF à partir des données enregistrées.

    Le PV présente, pour chaque étudiant inscrit : les composantes saisies
    (CC, CCTP, EXAMTP, EXAM), la moyenne (%), le grade et les points, ainsi
    que les statistiques de l'UE (inscrits, admis, échecs, taux de réussite)
    et les évaluations de la session. Toutes les valeurs proviennent du
    moteur central (Session Examen Note) — aucune donnée fictive, aucun
    recalcul local. Si un rattrapage est saisi, la note retenue (= MAX
    examen/rattrapage) et le résultat correspondant sont utilisés.
    """
    _verifier_acces_enseignant(teaching_unit)
    args = {
        "academic_year": academic_year,
        "semestre": _semestre_effectif({"academic_year": academic_year, "semestre": semestre, "teaching_unit": teaching_unit}),
        "filiere": filiere,
        "niveau": niveau,
        "teaching_unit": teaching_unit,
    }
    semestre_effectif = args["semestre"]

    ue_info = _get_ue_info(teaching_unit, filiere, niveau)
    students = _get_etudiants(academic_year, filiere, niveau, teaching_unit)

    sessions = _sessions_avec_choix(args, session_examen, type_dexamen)
    notes = _charger_notes(students, teaching_unit, sessions)

    # Lignes unifiées (CC, CCTP, EXAMTP, EXAM + résultat) — même source que la page.
    lignes = _lignes_unifiees(students, notes)

    # Le rattrapage saisi prime : note retenue et résultat de la session de rattrapage.
    notes_rt = notes.get("Rattrapage", {})
    for ligne in lignes:
        rt = notes_rt.get(ligne.get("student")) or {}
        if rt.get("note_pct") is not None:
            ligne["examen"] = rt.get("note_examen_active")
            ligne["note_finale"] = rt.get("note_finale")
            ligne["note_pct"] = rt.get("note_pct")
            ligne["grade"] = rt.get("grade")
            ligne["point"] = rt.get("point")

    # Statistiques de l'UE : admis/échecs selon le seuil de validation du cycle.
    cycle = _cycle_pour_niveau(niveau)
    seuil = get_seuil_validation(cycle)
    evalues = [l for l in lignes if l.get("note_pct") is not None]
    admis = sum(1 for l in evalues if flt(l["note_pct"]) >= seuil)
    echecs = len(evalues) - admis
    taux = "{0:.2f}%".format(admis * 100.0 / len(evalues)) if evalues else ""

    # Évaluations de la session (type + matière + date de début).
    code_matiere = ue_info.get("code") or ""
    evaluations = []
    for type_label, cle in (("CC", "cc"), ("EXAM", "normale"), ("RAT", "rattrapage")):
        date_debut = frappe.db.get_value("Session Examen", sessions[cle], "date_debut")
        evaluations.append(
            {
                "type": type_label,
                "code": "",
                "matiere": code_matiere,
                "date": frappe.utils.formatdate(date_debut, "dd-MM-yyyy") if date_debut else "",
            }
        )

    setting = frappe.get_single("Udshed Setting")
    ecole = setting.school_name or ""

    logo_html = ""
    if setting.school_logo:
        logo_url = setting.school_logo
        if logo_url.startswith("/"):
            logo_url = frappe.utils.get_url(logo_url)
        logo_html = '<img src="{0}" alt="logo">'.format(frappe.utils.escape_html(logo_url))

    logo_wm = ""
    try:
        from udshed.api.school_setting import get_logo_data_uri

        logo_wm = get_logo_data_uri() or ""
    except Exception:
        logo_wm = ""

    fos_doc = frappe.get_doc("Field of study", filiere)
    faculte = ""
    if fos_doc.faculte:
        faculte = frappe.db.get_value("Faculty", fos_doc.faculte, "faculty_name") or ""

    html = _html_pv_matiere_pdf(
        ecole=ecole,
        institut=faculte,
        departement=fos_doc.name_of_field or "",
        logo_html=logo_html,
        logo_wm=logo_wm,
        classe=_code_classe(fos_doc.field_of_study_code or "", niveau),
        annee=academic_year,
        semestre_label=_code_semestre(semestre_effectif),
        matiere=ue_info.get("intitule") or teaching_unit,
        code_matiere=code_matiere,
        inscrits=len(lignes),
        admis=admis,
        echecs=echecs,
        taux=taux,
        evaluations=evaluations,
        lignes=lignes,
    )

    frappe.response["filename"] = "PV_{0}_{1}.pdf".format(
        (code_matiere or teaching_unit).replace("/", "-"),
        (niveau or "").replace(" ", "-"),
    )
    frappe.response["filecontent"] = _html_en_pdf(html)
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/pdf"


@frappe.whitelist()
def generer_pdf_cc(academic_year, filiere, niveau, semestre, teaching_unit, session_examen=None, type_dexamen=None):
    """Génère la feuille des notes de contrôle continu (CC uniquement).

    Document de travail présentant, pour chaque étudiant inscrit, uniquement
    la note de CC (moyenne harmonisée, plus le CCTP si la formule l'utilise) :
    le « Télécharger PDF » du mode Contrôle continu ne mélange jamais les
    notes d'examen. Le document réutilise le template de la fiche de report.
    """
    _verifier_acces_enseignant(teaching_unit)
    args = {
        "academic_year": academic_year,
        "semestre": _semestre_effectif(
            {
                "academic_year": academic_year,
                "semestre": semestre,
                "teaching_unit": teaching_unit,
            }
        ),
        "filiere": filiere,
        "niveau": niveau,
        "teaching_unit": teaching_unit,
    }
    students = _get_etudiants(academic_year, filiere, niveau, teaching_unit)
    sessions = _sessions_avec_choix(args, session_examen, type_dexamen)
    notes = _charger_notes(students, teaching_unit, sessions)
    lignes = _lignes_unifiees(students, notes, teaching_unit)
    credit = _credits_ue(teaching_unit, filiere, niveau)

    has_cctp = any(ligne.get("cctp") is not None for ligne in lignes)

    ue_info = _get_ue_info(teaching_unit, filiere, niveau)
    code = ue_info.get("code") or ""
    intitule = ue_info.get("intitule") or teaching_unit
    matiere = "{0} — {1}".format(code, intitule) if code and code != intitule else intitule

    colonnes = [_("N°"), _("Matricule"), _("Nom"), _("Prénom"), _("Crédit")]
    if has_cctp:
        colonnes.append("CCTP")
    colonnes.append(_("Note CC"))

    lignes_fiche = []
    for i, ligne in enumerate(lignes, start=1):
        valeurs = {
            "N°": i,
            "Matricule": ligne["matricule"] or ligne["student"],
            "Nom": ligne["nom"],
            "Prénom": ligne["prenom"],
            "Crédit": credit,
        }
        if has_cctp:
            valeurs["CCTP"] = _fmt(ligne.get("cctp"))
        valeurs["Note CC"] = _fmt(ligne.get("cc"))
        lignes_fiche.append(valeurs)

    from types import SimpleNamespace

    from udshed.api.examen_anonymat import _html_fiche

    session_doc = SimpleNamespace(
        academic_year=academic_year or "",
        semestre=args["semestre"],
        type_dexamen=_("Contrôle continu"),
        statut=frappe.db.get_value("Session Examen", sessions["cc"], "statut") or "",
    )
    html = _html_fiche(
        titre=_("Notes de contrôle continu"),
        mention_confidentiel="",
        session_doc=session_doc,
        matiere=matiere,
        colonnes=colonnes,
        lignes=lignes_fiche,
    )

    frappe.response["filename"] = "Notes_CC_{0}.pdf".format(
        teaching_unit.replace("/", "-")
    )
    frappe.response["filecontent"] = _html_en_pdf(html)
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/pdf"


@frappe.whitelist()
def _feuille_saisie_entetes(entetes):
    """Colonnes de la feuille de saisie : Code d'anonymat + Crédit + notes.

    La feuille s'imprime en mode anonyme : la colonne « Matricule » devient
    « Code d'anonymat » et les colonnes Nom / Prénom sont supprimées. Seules
    restent l'identification par code et les colonnes de notes à remplir
    (le crédit est conservé).
    """
    feuille = []
    for h in entetes:
        if h == _("Matricule"):
            feuille.append(_("Code d'anonymat"))
        elif h in (_("Nom"), _("Prénom")):
            continue
        else:
            feuille.append(h)
    if _("Crédit") not in feuille:
        pos = 1 if feuille[0:1] == [_("Code d'anonymat")] else 0
        feuille.insert(pos, _("Crédit"))
    return feuille


@frappe.whitelist()
def export_modele_pdf(
    type_dexamen,
    cc_columns=None,
    academic_year=None,
    filiere=None,
    niveau=None,
    semestre=None,
    teaching_unit=None,
    anonyme=None,
):
    """Télécharge la feuille de saisie des notes en PDF (étudiants pré-remplis).

    La feuille réutilise le template de la fiche de report (logo, bandeau,
    filigrane, signatures) : chaque étudiant figure ligne par ligne,
    identifié uniquement par son **code d'anonymat** (propre à la matière et
    au type d'examen), suivi du crédit de l'UE et des colonnes de notes à
    remplir (cellules blanches). Les colonnes Matricule / Nom / Prénom sont
    supprimées.
    """
    cc_columns = _colonnes_cc(cc_columns)
    entetes = _en_tetes(type_dexamen, cc_columns)
    if teaching_unit:
        entetes = _entetes_avec_tp(entetes, type_dexamen, teaching_unit)
    entetes = _feuille_saisie_entetes(entetes)

    students = []
    credit = ""
    if teaching_unit and academic_year and filiere and niveau:
        students = _get_etudiants(academic_year, filiere, niveau, teaching_unit)
        credit = _credits_ue(teaching_unit, filiere, niveau)

    codes = _exiger_codes_anonymes(
        students,
        teaching_unit,
        type_dexamen,
        libelle=_("la feuille de saisie"),
    )
    lignes = []
    for s in students:
        ligne = {}
        for h in entetes:
            if h == _("Code d'anonymat"):
                ligne[h] = codes.get(s["student"], "")
            elif h == _("Crédit"):
                ligne[h] = credit
            else:
                ligne[h] = ""
        lignes.append(ligne)

    if type_dexamen == "Examen":
        session_type = _("Examen de session normal")
    elif type_dexamen == "Rattrapage":
        session_type = _("Examen de rattrapage")
    elif type_dexamen == "CC":
        session_type = _("Contrôle continu")
    elif type_dexamen == "TP":
        session_type = _("Travaux pratiques")
    else:
        session_type = type_dexamen or ""

    titre = _("Modèle de saisie des notes — {0}").format(type_dexamen)
    from types import SimpleNamespace

    from udshed.api.examen_anonymat import _html_fiche, _matiere_label

    session_doc = SimpleNamespace(
        academic_year=academic_year or "",
        semestre=_semestre_effectif(
            {
                "academic_year": academic_year,
                "semestre": semestre,
                "teaching_unit": teaching_unit,
            }
        ),
        type_dexamen=session_type,
        statut=_("À saisir"),
    )
    html = _html_fiche(
        titre=titre,
        mention_confidentiel="",
        session_doc=session_doc,
        matiere=_matiere_label(teaching_unit) if teaching_unit else None,
        colonnes=entetes,
        lignes=lignes,
        notes_footer=None,
        vide="&nbsp;",
    )

    frappe.response["filename"] = "Feuille_saisie_{0}.pdf".format(
        type_dexamen.lower()
    )
    frappe.response["filecontent"] = _html_en_pdf(html)
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/pdf"


@frappe.whitelist()
def download_fiche_report_pdf(academic_year, filiere, niveau, semestre, teaching_unit, type_dexamen=None, session_examen=None):
    """Fiche de report vierge (Examen ou Rattrapage) avec les codes d'anonymat.

    Fiche que l'enseignant imprime pour relever les notes au moment de la
    correction : chaque étudiant figure ligne par ligne, identifié par son
    code d'anonymat propre à la matière et au type d'examen (normal ou
    rattrapage), avec une colonne vide « Note /20 » à remplir. Aucune copie
    corrigée n'est nécessaire : la fiche est disponible dès l'inscription des
    étudiants. Le template (fiche d'anonymat avec filigrane) est identique
    pour l'examen et le rattrapage ; seul le type d'examen et le jeu de codes
    changent.
    """
    if _mode_saisie(type_dexamen) == "rattrapage":
        type_reel = TYPE_RATTRAPAGE
        titre = _("Fiche de report — Rattrapage")
        suffixe = "rattrapage"
    else:
        type_reel = TYPE_NORMALE
        titre = _("Fiche de report — Examen normal")
        suffixe = "examen"
    args = {
        "academic_year": academic_year,
        "filiere": filiere,
        "niveau": niveau,
        "semestre": _semestre_effectif(
            {
                "academic_year": academic_year,
                "semestre": semestre,
                "teaching_unit": teaching_unit,
            }
        ),
        "teaching_unit": teaching_unit,
    }
    students = _get_etudiants(academic_year, filiere, niveau, teaching_unit)
    if not students:
        frappe.throw(_("Aucun étudiant inscrit pour générer la fiche de report."))
    codes = _exiger_codes_anonymes(
        students,
        teaching_unit,
        type_reel,
        libelle=_("la fiche de report"),
    )

    ue_info = _get_ue_info(teaching_unit, filiere, niveau)
    code = ue_info.get("code") or ""
    intitule = ue_info.get("intitule") or teaching_unit
    matiere = "{0} — {1}".format(code, intitule) if code and code != intitule else intitule

    # La session choisie au sélecteur prime sur la résolution automatique.
    session_name = _valider_session_cible(args, session_examen, type_reel) or _chercher_session(
        args, type_reel
    )
    if session_name:
        session_doc = frappe.get_doc("Session Examen", session_name)
    else:
        from types import SimpleNamespace

        session_doc = SimpleNamespace(
            academic_year=academic_year,
            semestre=args["semestre"],
            type_dexamen=type_reel,
            statut="",
        )

    colonnes = [_("N°"), _("Code anonymat"), _("Matricule"), _("Nom"), _("Prénom"), _("Note /20")]
    lignes = []
    for i, s in enumerate(students, start=1):
        lignes.append(
            {
                "N°": i,
                "Code anonymat": codes.get(s["student"], ""),
                "Matricule": s.get("matricule") or s.get("student") or "",
                "Nom": s.get("nom") or "",
                "Prénom": s.get("prenom") or "",
                "Note /20": " ",
            }
        )

    from udshed.api.examen_anonymat import _html_fiche

    html = _html_fiche(
        titre=titre,
        mention_confidentiel="",
        session_doc=session_doc,
        matiere=matiere,
        colonnes=colonnes,
        lignes=lignes,
        notes_footer=None,
    )

    frappe.response["filename"] = "Fiche_report_{0}_{1}.pdf".format(
        suffixe, teaching_unit.replace("/", "-")
    )
    frappe.response["filecontent"] = _html_en_pdf(html)
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/pdf"


@frappe.whitelist()
def export_notes(academic_year, filiere, niveau, semestre, teaching_unit, type_dexamen, cc_columns=None, anonyme=None, session_examen=None):
    """Exporte les notes déjà saisies au format Excel.

    ``anonyme`` (0/1) : les identités sont remplacées par les codes anonymes
    de la fiche d'anonymat (AN0001…) ; l'import relit ensuite indifféremment
    matricules ou codes anonymes.
    """
    cc_columns = _colonnes_cc(cc_columns)
    args = {"academic_year": academic_year, "filiere": filiere, "niveau": niveau, "semestre": _semestre_effectif({"academic_year": academic_year, "semestre": semestre, "teaching_unit": teaching_unit}), "teaching_unit": teaching_unit}
    students = _get_etudiants(academic_year, filiere, niveau, teaching_unit)
    anonymes = bool(anonyme)
    if anonymes:
        codes = _exiger_codes_anonymes(
            students, teaching_unit, type_dexamen, libelle=_("l'export anonyme")
        )
    else:
        codes = {}

    sessions = _sessions_avec_choix(args, session_examen, type_dexamen)
    notes = _charger_notes(students, teaching_unit, sessions)
    lignes_unifiees = _lignes_unifiees(students, notes, teaching_unit)
    credit = _credits_ue(teaching_unit, filiere, niveau)

    entetes = _en_tetes(type_dexamen, cc_columns)
    entetes = _entetes_avec_tp(entetes, type_dexamen, teaching_unit)
    lignes = [entetes]
    for s in students:
        nom = s["student"]
        identite = _identite_export(s, anonymes, codes)
        if type_dexamen == "CC":
            # Le contrôle continu (CC) est **toujours nominatif** : il ne fait pas
            # partie de l'anonymat d'examen. On ignore le drapeau 'anonyme'.
            identite_cc = [s["matricule"], s["nom"], s["prenom"]]
            harmonise = next((l for l in lignes_unifiees if l["student"] == nom), {})
            valeur_cc = harmonise.get("cc")
            if valeur_cc is None:
                # Repli sur la session CC historique (saisie indépendante).
                valeur_cc = notes["CC"].get(nom, {}).get("note_cc_moyenne")
            lignes.append(
                identite_cc + [credit] + [valeur_cc for _ in cc_columns] + [valeur_cc]
            )
        elif type_dexamen == "Examen":
            ex = notes["Examen"].get(nom, {})
            ligne = identite + [credit]
            if _("Note de TP") in entetes:
                ligne.append(ex.get("note_tp"))
            ligne.append(ex.get("note_examen"))
            lignes.append(ligne)
        elif type_dexamen == "TP":
            tp = notes["TP"].get(nom, {})
            lignes.append(identite + [credit, tp.get("note_tp")])
        elif type_dexamen == "Rattrapage":
            rt = notes["Rattrapage"].get(nom, {})
            lignes.append(
                identite + [rt.get("note_examen"), rt.get("note_examen_rattrapage"), rt.get("note_examen_active")]
            )

    _repondre_xlsx(lignes, "notes_{0}_{1}.xlsx".format(teaching_unit.replace("/", "-"), type_dexamen.lower()))


@frappe.whitelist()
def export_evaluations(academic_year, filiere, niveau, semestre, teaching_unit, anonyme=None, session_examen=None, type_dexamen=None):
    """Exporte la saisie unifiée (CC, CCTP, EXAMTP, EXAM) au format Excel.

    ``anonyme`` (0/1) : les identités sont remplacées par les codes anonymes
    propres à la matière (AN0001…) ; les cellules Nom / Prénom sont vidées.
    **En mode anonyme, seules les colonnes d'examen (EXAM) sont exportées :**
    le CC, CCTP et EXAMTP sont des évaluations nominatives (contrôle continu)
    et ne font pas partie de l'anonymat d'examen.
    L'import relit indifféremment matricules ou codes anonymes.
    """
    args = {"academic_year": academic_year, "filiere": filiere, "niveau": niveau, "semestre": _semestre_effectif({"academic_year": academic_year, "semestre": semestre, "teaching_unit": teaching_unit}), "teaching_unit": teaching_unit}
    students = _get_etudiants(academic_year, filiere, niveau, teaching_unit)
    sessions = _sessions_avec_choix(args, session_examen, type_dexamen)
    notes = _charger_notes(students, teaching_unit, sessions)
    credit = _credits_ue(teaching_unit, filiere, niveau)

    anonymes = bool(anonyme)
    if anonymes:
        # En mode anonyme : on n'exporte que l'examen anonyme (EXAM).
        # CC, CCTP, EXAMTP sont nominatifs (contrôle continu) -> exclus.
        lignes = [["Matricule", "Nom", "Prénoms", "Crédits", "EXAM", "MOY", "GRD", "PTS"]]
        for ligne in _lignes_unifiees(students, notes, teaching_unit):
            lignes.append(
                [
                    ligne["code_anonyme"],
                    "",
                    "",
                    credit,
                    ligne.get("examen"),
                    ligne.get("note_finale"),
                    ligne.get("grade"),
                    ligne.get("point"),
                ]
            )
    else:
        # Mode nominatif : toutes les colonnes.
        lignes = [["Matricule", "Nom", "Prénoms", "Crédits", "CC", "CCTP", "EXAMTP", "EXAM", "MOY", "GRD", "PTS"]]
        for ligne in _lignes_unifiees(students, notes, teaching_unit):
            lignes.append(
                [
                    ligne["matricule"],
                    ligne["nom"],
                    ligne["prenom"],
                    credit,
                    ligne.get("cc"),
                    ligne.get("cctp"),
                    ligne.get("examtp"),
                    ligne.get("examen"),
                    ligne.get("note_finale"),
                    ligne.get("grade"),
                    ligne.get("point"),
                ]
            )

    _repondre_xlsx(lignes, "notes_{0}_evaluations.xlsx".format(teaching_unit.replace("/", "-")))
