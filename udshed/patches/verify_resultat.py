import frappe


def execute():
    from udshed.api.resultat_academique import (
        calculer_resultat_session,
        calculer_resultat_semestre,
        calculer_resultat_annee,
        generer_classe_resultat,
    )
    print("4 APIs importees OK")
