# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Anonymat des copies d'examen : codes, correction, validation, levée.

Principe d'architecture
-----------------------
- « Examen Anonymat » porte l'unique correspondance (étudiant, session, matière)
  vers un code d'anonymat confidentiel. Rôles restreints uniquement.
- « Copie Examen » est la vue de correction : aucun champ étudiant. Le
  correcteur ne voit que le code, la matière et le fichier de la copie.
- L'anonymat est « réel au niveau des permissions » : le lien vers l'étudiant
  est indisponible au rôle Correcteur, même hors API.

Intégration dans le flux de notes
---------------------------------
À la levée d'anonymat (rôle autorisé uniquement), les notes issues des copies
sont injectées dans le flux existant via les fonctions de saisie
(`_sauvegarder_examen` / `_sauvegarder_rattrapage`). La suite du parcours reste
inchangée : validation, publication, calcul automatique des résultats MPS/MPC.
"""

import random

import frappe
from frappe import _
from frappe.utils import cint, flt, now

from udshed.api.resultats_page import _etudiants_classe, _ues_classe
from udshed.api.saisie_notes import (
    TYPE_NORMALE,
    TYPE_RATTRAPAGE,
    _get_or_create_session,
    _get_ue_info,
    _html_en_pdf,
    _sauvegarder_examen,
    _sauvegarder_rattrapage,
)

# Rôles pouvant corriger des copies (mais jamais voir l'identité).
ROLES_CORRECTION = ("System Manager", "Coordonateur", "Correcteur", "Teacher")

# Rôles pouvant générer les codes, valider la correction et lever l'anonymat.
ROLES_RESPONSABLE = ("System Manager", "Coordonateur", "Registration Manager")

# Alphabet sans ambiguïté (ni 0/O/1/I/l).
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

LONGUEUR_CODE = 6

STATUTS_ATTENTE = ("En attente", "Déposée", "En correction")
STATUTS_INJECTABLES = ("Validée",)


# ---------------------------------------------------------------------------
# Contrôles d'accès
# ---------------------------------------------------------------------------
def _verifier_correcteur():
    """Bloque si l'utilisateur connecté n'est pas autorisé à corriger."""
    roles = set(frappe.get_roles(frappe.session.user))
    if not roles & set(ROLES_CORRECTION):
        frappe.throw(_("Accès refusé : réservé à la correction des copies d'examen."))


def _verifier_responsable():
    """Bloque si l'utilisateur connecté n'est pas un responsable autorisé."""
    roles = set(frappe.get_roles(frappe.session.user))
    if not roles & set(ROLES_RESPONSABLE):
        frappe.throw(
            _("Accès refusé : opération réservée au responsable des examens.")
        )


def _est_responsable():
    """True si l'utilisateur connecté est un responsable autorisé."""
    return bool(set(frappe.get_roles(frappe.session.user)) & set(ROLES_RESPONSABLE))


def _niveau_label(niveau_row):
    """Label d'un niveau depuis le name de la ligne de la grille de la filière."""
    if not niveau_row:
        return None
    label = frappe.db.get_value("Field of study Level", niveau_row, "level")
    return label or str(niveau_row)


# ---------------------------------------------------------------------------
# Génération des codes
# ---------------------------------------------------------------------------
def _generer_code_anonymat():
    """Code aléatoire court, non prédictible, garanti unique."""
    for _ in range(60):
        code = "".join(random.choice(ALPHABET) for _ in range(LONGUEUR_CODE))
        if not frappe.db.exists("Examen Anonymat", {"code_anonymat": code}):
            return code
    frappe.throw(_("Impossible de générer un code d'anonymat unique."))


def _creer_copie(anonymat):
    """Crée la copie d'examen associée à un code (jamais d'identité)."""
    if frappe.db.exists(
        "Copie Examen",
        {"examen_anonymat": anonymat.name, "session_examen": anonymat.session_examen},
    ):
        return
    doc = frappe.new_doc("Copie Examen")
    doc.session_examen = anonymat.session_examen
    doc.teaching_unit = anonymat.teaching_unit
    doc.code_anonymat = anonymat.code_anonymat
    doc.examen_anonymat = anonymat.name
    doc.statut_correction = "En attente"
    doc.insert(ignore_permissions=True)


