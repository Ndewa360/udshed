# Copyright (c) 2026, Udshed and contributors
# For license information, please see license.txt

"""Résultat d'une UE : moyenne pondérée par les crédits de ses matières.

Une **UE** est un `Teaching Unit Value` (UTI308). Ses **matières** sont les
`Teaching Unit` qui la pointent via `unite_de_valeur` : c'est exactement la
grille d'enseignement, seule source de la composition d'une UE.

Règles de calcul
----------------
1. Note d'une matière = **meilleure** des deux sessions saisies, normale ou
   rattrapage (``MAX(note normale, note rattrapage)``). Une note « Saisi »,
   « Validé » ou « Publié » compte : seul un « Brouillon » est écarté. Le
   résultat d'UE ne dépend donc pas du bouton « Publier ».
2. Note de l'UE = moyenne **pondérée par les crédits** des matières :

       note_ue_pct = Σ(course_poid x note_pct) / Σ(course_poid)

   C'est la formule exacte de la MPS du semestre
   (``udshed.api.resultat_academique.calculer_mps``) : le PV d'UE et le PV de
   semestre ne peuvent donc pas afficher deux notes différentes.
3. Grade / point : grille officielle via ``get_grade_info(..., echelle=100)``.
4. Statut : ``note_ue_pct >= get_seuil_validation(cycle)``.

Aucune division n'est faite tant qu'une seule matière manque : l'UE passe en
« En attente », ce qui garantit qu'aucune moyenne partielle ne fuite dans un PV.
"""

import frappe
from frappe import _
from frappe.utils import flt

from udshed.grade_calculation import get_grade_info, get_seuil_validation, get_student_cycle

TYPE_NORMALE = "Examen de session normal"
TYPE_RATTRAPAGE = "Examen de rattrapage"

# Cycle de vie d'une note : Brouillon -> Saisi -> Validé -> Publié.
# Seul le brouillon est ignoré : dès que la note est « saisie », elle compte
# dans le calcul d'UE, sans attendre la publication.
STATUTS_SAISIS = ("Saisi", "Validé", "Publié")

DOCTYPE = "Resultat UE"


# ---------------------------------------------------------------------- #
#  Composition d'une UE (grille d'enseignement)
# ---------------------------------------------------------------------- #
def _niveau_name(filiere, niveau):
    """Accepte un libellé de niveau (« Licence 3 ») ou son nom interne.

    La page PV fournit un libellé, la note saisie fournit déjà le nom.
    """
    if not niveau:
        return None
    if frappe.db.exists("Field of study Level", niveau):
        return niveau
    if not filiere:
        return None
    noms = frappe.get_all(
        "Field of study Level",
        filters={"parent": filiere, "level": niveau},
        pluck="name",
        limit=1,
    )
    return noms[0] if noms else None


def _credits_matiere(teaching_unit, filiere=None, niveau=None):
    """Poids d'une matière dans son UE, selon la grille d'enseignement.

    Source primaire : ``Course Field of study level item.course_poid``.
    Repli : ``Teaching Unit.credits`` quand la grille n'a pas de poids.
    """
    niveau_id = _niveau_name(filiere, niveau)
    filtres = {"parent": teaching_unit}
    if filiere:
        filtres["filiere"] = filiere
    if niveau_id:
        filtres["niveau"] = niveau_id

    poids = frappe.db.get_value("Course Field of study level item", filtres, "course_poid")
    if poids:
        return flt(poids)
    return flt(frappe.db.get_value("Teaching Unit", teaching_unit, "credits"))


