"""Version Word (.docx) des documents.

Deux sources, au choix du modèle :
  - un modèle Word déposé sur le modèle (champ « Modèle Word ») : rempli avec docxtpl
    (mêmes variables que l'éditeur : {{ etudiant.nom_complet }}, {{ vacations.net }}…,
    tableaux : {%tr for l in vacations.lignes %} … {%tr endfor %}) ;
  - sinon, un document construit depuis le modèle dessiné : les éléments sont repris dans
    l'ordre de lecture (haut → bas, gauche → droite), avec leurs styles, images et tableaux.

`modele_vierge()` produit ce même document SANS remplir les variables : c'est le modèle
Word par défaut, à télécharger, retoucher dans Word puis redéposer sur le modèle.
"""

import base64
import io
import json

import frappe
from frappe.utils import flt

from udshed.utils import actes as moteur

BANDE_MM = 3.5  # éléments dont le haut est à moins de 3,5 mm : même ligne


def _docx():
	from docx import Document
	from docx.enum.table import WD_TABLE_ALIGNMENT  # noqa: F401
	from docx.enum.text import WD_ALIGN_PARAGRAPH
	from docx.shared import Mm, Pt, RGBColor

	return Document, WD_ALIGN_PARAGRAPH, Mm, Pt, RGBColor


def _image_bytes(el, ctx, modele, sujet, signer):
	"""Octets PNG/JPEG d'un élément image, ou None."""
	t = el.get("type")
	uri = ""
	if t == "image":
		uri = moteur.data_uri(el.get("src"))
	elif t == "logo":
		from udshed.api.school_setting import get_logo_data_uri

		uri = get_logo_data_uri()
	elif t == "photo" and (modele.get("sujet") or moteur.SUJET_ETUDIANT) == moteur.SUJET_ETUDIANT and sujet:
		uri = moteur.data_uri(frappe.db.get_value("Student", sujet, "photo"))
	elif t == "qr" and ctx:
		uri = moteur.qr_data_uri(ctx["acte"].lien_verification)
	elif t in ("signature", "cachet") and signer:
		uri = moteur.data_uri(modele.image_signature if t == "signature" else modele.image_cachet)
	if not uri or "," not in uri:
		return None
	try:
		return base64.b64decode(uri.split(",", 1)[1])
	except Exception:
		return None


def _styler(run, el, Pt, RGBColor):
	run.font.size = Pt(flt(el.get("taille")) or 11)
	run.bold = bool(el.get("gras"))
	run.italic = bool(el.get("italique"))
	couleur = (el.get("couleur") or "").lstrip("#")
	if len(couleur) == 6:
		try:
			run.font.color.rgb = RGBColor.from_string(couleur.upper())
		except Exception:
			pass
	if el.get("police") == "serif":
		run.font.name = "Times New Roman"
	elif el.get("police") == "monospace":
		run.font.name = "Courier New"


def _texte(el, ctx, gabarit):
	contenu = el.get("contenu") or ""
	if gabarit or ctx is None:
		return contenu
	try:
		return frappe.render_template(contenu, ctx)
	except Exception:
		return contenu


def _paragraphe(conteneur):
	"""Nouveau paragraphe ; dans une cellule encore vide, réutilise son paragraphe initial."""
	if getattr(conteneur, "_tc", None) is not None and conteneur.paragraphs:
		dernier = conteneur.paragraphs[-1]
		if not dernier.runs and not dernier.text:
			return dernier
	return conteneur.add_paragraph()


def _remplir_bloc(conteneur, el, ctx, modele, sujet, signer, gabarit, outils):
	"""Écrit un élément dans `conteneur` (document ou cellule)."""
	_Document, ALIGN, Mm, Pt, RGBColor = outils
	t = el.get("type")
	alignements = {"center": ALIGN.CENTER, "right": ALIGN.RIGHT, "justify": ALIGN.JUSTIFY}
	if t == "texte":
		for ligne in _texte(el, ctx, gabarit).split("\n"):
			p = _paragraphe(conteneur)
			p.alignment = alignements.get(el.get("align"), ALIGN.LEFT)
			p.paragraph_format.space_after = Pt(2)
			_styler(p.add_run(ligne), el, Pt, RGBColor)
	elif t in ("image", "logo", "photo", "qr", "signature", "cachet"):
		octets = None if gabarit and t in ("photo", "qr") else _image_bytes(el, ctx, modele, sujet, signer or gabarit)
		p = _paragraphe(conteneur)
		p.alignment = alignements.get(el.get("align"), ALIGN.LEFT)
		if octets:
			try:
				p.add_run().add_picture(io.BytesIO(octets), width=Mm(max(5, min(flt(el.get("w")) or 25, 170))))
			except Exception:
				pass
		elif gabarit and t in ("photo", "qr"):
			p.add_run("[" + ("Photo" if t == "photo" else "QR code") + "]").italic = True
	elif t in moteur.TABLEAUX:
		_tableau(conteneur, t, ctx, sujet, gabarit, el, outils)
		if el.get("texte_apres"):
			_remplir_bloc(conteneur, {"type": "texte", "contenu": el["texte_apres"], "taille": el.get("taille_apres") or 10},
						  ctx, modele, sujet, signer, gabarit, outils)
	elif t == "cadre" and flt(el.get("h")) <= 1.5:
		p = conteneur.add_paragraph()
		p.add_run("_" * 60).font.size = Pt(6)