@frappe.whitelist()
def generer_codes(session):
    """Génère (ou complète) les codes d'anonymat d'une session d'examen.

    Un code unique est attribué à chaque couple (étudiant, matière) de chaque
    classe concernée. Idempotent : les combinaisons déjà présentes sont
    conservées, seules les combinaisons manquantes sont créées.
    """
    _verifier_responsable()
    session_doc = frappe.get_doc("Session Examen", session)
    if not session_doc.classes_concernees:
        frappe.throw(_("La session d'examen n'a aucune classe concernée."))

    genere = 0
    for ligne in session_doc.classes_concernees:
        filiere = ligne.filiere
        niveau = _niveau_label(ligne.niveau)
        ues = _ues_classe(
            session_doc.academic_year,
            filiere,
            niveau,
            semestre=session_doc.semestre,
        )
        ue_names = [u.name for u in ues]
        if not ue_names:
            continue

        for etudiant in _etudiants_classe(
            session_doc.academic_year, filiere, niveau, ue_names
        ):
            nom = etudiant["student"]
            for ue in ue_names:
                if frappe.db.exists(
                    "Examen Anonymat",
                    {
                        "session_examen": session,
                        "teaching_unit": ue,
                        "student": nom,
                    },
                ):
                    continue
                anonymat = frappe.new_doc("Examen Anonymat")
                anonymat.session_examen = session
                anonymat.teaching_unit = ue
                anonymat.student = nom
                anonymat.filiere = filiere
                anonymat.niveau = niveau
                anonymat.code_anonymat = _generer_code_anonymat()
                anonymat.statut = "Généré"
                anonymat.insert(ignore_permissions=True)
                _creer_copie(anonymat)
                genere += 1

    return {"session": session, "genere": genere}


# ---------------------------------------------------------------------------
# Consultation (correction)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def obtenir_sessions(academic_year=None):
    """Sessions d'examen proposées à la correction (avec leurs années)."""
    _verifier_correcteur()
    years = frappe.get_all("Academic Year", fields=["name"], order_by="name desc")
    filters = {"academic_year": academic_year} if academic_year else {}
    sessions = frappe.get_all(
        "Session Examen",
        filters=filters,
        fields=["name", "academic_year", "type_dexamen", "statut", "semestre"],
        order_by="creation desc",
    )
    return {
        "years": [y.name for y in years],
        "sessions": sessions,
    }


@frappe.whitelist()
def obtenir_ues_session(session):
    """Matières d'une session avec l'état de leurs copies (résumé)."""
    _verifier_correcteur()
    names = frappe.get_all(
        "Copie Examen",
        filters={"session_examen": session},
        fields=["teaching_unit", "statut_correction", "absent"],
    )
    resume = {}
    for row in names:
        info = resume.setdefault(
            row.teaching_unit,
            {"total": 0, "corrigees": 0, "validees": 0, "manquantes": 0},
        )
        info["total"] += 1
        if row.statut_correction == "Corrigée":
            info["corrigees"] += 1
        elif row.statut_correction == "Validée":
            info["validees"] += 1
        elif row.statut_correction == "Copie manquante" or row.absent:
            info["manquantes"] += 1
    return {
        "session": session,
        "matieres": resume,
    }


@frappe.whitelist()
def obtenir_etat_anonymat(session, teaching_unit=None):
    """Résumé de l'anonymat pour la page « saisie des notes ».

    Visible par correcteur et responsable ; les actions ne sont proposées
    qu'au responsable (ROLES_RESPONSABLE).
    """
    _verifier_correcteur()
    templatefilter = {"session_examen": session}
    if teaching_unit:
        templatefilter["teaching_unit"] = teaching_unit

    codes = frappe.db.count("Examen Anonymat", templatefilter)

    copies = frappe.get_all(
        "Copie Examen",
        filters=templatefilter,
        fields=["statut_correction", "absent"],
    )
    resume = {"total": 0, "corrigees": 0, "validees": 0, "manquantes": 0}
    for row in copies:
        resume["total"] += 1
        if row.statut_correction == "Corrigée":
            resume["corrigees"] += 1
        elif row.statut_correction == "Validée":
            resume["validees"] += 1
        elif row.statut_correction == "Copie manquante" or row.absent:
            resume["manquantes"] += 1

    report_filters = {
        "session_examen": session,
        "statut_correction": "Validée",
        "note_examen": ["is", "set"],
    }
    if teaching_unit:
        report_filters["teaching_unit"] = teaching_unit

    return {
        "session": session,
        "enseignement": teaching_unit or None,
        "codes": codes,
        "copies": resume,
        "fiches_report": frappe.db.count("Copie Examen", report_filters),
        "statut_session": frappe.db.get_value(
            "Session Examen", session, "statut"
        ),
        "responsable": _est_responsable(),
    }


