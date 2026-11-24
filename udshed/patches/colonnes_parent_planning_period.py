"""Ajoute les colonnes de table enfant manquantes à `tabPlanning Period`.

« Planning Period » est devenu une table enfant (de Calendar Planing) après
la création initiale de sa table sur certains sites. Frappe n'ajoute pas
rétroactivement `parent`, `parentfield` et `parenttype` lors d'une telle
conversion : l'insertion d'un calendrier avec ses périodes échouait alors
(« Unknown column 'parent' »). Idempotent : ne fait rien si tout est présent.
"""

import frappe

COLONNES_ENFANT = ("parent", "parentfield", "parenttype")


def execute():
	if not frappe.db.table_exists("Planning Period"):
		return
	existantes = set(frappe.db.get_table_columns("Planning Period"))
	manquantes = [c for c in COLONNES_ENFANT if c not in existantes]
	if not manquantes:
		return

	ajouts = ", ".join(f"ADD COLUMN `{c}` varchar(140)" for c in manquantes)
	frappe.db.sql_ddl(f"ALTER TABLE `tabPlanning Period` {ajouts}")
	if "parent" in manquantes:
		frappe.db.sql_ddl("ALTER TABLE `tabPlanning Period` ADD INDEX `parent` (`parent`)")