def get_matieres_ue(teaching_unit_value, academic_year=None, filiere=None, niveau=None):
    """Matières d'une UE, dans l'ordre de la grille d'enseignement.

    Args:
        teaching_unit_value: UE (`Teaching Unit Value`).
        academic_year: restreint à une année (la même matière peut changer
            d'une année à l'autre).
        filiere / niveau: restreignent au périmètre de la classe.

    Returns:
        list[dict]: ``teaching_unit``, ``code``, ``intitule``, ``credits``.
    """
    if not teaching_unit_value:
        return []

    filtres = {"unite_de_valeur": teaching_unit_value}
    if academic_year:
        filtres["academic_year"] = academic_year

    teaching_units = frappe.get_all(
        "Teaching Unit",
        filters=filtres,
        fields=["name", "course", "intitule_cours", "semestre"],
        order_by="name asc",
    )

    niveau_id = _niveau_name(filiere, niveau)
    matieres = []
    for tu in teaching_units:
        if filiere or niveau_id:
            lignes = frappe.get_all(
                "Course Field of study level item",
                filters={
                    "parent": tu.name,
                    **({"filiere": filiere} if filiere else {}),
                    **({"niveau": niveau_id} if niveau_id else {}),
                },
                pluck="name",
                limit=1,
            )
            if not lignes:
                # La matière n'est pas dans cette classe : elle n'entre pas
                # dans la moyenne de l'UE de ce périmètre.
                continue

        code = ""
        if tu.course:
            code = frappe.db.get_value("Course", tu.course, "code") or ""
        matieres.append(
            {
                "teaching_unit": tu.name,
                "code": code,
                "intitule": tu.intitule_cours or tu.name,
                "semestre": tu.semestre,
                "credits": _credits_matiere(tu.name, filiere, niveau),
            }
        )
    return matieres


def get_ues_de_matiere(teaching_unit):
    """UE d'une matière (``Teaching Unit.unite_de_valeur``), ou None."""
    if not teaching_unit:
        return None
    return frappe.db.get_value("Teaching Unit", teaching_unit, "unite_de_valeur")


# ---------------------------------------------------------------------- #
#  Note d'une matière : meilleure des deux sessions
# ---------------------------------------------------------------------- #
def _meilleure_note(student, teaching_unit, academic_year, semestre, filiere=None, niveau=None):
    """Note retenue d'une matière : max(session normale, session rattrapage).

    Une seule requête : la meilleure note saisie, toutes sessions confondues. Le
    type de la session gagnante donne directement ``est_rattrapage``.

    Returns:
        dict | None: ``note_pct``, ``note_finale``, ``grade``, ``point``,
        ``est_rattrapage`` — ou None si aucune note saisie.
    """
    conditions = [
        "n.student = %(student)s",
        "n.teaching_unit = %(teaching_unit)s",
        "n.statut IN %(statuts)s",
        "n.note_pct IS NOT NULL",
        "s.academic_year = %(academic_year)s",
        "s.semestre = %(semestre)s",
        "s.type_dexamen IN %(types)s",
    ]
    valeurs = {
        "student": student,
        "teaching_unit": teaching_unit,
        "statuts": STATUTS_SAISIS,
        "academic_year": academic_year,
        "semestre": semestre,
        "types": (TYPE_NORMALE, TYPE_RATTRAPAGE),
    }
    # Restreint à la classe quand elle est connue : sinon les notes du même
    # étudiant dans une autre filière peuvent entrer dans la moyenne, et la
    # requête ramène des sessions sans rapport.
    if filiere:
        conditions.append("n.filiere = %(filiere)s")
        valeurs["filiere"] = filiere
    if niveau:
        conditions.append("n.niveau = %(niveau)s")
        valeurs["niveau"] = niveau

    rows = frappe.db.sql(
        """
        SELECT n.note_pct, n.note_finale, n.grade, n.point, s.type_dexamen
        FROM `tabSession Examen Note` n
        INNER JOIN `tabSession Examen` s ON s.name = n.session_examen
        WHERE {conditions}
        ORDER BY n.note_pct DESC, n.modified DESC
        LIMIT 1
        """.format(conditions=" AND ".join(conditions)),
        valeurs,
        as_dict=True,
    )
    if not rows:
        return None

    retenue = rows[0]
    return {
        "note_pct": flt(retenue.note_pct),
        "note_finale": flt(retenue.note_finale),
        "grade": retenue.grade or "",
        "point": flt(retenue.point),
        "est_rattrapage": retenue.type_dexamen == TYPE_RATTRAPAGE,
    }