@frappe.whitelist()
def charger_copies(session, teaching_unit=None):
    """Copies à corriger : uniquement code, matière, fichier et note.

    Aucune donnée d'identité n'est renvoyée : l'anonymat est garanti côté
    présentation comme côté modèle de données.
    """
    _verifier_correcteur()
    filters = {"session_examen": session}
    if teaching_unit:
        filters["teaching_unit"] = teaching_unit
    copies = frappe.get_all(
        "Copie Examen",
        filters=filters,
        fields=[
            "name",
            "session_examen",
            "teaching_unit",
            "code_anonymat",
            "statut_correction",
            "fichier_copie",
            "note_examen",
            "observation",
            "absent",
            "corrige_par",
            "corrige_le",
        ],
        order_by="code_anonymat",
    )
    return {"session": session, "teaching_unit": teaching_unit, "copies": copies}


# ---------------------------------------------------------------------------
# Correction
# ---------------------------------------------------------------------------
@frappe.whitelist()
def enregistrer_correction(copie, note=None, observation=None, absent=None):
    """Enregistre la note d'une copie. Aucun étudiant n'est accessible ici."""
    _verifier_correcteur()
    doc = frappe.get_doc("Copie Examen", copie)

    absent = cint(absent)
    doc.absent = absent
    if absent:
        doc.note_examen = None
        doc.statut_correction = "Copie manquante"
    else:
        if note in (None, ""):
            frappe.throw(_("La note d'examen est obligatoire pour une copie corrigée."))
        valeur = flt(note)
        if valeur < 0 or valeur > 20:
            frappe.throw(_("La note d'examen doit être comprise entre 0 et 20."))
        doc.note_examen = valeur
        doc.statut_correction = "Corrigée"

    doc.observation = observation
    doc.corrige_par = frappe.session.user
    doc.corrige_le = now()
    doc.save()

    return {
        "copie": doc.name,
        "statut_correction": doc.statut_correction,
    }


# ---------------------------------------------------------------------------
# Validation de la correction et levée de l'anonymat
# ---------------------------------------------------------------------------
@frappe.whitelist()
def valider_corrections(session, teaching_unit=None):
    """Valide les corrections terminées d'une session (avant levée)."""
    _verifier_responsable()
    filters = {"session_examen": session}
    if teaching_unit:
        filters["teaching_unit"] = teaching_unit

    toutes = frappe.get_all(
        "Copie Examen",
        filters=filters,
        fields=["name", "statut_correction"],
    )
    en_attente = [c.name for c in toutes if c.statut_correction in STATUTS_ATTENTE]
    if en_attente:
        frappe.throw(
            _("{0} copie(s) ne sont pas encore corrigées. La validation des "
              "corrections est impossible tant que toutes les copies ne sont "
              "pas corrigées ou marquées manquantes.").format(len(en_attente))
        )

    a_valider = [
        c.name
        for c in toutes
        if c.statut_correction == "Corrigée"
    ]
    for nom in a_valider:
        frappe.db.set_value("Copie Examen", nom, "statut_correction", "Validée")

    return {"session": session, "validees": len(a_valider)}


