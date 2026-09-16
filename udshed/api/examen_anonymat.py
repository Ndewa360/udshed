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
    TYPE_RATTRAPAGE,
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
    """
    _verifier_responsable()
    session_doc = frappe.get_doc("Session Examen", session)
    est_rattrapage = session_doc.type_dexamen == TYPE_RATTRAPAGE

    anonymats = {
        a.code_anonymat: a
        for a in frappe.get_all(
            "Examen Anonymat",
            filters={"session_examen": session, "statut": ["!=", "Levé"]},
            fields=["name", "student", "filiere", "niveau", "code_anonymat"],
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
        for ligne in lignes:
            frappe.db.set_value(
                "Examen Anonymat", ligne["anonymat_name"], "statut", "Levé"
            )
        injecte += len(lignes)
        leve += len(lignes)

    if erreurs:
        frappe.throw(
            _("La levée d'anonymat est incomplète :<br>{0}").format("<br>".join(erreurs))
        )

    return {"session": session, "injectees": injecte, "levees": leve}