# ---------------------------------------------------------------------- #
#  Calcul
# ---------------------------------------------------------------------- #
def calculer_ue_etudiant(student, teaching_unit_value, academic_year, semestre, filiere=None, niveau=None):
    """Calcule le résultat d'une UE pour un étudiant, **sans écrire**.

    Fonction pure : c'est elle qui alimente le PV d'UE. L'écriture est faite
    par ``calculer_resultat_ue``.

    Returns:
        dict | None: résultat complet, ou None si l'UE n'a aucune matière.
    """
    if not (student and teaching_unit_value and academic_year and semestre):
        return None

    matieres = get_matieres_ue(teaching_unit_value, academic_year, filiere, niveau)
    if not matieres:
        return None

    seuil = get_seuil_validation(get_student_cycle(student))
    niveau_id = _niveau_name(filiere, niveau)

    lignes = []
    poids_total = 0.0
    ponderee = 0.0
    credits_obtenus = 0.0
    manquantes = []
    sans_poids = []

    for matiere in matieres:
        note = _meilleure_note(
            student, matiere["teaching_unit"], academic_year, semestre, filiere, niveau_id
        )
        credits = flt(matiere["credits"])
        note_pct = note["note_pct"] if note else None

        lignes.append(
            {
                "teaching_unit": matiere["teaching_unit"],
                "code": matiere["code"],
                "intitule": matiere["intitule"],
                "credits": credits,
                "note_pct": note_pct,
                "note_finale": note["note_finale"] if note else None,
                "est_rattrapage": bool(note["est_rattrapage"]) if note else False,
                "valide": bool(note and note_pct >= seuil),
            }
        )

        if note is None:
            # Matière sans aucune note saisie : l'UE n'est pas calculable.
            manquantes.append(matiere["intitule"])
            continue

        # Une matière sans poids ne peut pas entrer dans une moyenne pondérée :
        # elle est exclue du calcul, et le commentaire le signale pour que la
        # grille soit corrigée plutôt que de laisser un PV faux en silence.
        if credits <= 0:
            sans_poids.append(matiere["intitule"])
            continue

        poids_total += credits
        ponderee += credits * note_pct
        if note_pct >= seuil:
            credits_obtenus += credits

    total_credits = round(sum(l["credits"] for l in lignes if l["credits"] > 0), 2)

    if manquantes:
        note_ue_pct = None
        commentaire = _("En attente — note manquante : {0}").format(", ".join(manquantes))
    elif poids_total <= 0:
        note_ue_pct = None
        commentaire = _(
            "Calcul impossible : aucun crédit renseigné pour les matières de cette UE."
        )
    else:
        note_ue_pct = round(ponderee / poids_total, 2)
        commentaire = None

    if sans_poids:
        avertissement = _(
            "Matière sans crédit, exclue de la moyenne : {0}"
        ).format(", ".join(sans_poids))
        commentaire = "{} — {}".format(commentaire, avertissement) if commentaire else avertissement

    # `point` reste un nombre (ou None) : les gabarits d'impression lui
    # appliquent un format « %.2f », qui échoue sur une chaîne vide.
    grade = mention = type_resultat = ""
    point = None
    capitalise = False
    if note_ue_pct is not None:
        info = get_grade_info(note_ue_pct, echelle=100) or {}
        grade = info.get("grade") or ""
        point = flt(info.get("point"))
        mention = info.get("mention") or ""
        type_resultat = info.get("type_resultat") or ""
        capitalise = bool(info.get("capitalise"))

    if note_ue_pct is None:
        statut = "En attente"
    else:
        statut = "Validé" if note_ue_pct >= seuil else "Non Validé"
    if statut != "Validé":
        capitalise = False

    return {
        "student": student,
        "teaching_unit_value": teaching_unit_value,
        "academic_year": academic_year,
        "semestre": semestre,
        "est_calculable": note_ue_pct is not None,
        "note_ue_pct": note_ue_pct,
        "note_ue_20": round(note_ue_pct * 20 / 100, 2) if note_ue_pct is not None else None,
        "grade": grade,
        "point": point,
        "mention": mention,
        "type_resultat": type_resultat,
        "capitalise": capitalise,
        "statut": statut,
        "seuil_validation": seuil,
        "n_matieres": len(lignes),
        "total_credits": total_credits,
        "credits_obtenus": credits_obtenus,
        "pct_validation": (
            round(credits_obtenus / total_credits * 100, 2) if total_credits else None
        ),
        "lignes": lignes,
        "commentaire": commentaire,
    }