@frappe.whitelist()
def lever_anonymat(session):
    """Lève l'anonymat et injecte les notes corrigées dans le flux existant.

    Pour chaque matière, les notes des copies validées sont enregistrées via
    les fonctions de saisie existantes (`_sauvegarder_examen` ou
    `_sauvegarder_rattrapage`). Le parcours ultérieur (validation,
    publication, calcul MPS/MPC) est strictement inchangé.

    Seules les copies au statut « Validée » sont injectées ; les copies
    manquantes sont ignorées (aucune note). Les codes levés ne sont jamais
    réinjectés (idempotence).

    Pour chaque note injectée, une « Fiche Report » est créée : matricule,
    nom/prénom, matière, session et note reportée (celle enregistrée lors de
    la correction). Cette fiche constitue la trace de la levée d'anonymat et
    référence le document « Session Examen Note » qui alimente ensuite les
    résultats académiques.
    """
    _verifier_responsable()
    session_doc = frappe.get_doc("Session Examen", session)
    est_rattrapage = session_doc.type_dexamen == TYPE_RATTRAPAGE

    anonymats = {
        a.code_anonymat: a
        for a in frappe.get_all(
            "Examen Anonymat",
            filters={"session_examen": session, "statut": ["!=", "Levé"]},
            fields=[
                "name",
                "student",
                "filiere",
                "niveau",
                "code_anonymat",
                "matricule",
                "nom",
                "prenom",
            ],
        )
    }
    copies = frappe.get_all(
        "Copie Examen",
        filters={"session_examen": session, "statut_correction": "Validée"},
        fields=["name", "teaching_unit", "code_anonymat", "note_examen"],
    )

    groupes = {}
    for copie in copies:
        anonymat = anonymats.get(copie.code_anonymat)
        if not anonymat or copie["note_examen"] is None:
            continue
        cle = (anonymat["filiere"], anonymat["niveau"], copie["teaching_unit"])
        groupes.setdefault(cle, []).append(
            {
                "anonymat_name": anonymat["name"],
                "student": anonymat["student"],
                "matricule": anonymat.get("matricule") or anonymat["student"],
                "nom": anonymat.get("nom") or "",
                "prenom": anonymat.get("prenom") or "",
                "code_anonymat": copie["code_anonymat"],
                "copie": copie["name"],
                "note": flt(copie["note_examen"]),
            }
        )

    injecte = 0
    leve = 0
    erreurs = []
    for (filiere, niveau, ue), lignes in groupes.items():
        args = {
            "academic_year": session_doc.academic_year,
            "filiere": filiere,
            "niveau": niveau,
            "semestre": session_doc.semestre,
            "teaching_unit": ue,
        }
        rows = [
            {"student": ligne["student"], "note_examen": ligne["note"]}
            if not est_rattrapage
            else {"student": ligne["student"], "note_examen_rattrapage": ligne["note"]}
            for ligne in lignes
        ]
        try:
            if est_rattrapage:
                _sauvegarder_rattrapage(args, rows)
            else:
                _sauvegarder_examen(args, rows)
        except frappe.exceptions.ValidationError as exc:
            message = str(exc) or exc
            erreurs.append("<b>{0}</b> ({1}/{2}) : {3}".format(ue, filiere, niveau, message))
            continue

        session_notes = _get_or_create_session(
            args, TYPE_RATTRAPAGE if est_rattrapage else TYPE_NORMALE
        )

        for ligne in lignes:
            _enregistrer_trace_levee(
                session=session,
                session_notes=session_notes,
                teaching_unit=ue,
                ligne=ligne,
            )
        injecte += len(lignes)
        leve += len(lignes)

    if erreurs:
        frappe.throw(
            _("La levée d'anonymat est incomplète :<br>{0}").format("<br>".join(erreurs))
        )

    return {"session": session, "injectees": injecte, "levees": leve}


def _enregistrer_trace_levee(session, session_notes, teaching_unit, ligne):
    """Trace la levée : statut/anonymat + création de la fiche de report.

    La fiche de report porte l'identité (matricule, nom, prénom), la matière,
    la session et la note reportée issue de la correction. Elle référence le
    document « Session Examen Note » créé dans le flux des notes.
    """
    frappe.db.set_value(
        "Examen Anonymat",
        ligne["anonymat_name"],
        {
            "statut": "Levé",
            "leve_par": frappe.session.user,
            "leve_le": now(),
        },
    )

    note_doc = frappe.db.get_value(
        "Session Examen Note",
        {
            "session_examen": session_notes,
            "student": ligne["student"],
            "teaching_unit": teaching_unit,
        },
        "name",
    )

    fiche = frappe.new_doc("Fiche Report")
    fiche.session_examen = session_notes
    fiche.teaching_unit = teaching_unit
    fiche.code_anonymat = ligne["code_anonymat"]
    fiche.student = ligne["student"]
    fiche.matricule = ligne["matricule"]
    fiche.nom = ligne["nom"]
    fiche.prenom = ligne["prenom"]
    fiche.note_reportee = flt(ligne["note"])
    fiche.session_examen_note = note_doc
    fiche.examen_anonymat = ligne["anonymat_name"]
    fiche.copie_examen = ligne["copie"]
    fiche.leve_par = frappe.session.user
    fiche.leve_le = now()
    fiche.insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Fiches imprimables (PDF)
