"""Pointage des séances : les séances FUTURES ne peuvent pas être « Fait ».

Le statut d'une séance valait « Fait » par défaut : toute séance planifiée,
même future, était considérée comme réalisée. Le défaut est désormais
« Non fait » ; ce patch remet en « Non fait » les séances à venir déjà
enregistrées comme faites. Les séances passées restent « Fait » (hypothèse la
plus fidèle à l'historique). Idempotent.
"""

import frappe
from frappe.utils import add_days, getdate


def execute():
	demain = add_days(getdate(), 1)
	frappe.db.sql(
		"""
		UPDATE `tabPlanning Item`
		SET status = 'Non fait'
		WHERE status = 'Fait' AND date >= %s
		""",
		(demain,),
	)