def calculer_resultat_ue(student, teaching_unit_value, academic_year, semestre, filiere=None, niveau=None):
    """Calcule puis enregistre le résultat d'une UE (idempotent).

    Returns:
        Document | None: le `Resultat UE` enregistré, ou None si l'UE n'a
        aucune matière exploitable.
    """
    if not (student and teaching_unit_value and academic_year and semestre):
        return None

    resultat = calculer_ue_etudiant(
        student, teaching_unit_value, academic_year, semestre, filiere, niveau
    )
    if resultat is None:
        frappe.log_error(
            title="udshed: UE sans matière",
            message=_("Aucune matière rattachée à l'UE {0} pour l'année {1}.").format(
                teaching_unit_value, academic_year
            ),
        )
        return None

    existing = frappe.db.get_value(
        DOCTYPE,
        {
            "student": student,
            "teaching_unit_value": teaching_unit_value,
            "academic_year": academic_year,
        },
        "name",
    )
    doc = frappe.get_doc(DOCTYPE, existing) if existing else frappe.new_doc(DOCTYPE)

    doc.student = student
    doc.teaching_unit_value = teaching_unit_value
    doc.academic_year = academic_year
    doc.semestre = semestre
    # Les colonnes numériques de Frappe sont `NOT NULL DEFAULT 0` : une note
    # absente y resterait 0.0. Le drapeau porte la vérité, le statut et le PV
    # s'appuient dessus.
    doc.est_calculable = 1 if resultat["est_calculable"] else 0
    doc.note_ue_pct = resultat["note_ue_pct"]
    doc.note_ue_20 = resultat["note_ue_20"]
    doc.grade = resultat["grade"]
    doc.point = resultat["point"]
    doc.mention = resultat["mention"]
    doc.type_resultat = resultat["type_resultat"]
    doc.capitalise = resultat["capitalise"]
    doc.n_matieres = resultat["n_matieres"]
    doc.total_credits = resultat["total_credits"]
    doc.credits_obtenus = resultat["credits_obtenus"]
    doc.pct_validation = resultat["pct_validation"]
    doc.commentaire = resultat["commentaire"]

    doc.set("table_matieres", [])
    for ligne in resultat["lignes"]:
        doc.append(
            "table_matieres",
            {
                "teaching_unit": ligne["teaching_unit"],
                "code": ligne["code"],
                "intitule": ligne["intitule"],
                "credits": ligne["credits"],
                "note_pct": ligne["note_pct"],
                "note_finale": ligne["note_finale"],
                "est_rattrapage": 1 if ligne["est_rattrapage"] else 0,
                "valide": 1 if ligne["valide"] else 0,
            },
        )

    if existing:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)

    return doc


# ---------------------------------------------------------------------- #
#  Point d'entrée déclenché à l'enregistrement d'une note
# ---------------------------------------------------------------------- #
def recalculer_ue_depuis_note(teaching_unit, student, session_examen, filiere=None, niveau=None):
    """Recalcule l'UE d'un étudiant après la sauvegarde d'une de ses notes.

    Appelé depuis ``Session Examen Note.on_update`` : le résultat est donc
    disponible dès la saisie, sans attendre la publication de la session.
    """
    if not (teaching_unit and student):
        return None

    teaching_unit_value = get_ues_de_matiere(teaching_unit)
    if not teaching_unit_value:
        # Matière non rattachée à une UE (hors grille) : rien à calculer.
        return None

    contexte = frappe.db.get_value(
        "Session Examen", session_examen, ["academic_year", "semestre"], as_dict=True
    )
    if not contexte or not contexte.academic_year or not contexte.semestre:
        return None

    return calculer_resultat_ue(
        student,
        teaching_unit_value,
        contexte.academic_year,
        contexte.semestre,
        filiere=filiere,
        niveau=niveau,
    )


@frappe.whitelist()
def recalculer_ue(academic_year, filiere, niveau, semestre, teaching_unit_value, student=None):
    """Recalcule l'UE pour un étudiant ou pour toute la classe.

    Sert au bouton « Recalculer » du PV d'UE et à la reprise d'un lot de notes
    saisi avant la mise en place de ce calcul.
    """
    if student:
        cibles = [student]
    else:
        from udshed.api.saisie_notes import _get_etudiants

        cibles = []
        vus = set()
        for matiere in get_matieres_ue(teaching_unit_value, academic_year, filiere, niveau):
            for et in _get_etudiants(academic_year, filiere, niveau, matiere["teaching_unit"]):
                if et["student"] in vus:
                    continue
                vus.add(et["student"])
                cibles.append(et["student"])

    calcules = 0
    for cible in cibles:
        if calculer_resultat_ue(cible, teaching_unit_value, academic_year, semestre, filiere, niveau):
            calcules += 1
    return {"ues": calcules, "etudiants": len(cibles)}
