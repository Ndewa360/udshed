# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Moteur de calcul des notes (LMD) pour UDSHED.

La source de vérité de la configuration est le doctype « Grade Formula » :
plusieurs formules actives par cycle (Licence / BTS / Master) sont
autorisées, une par combinaison d'évaluations.

Règles métier LMD :
- Le calcul porte sur les cours / matières.
- Les crédits LMD sont séparés des pourcentages de calcul (jamais de
  multiplication d'une note par des crédits).
- La somme des pourcentages d'une formule est exactement 100 %.
- Une composante peut intégrer une autre évaluation (composition interne).
- La formule d'une note est sélectionnée automatiquement selon le cycle de
  l'étudiant et la combinaison d'évaluations effectivement renseignées
  (détection : CC + EXAM, CC + CCTP + EXAM, CC + EXAMTP + EXAM, ...).
"""

import math

import frappe
from frappe import _
from frappe.utils import flt

NOTE_MAX = 20

CYCLES = ["Licence", "BTS", "Master"]

SEUILS_DEFAUT = {"Licence": 50, "BTS": 50, "Master": 60}

# Grille officielle des grades et des points UDSHED (référence unique).
# (min /20, max /20, min %, max %, grade, point, mention)
# La capitalisation LMD est déduite : >= 10/20 -> capitalisé et transférable.
GRILLE_OFFICIELLE = [
    (16.00, 20.00, 80.00, 100.00, "A", 4.00,
     "Excellent / Très Honorable avec Félicitations du Jury"),
    (15.00, 15.99, 75.00, 79.99, "A-", 3.70, "Très Bien / Très Honorable"),
    (14.00, 14.99, 70.00, 74.99, "B+", 3.30, "Très Bien"),
    (13.00, 13.99, 65.00, 69.99, "B", 3.00, "Assez Bien"),
    (12.00, 12.99, 60.00, 64.99, "B-", 2.70, "Assez Bien"),
    (11.00, 11.99, 55.00, 59.99, "C+", 2.30, "Passable"),
    (10.00, 10.99, 50.00, 54.99, "C", 2.00, "Passable"),
    (9.00, 9.99, 45.00, 49.99, "C-", 1.70, "Insuffisant"),
    (8.00, 8.99, 40.00, 44.99, "D+", 1.30, "Insuffisant"),
    (7.00, 7.99, 35.00, 39.99, "D", 1.00, "Insuffisant"),
    (6.00, 6.99, 30.00, 34.99, "E", 0.00, "Échec"),
    (0.00, 5.99, 0.00, 29.99, "F", 0.00, "Échec"),
]

# Labels alignés avec les options existantes de « Note Formule Config »
# afin de rester compatibles avec les mappings déjà en place.
COMPOSANTES = [
    "Controle Continu(CC)",
    "Controle Continu Travaux Pratiques(CCTP)",
    "Examen",
    "Examen Travaux Pratiques(EXAMTP)",
    "Travaux Pratique (TP)",
    "Rapport",
    "Competence",
]

COMPOSANTES_PRINCIPALES = [
    "Controle Continu(CC)",
    "Controle Continu Travaux Pratiques(CCTP)",
    "Examen",
    "Examen Travaux Pratiques(EXAMTP)",
    "Travaux Pratique (TP)",
]

# Ordre canonique d'affichage des combinaisons d'évaluations. Toutes les
# combinaisons (configurées ou détectées) sont comparées sur cet ordre afin
# que « CC + CCTP + EXAMTP + EXAM » soit lisible et stable.
ORDRE_COMPOSANTES = [
    "Controle Continu(CC)",
    "Controle Continu Travaux Pratiques(CCTP)",
    "Examen",
    "Examen Travaux Pratiques(EXAMTP)",
    "Travaux Pratique (TP)",
    "Rapport",
    "Competence",
]


def _cle_tri(composante):
    """Clé de tri canonique d'un label de composante."""
    if composante in ORDRE_COMPOSANTES:
        return ORDRE_COMPOSANTES.index(composante)
    return len(ORDRE_COMPOSANTES) + ord((composante or "")[0] or "z")

# Correspondance type d'UE -> combinaison d'évaluations utilisée.
# La combinaison sert à sélectionner automatiquement la formule d'une note.
TYPE_UE_COMBINAISON = {
    "Sans TP": ["Controle Continu(CC)", "Examen"],
    "Avec TP": ["Controle Continu(CC)", "Examen", "Travaux Pratique (TP)"],
    "Stage SMSB": ["Examen", "Rapport"],
}

METHODES_CC = [
    "Moyenne arithmétique",
    "Moyenne des N meilleures notes",
]

METHODES_ARRONDI = [
    "Au plus proche",
    "Au supérieur",
    "À l'inférieur",
    "Sans arrondi",
]


# ---------------------------------------------------------------------- #
#  Cycle
# ---------------------------------------------------------------------- #
def get_student_cycle(student):
    """Retourne le cycle (Licence / BTS / Master) d'un étudiant.

    Args:
        student: Document Student ou nom de l'étudiant.

    Returns:
        str: cycle, avec repli sur Licence.
    """
    if not student:
        return "Licence"
    cycle = getattr(student, "cycle", None)
    if not cycle and isinstance(student, str):
        cycle = frappe.db.get_value("Student", student, "cycle")
    return cycle if cycle in CYCLES else "Licence"


# ---------------------------------------------------------------------- #
#  Combinaison d'évaluations
# ---------------------------------------------------------------------- #
def combinaison_formule(formula):
    """Combinaison canonique d'une formule = composantes principales (pourcentage > 0), triées.

    Exemple : [CC (40 %), Examen (60 %)] -> "Controle Continu(CC) + Examen"

    Args:
        formula (Document): Grade Formula

    Returns:
        str: combinaison canonique ("" si aucune composante active)
    """
    labels = sorted(
        (c.composante for c in (formula.get("components") or []) if (c.pourcentage or 0) > 0),
        key=_cle_tri,
    )
    return " + ".join(labels)


def combinaison_detectee(labels):
    """Combinaison canonique détectée à partir des composantes renseignées.

    Exemple : ["Examen", "Controle Continu(CC)", "Controle Continu Travaux Pratiques(CCTP)"]
    -> "Controle Continu(CC) + Controle Continu Travaux Pratiques(CCTP) + Examen"

    Args:
        labels (list[str]): labels des composantes effectivement renseignées

    Returns:
        str: combinaison canonique
    """
    labels = sorted({l for l in labels if l in COMPOSANTES}, key=_cle_tri)
    return " + ".join(labels)


def combinaison_type_ue(type_ue):
    """Combinaison d'évaluations attendue pour un type d'UE.

    Args:
        type_ue (str): "Sans TP", "Avec TP" ou "Stage SMSB"

    Returns:
        str: combinaison canonique (repli sur "Sans TP")
    """
    labels = TYPE_UE_COMBINAISON.get(type_ue)
    if labels is None:
        labels = TYPE_UE_COMBINAISON["Sans TP"]
    return " + ".join(sorted(labels, key=_cle_tri))


# ---------------------------------------------------------------------- #
#  Récupération de la formule
# ---------------------------------------------------------------------- #
def get_formules_cycle(cycle, active=None):
    """Noms des formules d'un cycle (optionnellement filtrées sur l'activation).

    Args:
        cycle (str): "Licence", "BTS" ou "Master"
        active (bool | None): None = toutes, True = actives, False = inactives

    Returns:
        list[str]: noms des formules
    """
    filters = {"cycle": cycle}
    if active is not None:
        filters["active"] = 1 if active else 0
    return frappe.get_all(
        "Grade Formula", filters=filters, order_by="creation asc", pluck="name"
    )


def get_formula(cycle, combinaison=None, active=True):
    """Récupère la formule d'un cycle, idéalement pour une combinaison donnée.

    La combinaison est comparée sur la forme canonique (composantes > 0 %
    triées), de sorte que l'ordre des composantes n'a pas d'importance.

    Args:
        cycle (str): "Licence", "BTS" ou "Master"
        combinaison (str, optional): combinaison canonique recherchée
        active (bool): ne considérer que les formules actives

    Returns:
        Document | None: formule correspondante
    """
    for name in get_formules_cycle(cycle, active=active):
        doc = frappe.get_doc("Grade Formula", name)
        if not combinaison or combinaison_formule(doc) == combinaison:
            return doc
    return None


def get_active_formula(cycle, combinaison=None):
    """Récupère la formule active d'un cycle (lève une erreur si absente).

    Args:
        cycle (str): "Licence", "BTS" ou "Master"
        combinaison (str, optional): combinaison d'évaluations recherchée

    Returns:
        Document: formule active
    """
    formula = get_formula(cycle, combinaison)
    if not formula:
        if combinaison:
            frappe.throw(
                _("Aucune formule active trouvée pour le cycle {0} et la combinaison "
                  "d'évaluations « {1} ». Vérifiez la configuration dans Grade Formula.").format(
                    cycle, combinaison
                )
            )
        frappe.throw(
            _("Aucune formule active trouvée pour le cycle {0}. "
              "Veuillez configurer une formule active dans Grade Formula.").format(cycle)
        )
    return formula


def get_seuil_validation(cycle):
    """Seuil de validation des UE (%) pour un cycle.

    Priorité : formule unique active du cycle -> Udshed Setting -> défaut LMD.
    Avec plusieurs formules actives par cycle, le seuil revient à la
    configuration globale (Udshed Setting) puis au défaut LMD.

    Args:
        cycle (str): "Licence", "BTS" ou "Master"

    Returns:
        float: seuil en pourcentage (0-100)
    """
    cycle = cycle if cycle in CYCLES else "Licence"
    formules = get_formules_cycle(cycle, active=True)
    if len(formules) == 1:
        formula = frappe.get_doc("Grade Formula", formules[0])
        if formula.seuil_validation is not None:
            return float(formula.seuil_validation)

    setting = frappe.get_single("Udshed Setting")
    if cycle == "Licence":
        return float(setting.seuil_validation_licence or 0) or SEUILS_DEFAUT["Licence"]
    if cycle == "BTS":
        return float(getattr(setting, "seuil_validation_bts", 0) or 0) or SEUILS_DEFAUT["BTS"]
    return float(setting.seuil_validation_master or 0) or SEUILS_DEFAUT["Master"]


# ---------------------------------------------------------------------- #
#  Moyenne CC
# ---------------------------------------------------------------------- #
def calculer_moyenne_cc(notes_cc, methode="Moyenne arithmétique", nombre_min=1):
    """Calcule la moyenne des Contrôles Continus selon la méthode choisie.

    Args:
        notes_cc (list): notes CC (float ou (pondération, note))
        methode (str): méthode de calcul
        nombre_min (int): nombre minimum de notes CC requises

    Returns:
        float: moyenne CC sur 20
    """
    if not notes_cc:
        return 0

    valeurs = []
    for item in notes_cc:
        if isinstance(item, (tuple, list)):
            valeurs.append(item)
        else:
            valeurs.append((1, item))
    valeurs = [(w, n) for w, n in valeurs if n is not None]

    if len(valeurs) < nombre_min:
        frappe.throw(
            _("Nombre insuffisant de notes CC ({0}/{1} requis).").format(
                len(valeurs), nombre_min
            )
        )

    if methode == "Moyenne arithmétique":
        return sum(n for _, n in valeurs) / len(valeurs)

    if methode == "Moyenne des N meilleures notes":
        n = min(nombre_min, len(valeurs))
        meilleures = sorted((n for _, n in valeurs), reverse=True)[:n]
        return sum(meilleures) / len(meilleures)

    frappe.throw(_("Méthode de calcul CC inconnue : {0}").format(methode))


# ---------------------------------------------------------------------- #
#  Arrondi
# ---------------------------------------------------------------------- #
def appliquer_arrondi(note, methode="Au plus proche"):
    """Applique la méthode d'arrondi configurée à 2 décimales.

    Args:
        note (float): note à arrondir
        methode (str): méthode d'arrondi

    Returns:
        float: note arrondie
    """
    if methode == "Au supérieur":
        return math.ceil(note * 100) / 100
    if methode == "À l'inférieur":
        return math.floor(note * 100) / 100
    return round(note, 2)


# ---------------------------------------------------------------------- #
#  Validations de la formule
# ---------------------------------------------------------------------- #
def valider_formule(formula):
    """Valide une formule (côté backend).

    Vérifie :
    - cycle valide ;
    - seuil UE entre 0 et 100 ;
    - au moins une composante active ;
    - aucun pourcentage négatif / supérieur à 100 ;
    - total général exactement 100 % ;
    - total interne de chaque composition exactement 100 % ;
    - aucune double comptabilisation d'une note.

    Args:
        formula (Document): Grade Formula

    Raises:
        frappe.ValidationError: si la formule est invalide.
    """
    if formula.cycle not in CYCLES:
        frappe.throw(_("Cycle invalide : {0}").format(formula.cycle))

    seuil = formula.seuil_validation
    if seuil is None or seuil < 0 or seuil > 100:
        frappe.throw(
            _("Le seuil de validation de l'UE doit être compris entre 0 et 100 %. "
              "(valeur actuelle : {0})").format(seuil)
        )

    components = list(formula.get("components") or [])
    if not components:
        frappe.throw(_("La formule doit contenir au moins une composante."))

    total = 0
    composantes_principales = set()
    for c in components:
        pct = c.pourcentage or 0
        if pct < 0 or pct > 100:
            frappe.throw(
                _("Le pourcentage de la composante <b>{0}</b> doit être entre 0 et 100 %.").format(
                    c.composante
                )
            )
        if c.composante not in COMPOSANTES:
            frappe.throw(_("Composante inconnue : {0}").format(c.composante))
        total += pct
        composantes_principales.add(c.composante)

    if abs(total - 100) > 0.001:
        frappe.throw(
            _("La somme des pourcentages de la formule doit être exactement 100 %. "
              "(total actuel : {0} %)").format(total)
        )

    if not any((c.pourcentage or 0) > 0 for c in components):
        frappe.throw(_("Au moins une composante doit avoir un pourcentage supérieur à 0."))

    # Composition interne
    par_parent = {}
    for r in formula.get("composition") or []:
        if r.composante_parent not in composantes_principales:
            frappe.throw(
                _("La composition de <b>{0}</b> concerne une composante non utilisée "
                  "dans la formule.").format(r.composante_parent)
            )
        if r.composante not in COMPOSANTES:
            frappe.throw(_("Composante inconnue dans la composition : {0}").format(r.composante))
        if r.pourcentage is None or r.pourcentage < 0 or r.pourcentage > 100:
            frappe.throw(
                _("Le pourcentage interne de <b>{0}</b> doit être entre 0 et 100 %.").format(
                    r.composante
                )
            )
        par_parent.setdefault(r.composante_parent, []).append(r)

    for parent, rows in par_parent.items():
        total_interne = sum(r.pourcentage or 0 for r in rows)
        if abs(total_interne - 100) > 0.001:
            frappe.throw(
                _("La composition interne de <b>{0}</b> doit totaliser exactement 100 %. "
                  "(total actuel : {1} %)").format(parent, total_interne)
            )
        sources = {r.composante for r in rows}
        interdites = composantes_principales - {parent}
        conflits = sources & interdites
        if conflits:
            frappe.throw(
                _("Double comptabilisation : la note <b>{0}</b> est déjà utilisée comme "
                  "composante principale de la formule et à l'intérieur de la composition "
                  "de <b>{1}</b>.").format(", ".join(sorted(conflits)), parent)
            )


def is_formule_complete(formula, notes):
    """Vrai si toutes les composantes actives de la formule sont renseignées.

    Une composante à 0 % n'est pas exigée.

    Args:
        formula (Document): Grade Formula
        notes (dict): valeurs des composantes (label -> note /20 | None)

    Returns:
        bool
    """
    for c in formula.get("components") or []:
        if not c.pourcentage:
            continue
        if notes.get(c.composante) is None:
            return False
    return True


# ---------------------------------------------------------------------- #
#  Résolution de la note
# ---------------------------------------------------------------------- #
def _valeur_composante(formula, composante, ctx):
    """Valeur /20 d'une composante, en appliquant sa composition interne éventuelle.

    Args:
        formula (Document): Grade Formula
        composante (str): label de la composante principale
        ctx (dict): valeurs brutes des composantes (label -> note /20)

    Returns:
        float: valeur de la composante sur 20
    """
    rows = [r for r in (formula.get("composition") or []) if r.composante_parent == composante]
    if rows:
        total = sum(r.pourcentage or 0 for r in rows)
        if total <= 0:
            return ctx.get(composante) or 0
        valeur = sum((ctx.get(r.composante) or 0) * (r.pourcentage or 0) for r in rows)
        return valeur / total
    return ctx.get(composante) or 0


def calculer_note_ue(ctx, formula):
    """Calcule la note finale d'un cours / matière selon la formule.

    Les composantes sont d'abord résolues (avec leurs compositions internes),
    puis combinées par leurs pourcentages. La note est sur 20.

    Args:
        ctx (dict): valeurs brutes des composantes (label -> note /20 | None)
        formula (Document): Grade Formula active

    Returns:
        tuple: (note_finale /20, note_pct %) ou (None, 0) si incomplet
    """
    note = 0.0
    for c in formula.get("components") or []:
        pct = c.pourcentage or 0
        if pct <= 0:
            continue
        valeur = _valeur_composante(formula, c.composante, ctx)
        if valeur is None:
            return None, 0
        note += valeur * pct / 100

    note_pct = round(note * 100 / NOTE_MAX, 2)
    note_finale = appliquer_arrondi(note, formula.methode_arrondi)
    return note_finale, note_pct


def est_valide(note_finale, cycle="Licence"):
    """Détermine si l'UE est validée selon le seuil du cycle.

    Args:
        note_finale (float): note finale /20
        cycle (str): "Licence", "BTS" ou "Master"

    Returns:
        bool: True si validée
    """
    note_pct = (note_finale / NOTE_MAX) * 100
    return note_pct >= get_seuil_validation(cycle)


# ---------------------------------------------------------------------- #
#  Grille des grades (Grade Config)
# ---------------------------------------------------------------------- #
def get_grille_grades():
    """Lignes de la grille des grades depuis Udshed Setting (source de vérité).

    Returns:
        list[Document]: lignes du tableau enfant « Grade Config »
    """
    setting = frappe.get_single("Udshed Setting")
    return list(setting.get("grille_grades") or [])


def _borne_min_20(ligne):
    """Borne minimale /20 d'une ligne de grille (repli sur l'ancien champ %).

    Args:
        ligne (Document): ligne de « Grade Config »

    Returns:
        float: note minimale sur 20
    """
    note_min_20 = ligne.get("note_min_20")
    if note_min_20 is not None:
        return float(note_min_20)
    # Données anciennes : seul le % était renseigné.
    note_min_pct = ligne.get("note_min_100")
    if note_min_pct is None:
        note_min_pct = ligne.get("note_min") or 0
    return float(note_min_pct) * NOTE_MAX / 100.0


def get_grade_scale():
    """Grille officielle triée (du grade le plus haut au plus bas).

    Vue normalisée partagée par tous les affichages (transcript, babillard,
    PDF...) afin qu'aucun module ne reconstruise sa propre lecture de la
    grille.

    Returns:
        list[dict]: [{
            "note_min_20": float, "note_max_20": float,
            "note_min_pct": float, "note_max_pct": float,
            "grade": str, "point": float, "mention": str,
        }, ...]
    """
    scale = []
    for ligne in get_grille_grades():
        note_max_20 = ligne.get("note_max_20")
        if note_max_20 is None:
            note_max_pct = ligne.get("note_max_100")
            if note_max_pct is None:
                note_max_pct = ligne.get("note_max") or 0
            note_max_20 = float(note_max_pct) * NOTE_MAX / 100.0

        note_min_pct = ligne.get("note_min_100")
        if note_min_pct is None:
            note_min_pct = _borne_min_20(ligne) * 100.0 / NOTE_MAX
        note_max_pct = ligne.get("note_max_100")
        if note_max_pct is None:
            note_max_pct = float(note_max_20) * 100.0 / NOTE_MAX

        scale.append({
            "note_min_20": _borne_min_20(ligne),
            "note_max_20": float(note_max_20),
            "note_min_pct": round(float(note_min_pct), 2),
            "note_max_pct": round(float(note_max_pct), 2),
            "grade": ligne.grade or "",
            "point": flt(ligne.point),
            "mention": ligne.mention or "",
        })
    scale.sort(key=lambda x: x["note_min_20"], reverse=True)
    return scale


def get_grade_info(note, echelle=20):
    """Détermine le grade d'une note à partir de la grille officielle.

    Règle unique de résolution (source : Udshed Setting › grille_grades) :
    la recherche se fait sur la note ramenée sur 20, arrondie à 2 décimales ;
    on retient la première tranche (triée de la plus haute à la plus basse)
    dont la borne minimale est atteinte. Le pourcentage n'est que la
    représentation équivalente de la note /20 et n'est jamais utilisé comme
    seconde règle.

    Args:
        note (float): note saisie (sur 20 par défaut, ou sur 100)
        echelle (int): échelle de la note passée (« 20 » ou « 100 »)

    Returns:
        dict | None: {
            "grade": str,
            "point": float,
            "mention": str,
            "type_resultat": str,
            "capitalise": bool,
            "note_20": float,
            "note_pct": float,
        } ou None si aucune tranche ne correspond.
    """
    if note is None:
        return None

    note_20 = round(float(note) * NOTE_MAX / 100.0, 2) if echelle == 100 else round(float(note), 2)
    note_pct = round(note_20 * 100.0 / NOTE_MAX, 2)

    for ligne in sorted(get_grille_grades(), key=_borne_min_20, reverse=True):
        if note_20 >= _borne_min_20(ligne):
            type_resultat = ligne.get("type_resultat") or ""
            return {
                "grade": ligne.grade,
                "point": flt(ligne.point),
                "mention": ligne.mention,
                "type_resultat": type_resultat,
                "capitalise": bool(type_resultat.lower().startswith("crédits capitalisés")),
                "note_20": note_20,
                "note_pct": note_pct,
            }
    return None


def determiner_statut_ue(note_finale, cycle="Licence"):
    """Statut complet d'une note d'UE : validation (seuil du cycle) + grade.

    Combine la validation selon le seuil de validation du cycle et les
    informations de la grille des grades (grade, point, mention, type de
    résultat).

    Args:
        note_finale (float): note finale de l'UE sur 20
        cycle (str): "Licence", "BTS" ou "Master"

    Returns:
        dict: {
            "valide": bool,
            "seuil_pct": float,
            "grade": str | None,
            "point": float | None,
            "mention": str | None,
            "type_resultat": str | None,
            "capitalise": bool,
        }
    """
    seuil = get_seuil_validation(cycle)
    valide = est_valide(note_finale, cycle)
    info = get_grade_info(note_finale, echelle=20) or {
        "grade": None,
        "point": None,
        "mention": None,
        "type_resultat": None,
        "capitalise": False,
    }
    return {
        "valide": valide,
        "seuil_pct": seuil,
        "grade": info["grade"],
        "point": info["point"],
        "mention": info["mention"],
        "type_resultat": info["type_resultat"],
        "capitalise": bool(info["capitalise"] and valide),
    }


# ---------------------------------------------------------------------- #
#  Aperçu lisible de la formule
# ---------------------------------------------------------------------- #
def rendre_apercu(formula):
    """Représentation lisible de la formule pour l'interface.

    Exemples :
        Combinaison : Controle Continu(CC) + Examen
        Note du cours = Controle Continu(CC) (40%) + Examen (60%)
        Controle Continu(CC) = Controle Continu(CC) (70%) + Travaux Pratique (TP) (30%)

    Args:
        formula (Document): Grade Formula

    Returns:
        str: aperçu multi-lignes
    """
    lignes = []
    combinaison = combinaison_formule(formula)
    if combinaison:
        lignes.append("Combinaison : {0}".format(combinaison))
    principales = [c for c in (formula.get("components") or []) if c.pourcentage]
    parties = ["{0} ({1}%)".format(c.composante, int(c.pourcentage)) for c in principales]
    lignes.append("Note du cours = " + " + ".join(parties) if parties else "Aucune composante")

    par_parent = {}
    for r in formula.get("composition") or []:
        par_parent.setdefault(r.composante_parent, []).append(r)

    for parent in [c.composante for c in principales]:
        rows = par_parent.get(parent) or []
        if not rows:
            continue
        internes = ["{0} ({1}%)".format(r.composante, int(r.pourcentage)) for r in rows]
        lignes.append("{0} = {1}".format(parent, " + ".join(internes)))

    return "\n".join(lignes)