def _tableau(conteneur, t, ctx, sujet, gabarit, el, outils):
	_Document, _ALIGN, _Mm, Pt, _RGB = outils
	entetes, cles, source = moteur.colonnes_tableau(t)
	table = conteneur.add_table(rows=1, cols=len(entetes))
	table.style = "Table Grid"
	for i, h in enumerate(entetes):
		cell = table.rows[0].cells[i]
		cell.text = ""
		run = cell.paragraphs[0].add_run(h)
		run.bold = True
		run.font.size = Pt(flt(el.get("taille")) or 8)
	if gabarit:
		# Boucle docxtpl : le modèle vierge reste remplissable une fois redéposé.
		ligne = table.add_row().cells
		ligne[0].text = "{%tr for l in " + source + " %}"
		ligne = table.add_row().cells
		for i, cle in enumerate(cles):
			ligne[i].text = "{{ l." + cle + " }}"
		ligne = table.add_row().cells
		ligne[0].text = "{%tr endfor %}"
		return
	for donnee in moteur.lignes_tableau(t, ctx, sujet):
		cells = table.add_row().cells
		for i, cle in enumerate(cles):
			cells[i].text = ""
			run = cells[i].paragraphs[0].add_run(str(donnee.get(cle, "") if donnee.get(cle) is not None else ""))
			run.font.size = Pt(flt(el.get("taille")) or 8)
			if donnee.get("_gras"):
				run.bold = True


def _construire(modele, sujet, ctx, signer, gabarit):
	outils = _docx()
	Document, _ALIGN, Mm, _Pt, _RGB = outils
	largeur, hauteur = moteur.FORMATS.get(modele.format, moteur.FORMATS["A4 portrait"])
	doc = Document()
	section = doc.sections[0]
	section.page_width, section.page_height = Mm(largeur), Mm(hauteur)
	marge = 4 if largeur < 100 else 15
	section.left_margin = section.right_margin = section.top_margin = section.bottom_margin = Mm(marge)
	layout = json.loads(modele.layout or "{}") if isinstance(modele.layout, str) else (modele.layout or {})
	elements = [e for e in (layout.get("elements") or []) if not (e.get("type") == "cadre" and flt(e.get("h")) > 1.5)]
	elements.sort(key=lambda e: (flt(e.get("y")), flt(e.get("x"))))

	# Regroupe par bandes horizontales : plusieurs éléments côte à côte → tableau sans bordure.
	bandes, courante, haut = [], [], None
	for el in elements:
		if haut is None or flt(el.get("y")) - haut <= BANDE_MM:
			courante.append(el)
			haut = flt(el.get("y")) if haut is None else haut
		else:
			bandes.append(courante)
			courante, haut = [el], flt(el.get("y"))
	if courante:
		bandes.append(courante)

	for bande in bandes:
		bande.sort(key=lambda e: flt(e.get("x")))
		if len(bande) == 1 or any(e.get("type") in moteur.TABLEAUX for e in bande):
			for el in bande:
				_remplir_bloc(doc, el, ctx, modele, sujet, signer, gabarit, outils)
			continue
		table = doc.add_table(rows=1, cols=len(bande))
		for i, el in enumerate(bande):
			cell = table.rows[0].cells[i]
			cell.width = Mm(max(10, flt(el.get("w")) or 40))
			_remplir_bloc(cell, el, ctx, modele, sujet, signer, gabarit, outils)
	out = io.BytesIO()
	doc.save(out)
	return out.getvalue()


def _en_dict(valeur):
	if isinstance(valeur, dict):
		return {k: _en_dict(v) for k, v in valeur.items()}
	if isinstance(valeur, list):
		return [_en_dict(v) for v in valeur]
	return valeur


def docx(modele, sujet, acte=None, signer=None, params=None):
	"""Document Word rempli (modèle Word déposé, sinon construit depuis le modèle dessiné)."""
	if signer is None:
		signer = bool(acte and acte.get("signe_electroniquement"))
	ctx = moteur.contexte_pour(modele, sujet, acte, params)
	if modele.get("modele_word"):
		chemin = moteur.chemin_fichier(modele.modele_word)
		if chemin:
			from docxtpl import DocxTemplate

			gabarit = DocxTemplate(chemin)
			gabarit.render(_en_dict(ctx), autoescape=True)
			out = io.BytesIO()
			gabarit.save(out)
			return out.getvalue()
	return _construire(modele, sujet, ctx, signer, gabarit=False)


def modele_vierge(modele):
	"""Modèle Word avec ses variables {{ … }} (à retoucher puis redéposer sur le modèle)."""
	if modele.get("modele_word"):
		chemin = moteur.chemin_fichier(modele.modele_word)
		if chemin:
			with open(chemin, "rb") as f:
				return f.read()
	return _construire(modele, None, None, True, gabarit=True)