# ---------------------------------------------------------------------------
_CSS_FICHE = """
* { box-sizing: border-box; }
body { font-family: "Times New Roman", Times, serif; color: #1e2025; margin: 0; padding: 0; font-size: 12px; }
.page { width: 100%; }
.header { display: flex; align-items: center; border-bottom: 3px solid #1e2025; padding-bottom: 10px; margin-bottom: 14px; }
.header .logo { height: 56px; margin-right: 14px; }
.header .logo-placeholder { width: 56px; height: 56px; border: 1.5px dashed #b9bcc4; border-radius: 4px; display: flex; align-items: center; justify-content: center; color: #a0a4ad; font-size: 8px; text-transform: uppercase; text-align: center; padding: 4px; }
.header .brand { flex: 1; }
.header .brand .univ { font-size: 15px; font-weight: 800; letter-spacing: .5px; }
.header .brand .sub { font-size: 10px; color: #525462; margin-top: 2px; }
.header .titre { text-align: right; }
.header .titre .doc { font-size: 16px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; }
.header .titre .conf { font-size: 10px; font-weight: 700; margin-top: 4px; color: #b91c1c; text-transform: uppercase; letter-spacing: .5px; }
.header .titre .date { font-size: 10px; color: #6b6d7a; margin-top: 2px; }
.bandeau { background: #f4f6f9; border: 1px solid #e0e3ea; border-radius: 6px; padding: 10px 12px; margin-bottom: 12px; }
.bandeau .row { display: flex; flex-wrap: wrap; gap: 8px 26px; font-size: 11.5px; }
.bandeau .row span b { color: #525462; }
.bandeau .matiere { margin-top: 8px; font-size: 11.5px; }
.bandeau .matiere b { color: #525462; }
table.data { width: 100%; border-collapse: collapse; margin-top: 6px; }
table.data th { background: #1e2025; color: #fff; border: 1px solid #1e2025; text-align: left; font-size: 10px; text-transform: uppercase; letter-spacing: .5px; padding: 6px 8px; }
table.data td { border: 1px solid #d4d6dd; padding: 6px 8px; font-size: 11px; }
tr.row-even td { background: #fafbfc; }
.td-num { text-align: right; }
.vide { color: #9aa0a8; font-style: italic; }
.sign { display: flex; justify-content: space-between; margin-top: 44px; }
.sign .s { width: 42%; border-top: 1px solid #1e2025; padding-top: 6px; font-size: 11px; text-align: center; color: #525462; }
.footer { margin-top: 18px; border-top: 1px solid #e0e3ea; padding-top: 8px; font-size: 9.5px; color: #6b6d7a; text-align: center; }

/* ================= FILIGRANE ================= */
.watermark {
    position: fixed;
    left: 50%;
    top: 55%;
    transform: translate(-50%, -50%) rotate(-28deg);
    font-family: Arial, Helvetica, sans-serif;
    white-space: nowrap;
    pointer-events: none;
    z-index: 10;
}
.watermark img {
    width: 150mm;
    opacity: 0.08;
}
"""


def _matiere_label(teaching_unit):
    """Libellé lisible d'une matière (code + intitulé du cours)."""
    try:
        info = _get_ue_info(teaching_unit)
        code = info.get("code") or ""
        intitule = info.get("intitule") or teaching_unit
        if code and code != intitule:
            return "{0} — {1}".format(code, intitule)
        return intitule
    except Exception:
        return teaching_unit or ""


def _repondre_pdf(html, filename):
    """Renvoie un PDF en téléchargement (réponse HTTP)."""
    frappe.response["filename"] = filename
    frappe.response["filecontent"] = _html_en_pdf(html)
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/pdf"


