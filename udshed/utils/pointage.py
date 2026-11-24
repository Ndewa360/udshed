"""Pointage des séances (Planning Item).

Règle
  - Une séance programmée est « Non fait ».
  - Chaque dimanche à 23 h (tâche planifiée), toutes les séances de la semaine
    (lundi → dimanche) encore « Non fait » passent à « Fait »,
    SAUF celles dont le statut a été fixé à la main (pointage_manuel) :
    une séance déclarée « Non fait » par un utilisateur le reste.
  - Les séances annulées ne sont jamais touchées.
  - Rattrapage : une semaine passée non traitée (serveur arrêté le dimanche)
    est traitée au passage suivant.

Statut « automatique » (choix « Planifiée » dans l'interface) : la séance
redevient gérée par le pointage du dimanche ; si sa semaine est déjà
écoulée, elle est directement « Fait ».
"""

from datetime import datetime, timedelta

import frappe
from frappe.utils import getdate

STATUT_AUTO = "auto"
STATUTS = ("Non fait", "Fait", "Annulée")


def debut_semaine(jour=None):
	jour = getdate(jour)
	return jour - timedelta(days=jour.weekday())


def statut_automatique(jour_seance, aujourd_hui=None):
	"""Statut d'une séance laissée au pointage automatique."""
	return "Fait" if getdate(jour_seance) < debut_semaine(aujourd_hui) else "Non fait"


def pointer_semaine(aujourd_hui=None):
	"""Passe à « Fait » les séances de la semaine (et des semaines passées non
	traitées) restées « Non fait » sans statut fixé à la main.

	Retourne le nombre de séances pointées.
	"""
	fin = debut_semaine(aujourd_hui) + timedelta(days=7)  # lundi suivant, exclu
	filtre_manuel = (
		"AND IFNULL(pointage_manuel, 0) = 0"
		if frappe.db.has_column("Planning Item", "pointage_manuel")
		else ""
	)
	noms = frappe.db.sql_list(
		f"""
		SELECT name FROM `tabPlanning Item`
		WHERE IFNULL(status, 'Non fait') = 'Non fait' AND date < %s {filtre_manuel}
		""",
		(datetime.combine(fin, datetime.min.time()),),
	)
	if noms:
		frappe.db.sql(
			"UPDATE `tabPlanning Item` SET status = 'Fait', modified = NOW() WHERE name IN %s",
			(tuple(noms),),
		)
	return len(noms)


def tache_dimanche():
	"""Tâche planifiée (dimanche 23 h, cf. hooks.scheduler_events)."""
	nombre = pointer_semaine()
	frappe.db.commit()
	frappe.logger("udshed").info(f"Pointage automatique : {nombre} séance(s) passée(s) à « Fait ».")
	return nombre
