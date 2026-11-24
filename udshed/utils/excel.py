"""Classeur Excel à plusieurs onglets, indépendant de la version de Frappe.

`frappe.utils.xlsxutils.make_xlsx(..., wb=...)` n'est pas stable d'une version
à l'autre : selon la version, il attend un classeur openpyxl (`create_sheet`)
ou xlsxwriter (`add_worksheet`), et insère les onglets en tête ou à la fin.
Un export écrit pour l'une plantait sur l'autre en production
(« 'Workbook' object has no attribute 'add_worksheet' »). On écrit donc le
classeur directement avec openpyxl.
"""

from datetime import date, datetime
from io import BytesIO
import re

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

# Caractères interdits dans un nom d'onglet ; 31 caractères au plus.
_TITRE_INVALIDE = re.compile(r"[\\/*?:\[\]]")
# Caractères de contrôle refusés par openpyxl dans une cellule.
_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _valeur(v):
	if v is None:
		return ""
	if isinstance(v, (int, float, date, datetime)) and not isinstance(v, bool):
		return v
	if isinstance(v, bool):
		return "Oui" if v else "Non"
	return _CONTROLE.sub("", str(v))


def classeur_xlsx(feuilles):
	"""Octets d'un .xlsx.

	`feuilles` : liste de (lignes, nom_onglet, largeurs_colonnes), dans l'ordre
	des onglets. La première ligne de chaque onglet est l'en-tête (en gras).
	"""
	wb = Workbook()
	wb.remove(wb.active)
	gras = Font(bold=True)
	for lignes, nom, largeurs in feuilles:
		ws = wb.create_sheet(_TITRE_INVALIDE.sub(" ", nom)[:31])
		for i, largeur in enumerate(largeurs or []):
			if largeur:
				ws.column_dimensions[get_column_letter(i + 1)].width = largeur
		for n, ligne in enumerate(lignes):
			ws.append([_valeur(v) for v in ligne])
			if n == 0:
				for cellule in ws[1]:
					cellule.font = gras
		if lignes:
			ws.freeze_panes = "A2"
	flux = BytesIO()
	wb.save(flux)
	return flux.getvalue()
