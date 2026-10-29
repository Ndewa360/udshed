import frappe


def execute():
    """Réaligne le code d'anonymat des copies sur sa fiche d'anonymat.

    ``Copie Examen.code_anonymat`` dupliquait le code porté par la fiche
    d'anonymat. Les deux champs étant modifiables, ils ont pu diverger : la
    fiche d'anonymat et la fiche de report affichaient alors deux numéros
    différents pour un même étudiant, et la levée d'anonymat perdait les notes
    (jointure faite sur le code).

    La fiche d'anonymat fait désormais foi : ``Copie Examen.validate`` et
    ``Fiche Report.validate`` réalignent le code à chaque enregistrement. Ce
    patch rattrape les documents déjà enregistrés.
    """
    copies = frappe.db.sql(
        """
        select c.name, c.code_anonymat as copie_code, a.code_anonymat as fiche_code
        from `tabCopie Examen` c
        inner join `tabExamen Anonymat` a on a.name = c.examen_anonymat
        where ifnull(c.code_anonymat, '') != ifnull(a.code_anonymat, '')
        """,
        as_dict=True,
    )
    for copie in copies:
        frappe.db.set_value(
            "Copie Examen", copie.name, "code_anonymat", copie.fiche_code
        )

    if copies:
        frappe.logger("udshed").info(
            "Patches: code d'anonymat réaligné sur {0} copie(s).".format(len(copies))
        )

    _aligner_fiche_report()


def _aligner_fiche_report():
    """Réaligne le code d'anonymat des fiches de report sur leur fiche.

    Même cause que pour les copies : ``Fiche Report.code_anonymat`` dupliquait
    un code qui peut diverger de celui de la fiche d'anonymat. Le champ est
    désormais recopié par ``Fiche Report.validate``.
    """
    fiches = frappe.db.sql(
        """
        select f.name, a.code_anonymat as fiche_code
        from `tabFiche Report` f
        inner join `tabExamen Anonymat` a on a.name = f.examen_anonymat
        where ifnull(f.code_anonymat, '') != ifnull(a.code_anonymat, '')
        """,
        as_dict=True,
    )
    for fiche in fiches:
        frappe.db.set_value(
            "Fiche Report", fiche.name, "code_anonymat", fiche.fiche_code
        )

    if fiches:
        frappe.logger("udshed").info(
            "Patches: code d'anonymat réaligné sur {0} fiche(s) de report.".format(
                len(fiches)
            )
        )