def _html_fiche(
    titre,
    mention_confidentiel,
    session_doc=None,
    matiere=None,
    colonnes=None,
    lignes=None,
    notes_footer=None,
    vide="—",
):
    """Construit le HTML imprimable d'une fiche (anonymat ou report).

    ``vide`` : texte affiché dans les cellules vides (défaut « — ») ; passer
    ``&nbsp;`` pour une feuille de saisie à remplir (cellules laissées en
    blanc).
    """
    try:
        from udshed.api.school_setting import get_logo_data_uri

        logo = get_logo_data_uri() or ""
    except Exception:
        logo = ""

    ecole = frappe.db.get_single_value("Udshed Setting", "school_name") or ""

    logo_html = (
        '<img class="logo" src="{0}" alt="logo">'.format(logo)
        if logo
        else '<div class="logo-placeholder">Logo</div>'
    )

    logo_wm = ""
    try:
        from udshed.api.school_setting import get_logo_data_uri

        logo_wm = get_logo_data_uri() or ""
    except Exception:
        logo_wm = ""
    wm_html = '<img src="{0}" alt="">'.format(logo_wm) if logo_wm else ""

    session_doc = session_doc or frappe._dict(
        academic_year="",
        semestre="",
        type_dexamen="",
        statut="",
    )

    session_type = session_doc.type_dexamen or ""
    if session_type == TYPE_NORMALE:
        session_type = "Examen de session normal"
    elif session_type == TYPE_RATTRAPAGE:
        session_type = "Examen de rattrapage"

    today = frappe.utils.formatdate(frappe.utils.today(), "dd-mm-yyyy")

    ths = "".join(
        "<th>{0}</th>".format(frappe.utils.escape_html(h)) for h in colonnes
    )
    corps = ""
    for i, ligne in enumerate(lignes):
        classe = "row-even" if i % 2 == 0 else "row-odd"
        cellules = ""
        for h in colonnes:
            valeur = ligne.get(h, "")
            if valeur in (None, ""):
                cellule = '<span class="vide">{0}</span>'.format(vide)
            elif h == "N°" or h.startswith("Note") or h == "Crédit":
                cellule = '<span class="td-num">{0}</span>'.format(
                    frappe.utils.escape_html(str(valeur))
                )
            else:
                cellule = frappe.utils.escape_html(str(valeur))
            cellules += "<td>{0}</td>".format(cellule)
        corps += "<tr class='{0}'>{1}</tr>".format(classe, cellules)

    if not corps:
        corps = "<tr><td colspan='{0}' class='vide'>Aucune ligne.</td></tr>".format(
            len(colonnes)
        )

    bandeau = (
        "<div class='bandeau'>"
        "<div class='row'>"
        "<span><b>Année académique :</b> {0}</span>"
        "<span><b>Semestre :</b> {1}</span>"
        "<span><b>Session :</b> {2}</span>"
        "<span><b>Statut :</b> {3}</span>"
        "</div>"
        "<div class='matiere'><b>Matière :</b> {4}</div>"
        "</div>"
    ).format(
        frappe.utils.escape_html(session_doc.academic_year or ""),
        frappe.utils.escape_html(session_doc.semestre or ""),
        frappe.utils.escape_html(session_type),
        frappe.utils.escape_html(session_doc.statut or ""),
        frappe.utils.escape_html(matiere or "Toutes les matières"),
    )

    notes_html = ""
    if notes_footer:
        notes_html = "<div class='notes-footer'>{0}</div>".format(notes_footer)

    return (
        "<html><head><meta charset='utf-8'><style>{css}</style></head><body>"
        "<div class='watermark'>{wm}</div>"
        "<div class='page'>"
        "<div class='header'>"
        "{logo}"
        "<div class='brand'>"
        "<div class='univ'>{ecole}</div>"
        "<div class='sub'>Gestion des examens et des notes — Udshed</div>"
        "</div>"
        "<div class='titre'>"
        "<div class='doc'>{titre}</div>"
        "<div class='conf'>{conf}</div>"
        "<div class='date'>Édité le {date}</div>"
        "</div>"
        "</div>"
        "{bandeau}"
        "<table class='data'><thead><tr>{ths}</tr></thead><tbody>{corps}</tbody></table>"
        "{notes}"
        "<div class='sign'>"
        "<div class='s'>Le responsable des examens</div>"
        "<div class='s'>Le Coordonnateur</div>"
        "</div>"
        "<div class='footer'>Document généré automatiquement par Udshed.</div>"
        "</div>"
        "</body></html>"
    ).format(
        css=_CSS_FICHE,
        logo=logo_html,
        ecole=frappe.utils.escape_html(ecole),
        wm=wm_html,
        titre=frappe.utils.escape_html(titre),
        conf=frappe.utils.escape_html(mention_confidentiel or ""),
        date=today,
        bandeau=bandeau,
        ths=ths,
        corps=corps,
        notes=notes_html,
    )


