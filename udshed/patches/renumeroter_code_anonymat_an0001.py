import frappe

from udshed.api.examen_anonymat import (
    LARGEUR_NUMERO_ANONYMAT,
    PREFIXE_CODE_ANONYMAT,
)


def execute():
    """Renumérote les codes d'anonymat au format unique AN0001, AN0002, …

    Les codes étaient générés aléatoirement sur 6 caractères (ex. ``XRTUSD``),
    format supprimé : ils étaient longs, peu lisibles, et surtout hors du
    format attendu sur les fiches de report et les copies.

    La numérotation devient séquentielle et globale à l'application. Chaque
    fiche d'anonymat reçoit le prochain numéro, ce qui préserve la propriété
    essentielle : un même étudiant porte des codes **différents** d'une matière
    à l'autre, donc ses copies ne peuvent pas être corrélées entre matières.

    Les fiches sont réordonnées par ordre de création pour que la numérotation
    reste stable et lisible. Les copies et fiches de report liées sont
    réalignées par leur contrôleur (`validate`), qui recopie le code de la
    fiche d'anonymat.
    """
    fiches = frappe.db.sql(
        """
        select name
        from `tabExamen Anonymat`
        order by creation asc, name asc
        """
    )
    total = len(fiches)
    renumerotes = 0

    # Deux passes : les codes sont d'abord placés sous un préfixe temporaire
    # unique, puis renumérotés définitivement. Sans cette précaution, affecter
    # AN0001 à une fiche alors qu'une autre le porte déjà violerait la
    # contrainte d'unicité. « TM » + 4 chiffres ne peut pas entrer en conflit
    # avec les anciens formats (alphabet sans « 0 », ou AN + 3 chiffres).
    for numero, (fiche,) in enumerate(fiches, start=1):
        frappe.db.set_value(
            "Examen Anonymat",
            fiche,
            "code_anonymat",
            "TM{0:04d}".format(numero),
            update_modified=False,
        )
    for numero, (fiche,) in enumerate(fiches, start=1):
        frappe.db.set_value(
            "Examen Anonymat",
            fiche,
            "code_anonymat",
            "{0}{1:0{2}d}".format(
                PREFIXE_CODE_ANONYMAT, numero, LARGEUR_NUMERO_ANONYMAT
            ),
            update_modified=False,
        )
        renumerotes += 1

    if renumerotes:
        frappe.logger("udshed").info(
            "Patches: {0} code(s) d'anonymat renuméroté(s) au format {1}0001…".format(
                renumerotes, PREFIXE_CODE_ANONYMAT
            )
        )

    # Les copies et fiches de report recopient le code de leur fiche
    # d'anonymat à l'enregistrement ; on les réaligne explicitement.
    for doctype, jointure in (
        ("Copie Examen", "examen_anonymat"),
        ("Fiche Report", "examen_anonymat"),
    ):
        frappe.db.sql(
            """
            update `tab{0}` t
            inner join `tabExamen Anonymat` a on a.name = t.{1}
            set t.code_anonymat = a.code_anonymat
            where ifnull(t.code_anonymat, '') != ifnull(a.code_anonymat, '')
            """.format(doctype, jointure)
        )

    # Contrôle : plus aucun code hors format ne doit subsister. On réutilise le
    # motif du module applicatif plutôt qu'une regexp SQL, afin que le contrôle
    # de migration et celui de `ExamenAnonymat.validate` ne puissent pas diverger.
    from udshed.api.examen_anonymat import MOTIF_CODE_ANONYMAT

    reste = [
        (fiche,)
        for (fiche,) in frappe.db.sql("select name from `tabExamen Anonymat`")
        if not MOTIF_CODE_ANONYMAT.match(
            frappe.db.get_value("Examen Anonymat", fiche, "code_anonymat") or ""
        )
    ]
    reste = len(reste)
    if reste:
        frappe.throw(
            "Migration du code d'anonymat : {0} fiche(s) portent encore un code "
            "hors format AN0001.".format(reste)
        )

    frappe.logger("udshed").info(
        "Patches: code d'anonymat — {0} fiche(s) vérifiée(s), toutes au format "
        "AN0001.".format(total)
    )
