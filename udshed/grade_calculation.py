import frappe
import math


def get_active_formula(cycle):
    """Récupère la formule active pour un cycle donné.

    Args:
        cycle (str): "Licence" ou "Master"

    Returns:
        dict: La formule active (Grade Formula) ou None
    """
    name = frappe.db.get_value(
        "Grade Formula",
        {"cycle": cycle, "active": 1},
        "name"
    )
    if not name:
        frappe.throw(
            f"Aucune formule active trouvée pour le cycle {cycle}. "
            "Veuillez configurer une formule active dans Grade Formula."
        )
    return frappe.get_doc("Grade Formula", name)


def calculer_moyenne_cc(notes_cc, methode="Moyenne arithmétique", nombre_min=1, pondérations=None):
    """Calcule la moyenne des Contrôles Continus selon la méthode choisie.

    Args:
        notes_cc (list[float]): Liste des notes de CC
        methode (str): Méthode de calcul
        nombre_min (int): Nombre minimum de CC requis
        pondérations (list[float], optional): Poids pour la moyenne pondérée

    Returns:
        float: Moyenne des CC calculée, ou 0 si insuffisant
    """
    if not notes_cc:
        return 0

    notes_valides = [n for n in notes_cc if n is not None]

    if len(notes_valides) < nombre_min:
        frappe.throw(
            f"Nombre insuffisant de notes CC ({len(notes_valides)}/{nombre_min} requis)."
        )

    if methode == "Moyenne arithmétique":
        return sum(notes_valides) / len(notes_valides)

    elif methode == "Moyenne des N meilleures notes":
        n = min(nombre_min, len(notes_valides))
        meilleures = sorted(notes_valides, reverse=True)[:n]
        return sum(meilleures) / n

    elif methode == "Moyenne pondérée":
        if not pondérations or len(pondérations) != len(notes_valides):
            frappe.throw(
                "Le nombre de pondérations doit correspondre au nombre de notes CC "
                "pour le calcul de la moyenne pondérée."
            )
        total_pondere = sum(n * p for n, p in zip(notes_valides, pondérations))
        total_poids = sum(pondérations)
        if total_poids == 0:
            return 0
        return total_pondere / total_poids

    else:
        frappe.throw(f"Méthode de calcul CC inconnue : {methode}")


def calculer_note_finale_ue(
    note_cc,
    note_examen,
    notes_complementaires=None,
    formula=None
):
    """Calcule la note finale d'une UE selon la formule.

    La note est calculée sur 20. Les composantes sont d'abord calculées
    en pourcentage, puis converties sur 20.

    Args:
        note_cc (float): Note de CC sur 20
        note_examen (float): Note d'examen sur 20
        notes_complementaires (dict, optional): Dict {nom_composante: note_sur_20}
        formula (Document): Document Grade Formula actif

    Returns:
        float: Note finale sur 20
    """
    if formula is None:
        formula = get_active_formula("Licence")

    note_cc = note_cc or 0
    note_examen = note_examen or 0
    notes_complementaires = notes_complementaires or {}

    poids_cc = (formula.poids_cc or 0) / 100
    poids_examen = (formula.poids_examen or 0) / 100

    contribution_cc = (note_cc / 20) * poids_cc * 100
    contribution_examen = (note_examen / 20) * poids_examen * 100

    contribution_complementaire = 0
    for comp in formula.composantes_supplementaires:
        note_comp = notes_complementaires.get(comp.nom, 0)
        contribution = (note_comp / 20) * (comp.poids / 100) * 100
        contribution_complementaire += contribution

    total_pct = contribution_cc + contribution_examen + contribution_complementaire
    note_sur_20 = total_pct / 100 * 20

    return appliquer_arrondi(note_sur_20, formula.methode_arrondi)


def appliquer_arrondi(note, methode="Au plus proche"):
    """Applique la méthode d'arrondi configurée.

    Args:
        note (float): Note à arrondir
        methode (str): Méthode d'arrondi

    Returns:
        float: Note arrondie à 2 décimales
    """
    if methode == "Sans arrondi":
        return round(note, 2)

    elif methode == "Au plus proche":
        return round(note, 2)

    elif methode == "Au supérieur":
        return math.ceil(note * 100) / 100

    elif methode == "À l'inférieur":
        return math.floor(note * 100) / 100

    else:
        return round(note, 2)


def est_valide(note_finale, cycle="Licence"):
    """Détermine si l'UE est validée selon le seuil du cycle.

    Args:
        note_finale (float): Note finale sur 20
        cycle (str): "Licence" ou "Master"

    Returns:
        bool: True si validée, False sinon
    """
    note_pct = (note_finale / 20) * 100
    formula = get_active_formula(cycle)
    seuil = formula.seuil_validation
    return note_pct >= seuil