@frappe.whitelist()
def download_fiche_anonymat_pdf(session, teaching_unit=None):
    """PDF confidentiel de la fiche d'anonymat d'une session (responsable).

    Fiche unique par combinaison (étudiant, matière, session) : code
    d'anonymat, matricule, nom/prénom, matière et session. Document réservé
    aux utilisateurs autorisés (jamais le correcteur).
    """
    _verifier_responsable()
    session_doc = frappe.get_doc("Session Examen", session)

    filters = {"session_examen": session}
    if teaching_unit:
        filters["teaching_unit"] = teaching_unit
    anonymats = frappe.get_all(
        "Examen Anonymat",
        filters=filters,
        fields=[
            "code_anonymat",
            "teaching_unit",
            "student",
            "matricule",
            "nom",
            "prenom",
        ],
        order_by="teaching_unit, code_anonymat",
    )
    if not anonymats:
        frappe.throw(_("Aucune fiche d'anonymat pour ces critères."))

    colonnes = ["N°", "Code anonymat", "Matricule", "Nom", "Prénom", "Matière"]
    lignes = [
        {
            "N°": i + 1,
            "Code anonymat": a["code_anonymat"],
            "Matricule": a["matricule"] or a["student"],
            "Nom": a["nom"] or "",
            "Prénom": a["prenom"] or "",
            "Matière": _matiere_label(a["teaching_unit"]),
        }
        for i, a in enumerate(anonymats)
    ]

    html = _html_fiche(
        titre="Fiche d'anonymat",
        mention_confidentiel="Document confidentiel — réservé au responsable des examens",
        session_doc=session_doc,
        matiere=_matiere_label(teaching_unit) if teaching_unit else None,
        colonnes=colonnes,
        lignes=lignes,
    )

    _repondre_pdf(html, "Fiche_anonymat_{0}.pdf".format(session))


@frappe.whitelist()
def download_fiche_report_pdf(session, teaching_unit=None):
    """PDF de la fiche de report d'une session (avant ou après levée).

    La fiche relie chaque copie corrigée et validée (note) à l'étudiant
    (matricule, nom/prénom) via son code d'anonymat. Elle est disponible dès
    que des copies sont validées, y compris avant la levée de l'anonymat ;
    après la levée, la trace « levé par / le » est ajoutée en pied de page.
    """
    _verifier_responsable()
    session_doc = frappe.get_doc("Session Examen", session)

    filters = {"session_examen": session, "statut_correction": "Validée"}
    if teaching_unit:
        filters["teaching_unit"] = teaching_unit
    copies = frappe.get_all(
        "Copie Examen",
        filters=filters,
        fields=["code_anonymat", "teaching_unit", "note_examen"],
        order_by="teaching_unit, code_anonymat",
    )
    copies = [c for c in copies if c["note_examen"] is not None]
    if not copies:
        frappe.throw(
            _("Aucune fiche de report pour ces critères : aucune copie corrigée et validée (avec note) dans cette session/matière.")
        )

    anonymats = {
        a["code_anonymat"]: a
        for a in frappe.get_all(
            "Examen Anonymat",
            filters={"session_examen": session},
            fields=[
                "code_anonymat",
                "student",
                "matricule",
                "nom",
                "prenom",
                "statut",
                "leve_par",
                "leve_le",
            ],
        )
    }

    colonnes = ["N°", "Code anonymat", "Matricule", "Nom", "Prénom", "Matière", "Note"]
    lignes = []
    for i, c in enumerate(copies):
        a = anonymats.get(c["code_anonymat"]) or {}
        lignes.append(
            {
                "N°": i + 1,
                "Code anonymat": c["code_anonymat"],
                "Matricule": a.get("matricule") or a.get("student") or "",
                "Nom": a.get("nom") or "",
                "Prénom": a.get("prenom") or "",
                "Matière": _matiere_label(c["teaching_unit"]),
                "Note": "{0}/20".format("{:.2f}".format(c["note_examen"])),
            }
        )

    levees = [
        a
        for a in anonymats.values()
        if a.get("statut") == "Levé" and a.get("leve_par")
    ]
    note_footer = ""
    if levees:
        note_footer = "Anonymat levé par : {0}".format(
            ", ".join(sorted({a["leve_par"] for a in levees}))
        )

    html = _html_fiche(
        titre="Fiche de report",
        mention_confidentiel="",
        session_doc=session_doc,
        matiere=_matiere_label(teaching_unit) if teaching_unit else None,
        colonnes=colonnes,
        lignes=lignes,
        notes_footer=note_footer,
    )

    _repondre_pdf(html, "Fiche_report_{0}.pdf".format(session))