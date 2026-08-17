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
  l'étudiant et la combinaison d'évaluations de son type d'UE.
"""

import math

import frappe
from frappe import _

NOTE_MAX = 20

CYCLES = ["Licence", "BTS", "Master"]

SEUILS_DEFAUT = {"Licence": 50, "BTS": 50, "Master": 60}

# Labels alignés avec les options existantes de « Note Formule Config »
# afin de rester compatibles avec les mappings déjà en place.
COMPOSANTES = [
    "Controle Continu(CC)",
    "Examen",
    "Travaux Pratique (TP)",
    "Rapport",
    "Competence",
]

COMPOSANTES_PRINCIPALES = [
    "Controle Continu(CC)",
    "Examen",
    "Travaux Pratique (TP)",
]

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
    "Moyenne pondérée",
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
        c.composante
        for c in (formula.get("components") or [])
        if (c.pourcentage or 0) > 0
    )
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
    return " + ".join(sorted(labels))


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
def calculer_moyenne_cc(notes_cc, methode="Moyenne arithmétique", nombre_min=1, pondérations=None):
    """Calcule la moyenne des Contrôles Continus selon la méthode choisie.

    Les pondérations ne sont pas des crédits LMD : ce sont uniquement des
    poids de calcul pour les évaluations CC.

    Args:
        notes_cc (list): notes CC (float ou (pondération, note))
        methode (str): méthode de calcul
        nombre_min (int): nombre minimum de notes CC requises
        pondérations (list, optional): poids pour la moyenne pondérée

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

    if methode == "Moyenne pondérée":
        if pondérations is not None:
            if len(pondérations) != len(valeurs):
                frappe.throw(
                    _("Le nombre de pondérations doit correspondre au nombre de notes CC "
                      "pour le calcul de la moyenne pondérée.")
                )
            total_pondere = sum(n * p for (_, n), p in zip(valeurs, pondérations))
            total_poids = sum(pondérations)
        else:
            total_pondere = sum(w * n for w, n in valeurs)
            total_poids = sum(w for w, _ in valeurs)
        if total_poids == 0:
            return 0
        return total_pondere / total_poids

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


def _bornes_grade(ligne):
    """Bornes (min, max) d'une ligne de grille, sur l'échelle 100.

    Privilégie les nouvelles colonnes explicites (note_min_100 / note_max_100)
    et retombe sur les anciens champs « note_min / note_max » pour la
    compatibilité avec les données existantes.

    Args:
        ligne (Document): ligne de « Grade Config »

    Returns:
        tuple: (note_min_100, note_max_100)
    """
    note_min = ligne.get("note_min_100")
    if note_min is None:
        note_min = ligne.get("note_min") or 0
    note_max = ligne.get("note_max_100")
    if note_max is None:
        note_max = ligne.get("note_max") or 0
    return float(note_min), float(note_max)


def get_grade_info(note, echelle=20):
    """Détermine automatiquement le grade d'une note à partir de la grille.

    Retourne le grade, le point pondéré, la mention et le type de résultat
    (capitalisation des crédits) correspondant à la note.

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
        } ou None si aucune ligne ne correspond.
    """
    if note is None:
        return None
    note_pct = (note / NOTE_MAX) * 100 if echelle == 20 else float(note)

    for ligne in sorted(get_grille_grades(), key=lambda l: _bornes_grade(l)[0], reverse=True):
        note_min, note_max = _bornes_grade(ligne)
        if note_min <= note_pct <= note_max:
            type_resultat = ligne.get("type_resultat") or ""
            return {
                "grade": ligne.grade,
                "point": ligne.point,
                "mention": ligne.mention,
                "type_resultat": type_resultat,
                "capitalise": bool(type_resultat.lower().startswith("crédits capitalisés")),
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
