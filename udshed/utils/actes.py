"""Actes académiques : modèles dessinés, données, rendu PDF, vérification.

Un modèle (« Modele Acte ») est une page au format choisi (A4, carte…) sur
laquelle l'éditeur visuel place des ÉLÉMENTS (positions et tailles en mm) :

  texte          texte libre avec variables Jinja : {{ etudiant.nom_complet }}
  image          image téléversée (logo, bandeau, filigrane…)
  logo           logo de l'établissement (Udshed Setting)
  photo          photo de l'étudiant
  qr             QR code de vérification (lien /verifier-acte?code=…)
  signature      image de signature du modèle (signature électronique)
  cachet         image du cachet du modèle (signature électronique)
  cadre          rectangle (bordure, fond)
  tableau_notes  relevé des notes (semestres, UE, crédits, notes, décisions)

Les variables disponibles sont décrites par `catalogue_variables()`.
"""

import base64
import json
import mimetypes
import os

import frappe
from frappe import _
from frappe.utils import escape_html, flt, format_date, getdate, today

FORMATS = {
	"A4 portrait": (210, 297),
	"A4 paysage": (297, 210),
	"A5 paysage": (210, 148),
	"Carte (85,6 × 54 mm)": (85.6, 54),
}


# ---------------------------------------------------------------------- #
#  Images
# ---------------------------------------------------------------------- #
def chemin_fichier(url):
	"""Chemin disque d'un fichier (asset, /files, /private/files), sinon None."""
	url = (url or "").strip()
	if not url:
		return None
	if url.startswith("/assets/"):
		app, _sep, reste = url[len("/assets/"):].partition("/")
		chemin = frappe.get_app_path(app, "public", *reste.split("/"))
	elif url.startswith("/private/files/"):
		chemin = frappe.utils.get_site_path("private", "files", url.rsplit("/", 1)[-1])
	elif url.startswith("/files/"):
		chemin = frappe.utils.get_site_path("public", "files", url.rsplit("/", 1)[-1])
	else:
		return None
	return chemin if os.path.exists(chemin) else None


def data_uri(url):
	"""Image embarquée (data-URI) : le PDF ne dépend d'aucune URL réseau."""
	chemin = chemin_fichier(url)
	if not chemin:
		return ""
	mime = mimetypes.guess_type(chemin)[0] or "image/png"
	with open(chemin, "rb") as f:
		return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"


def qr_data_uri(texte):
	import pyqrcode

	return "data:image/png;base64," + pyqrcode.create(texte, error="M").png_as_base64_str(scale=6, quiet_zone=2)


# ---------------------------------------------------------------------- #
#  Données d'un acte
# ---------------------------------------------------------------------- #
def _annee_courante():
	return frappe.db.get_single_value("Udshed Setting", "current_year") or ""


def inscription_de(student, academic_year=None):
	"""Réinscription validée de l'étudiant pour l'année (sinon la plus récente)."""
	filtres = {"student": student, "statut": "Validée"}
	if academic_year:
		filtres["academic_year"] = academic_year
	return frappe.db.get_value("Academic Reregistration", filtres, ["name", "academic_year", "filiere", "niveau"],
							   as_dict=True, order_by="academic_year desc")


def diplome_de(student, cycle=None):
	if not frappe.db.table_exists("Diplome Etudiant"):
		return None
	filtres = {"student": student, "statut": "Délivré"}
	if cycle:
		filtres["cycle"] = cycle
	return frappe.db.get_value("Diplome Etudiant", filtres, "*", as_dict=True, order_by="date_jury desc")


def contexte(student, modele, acte=None):
	"""Variables Jinja disponibles dans les textes du modèle."""
	from udshed.utils.etablissement import etablissement

	s = frappe.get_doc("Student", student)
	insc = inscription_de(student, _annee_courante()) or inscription_de(student) or frappe._dict()
	filiere = insc.get("filiere") or s.filiere
	nom_filiere = frappe.db.get_value("Field of study", filiere, "name_of_field") if filiere else ""
	code = acte.code_verification if acte else "APERCU"
	lien = frappe.utils.get_url(f"/verifier-acte?code={code}")
	dip = diplome_de(student) or frappe._dict()
	return {
		"etablissement": etablissement(),
		"etudiant": frappe._dict({
			"matricule": s.matricule or s.name, "nom": s.nom or "", "prenom": s.prenom or "",
			"nom_complet": " ".join(x for x in [s.nom, s.prenom] if x),
			"sexe": s.sexe or "", "ne_e": "née" if (s.sexe or "").lower().startswith(("f", "fé")) else "né",
			"date_naissance": format_date(s.birth_date) if s.birth_date else "",
			"lieu_naissance": s.birth_place or "", "email": s.email or "", "cycle": s.cycle or "",
			"filiere": nom_filiere or filiere or "", "code_filiere": filiere or "",
			"niveau": insc.get("niveau") or s.niveau_actuel or "",
		}),
		"inscription": frappe._dict({"annee": insc.get("academic_year") or _annee_courante(),
									 "niveau": insc.get("niveau") or s.niveau_actuel or "",
									 "filiere": nom_filiere or filiere or ""}),
		"acte": frappe._dict({"numero": acte.name if acte else "ACTE-APERCU", "code": code, "lien_verification": lien,
							  "date": format_date(acte.traite_le or acte.creation if acte else today()),
							  "type": modele.type_acte, "lieu": (etablissement().adresse or "").split(",")[-1].strip()}),
		"signataire": frappe._dict({"titre": modele.signataire_titre or "", "nom": modele.signataire_nom or ""}),
		"diplome": frappe._dict({"intitule": dip.get("intitule") or "", "mention": dip.get("mention") or "",
								 "moyenne": dip.get("moyenne") or "", "cycle": dip.get("cycle") or "",
								 "annee": dip.get("academic_year") or "", "numero": dip.get("name") or "",
								 "date_jury": format_date(dip.get("date_jury")) if dip.get("date_jury") else ""}),
		"date_du_jour": format_date(today()),
	}


def catalogue_variables():
	"""Variables proposées par l'éditeur (insertion en un clic)."""
	return [
		("etablissement.nom", "Nom de l'établissement"), ("etablissement.institut", "Institut / école"),
		("etablissement.adresse", "Adresse"), ("etablissement.telephone", "Téléphone"),
		("etudiant.nom_complet", "Nom complet"), ("etudiant.nom", "Nom"), ("etudiant.prenom", "Prénom"),
		("etudiant.matricule", "Matricule"), ("etudiant.ne_e", "né / née"),
		("etudiant.date_naissance", "Date de naissance"), ("etudiant.lieu_naissance", "Lieu de naissance"),
		("etudiant.filiere", "Filière"), ("etudiant.niveau", "Niveau"), ("etudiant.cycle", "Cycle"),
		("inscription.annee", "Année académique"), ("acte.numero", "Numéro de l'acte"),
		("acte.date", "Date de délivrance"), ("acte.lieu", "Lieu de délivrance"),
		("signataire.titre", "Titre du signataire"), ("signataire.nom", "Nom du signataire"),
		("diplome.intitule", "Intitulé du diplôme"), ("diplome.mention", "Mention"),
		("diplome.moyenne", "Moyenne du cycle"), ("diplome.date_jury", "Date du jury"),
		("diplome.annee", "Année d'obtention"), ("date_du_jour", "Date du jour"),
	]


# ---------------------------------------------------------------------- #
#  Conditions d'obtention
# ---------------------------------------------------------------------- #
def verifier_condition(modele, student):
	"""(possible, message) selon la condition du modèle."""
	condition = modele.condition or "Aucune"
	if condition == "Inscrit pour l'année en cours":
		annee = _annee_courante()
		if not inscription_de(student, annee):
			return False, _("Vous n'êtes pas inscrit(e) pour l'année {0}.").format(annee)
	elif condition == "Résultats publiés":
		if not frappe.db.exists("Resultat Academique", {"student": student}):
			return False, _("Aucun résultat publié pour le moment.")
	elif condition == "Diplômé du cycle":
		if not diplome_de(student):
			return False, _("Document réservé aux diplômé(e)s : votre diplomation n'a pas encore été prononcée.")
	return True, ""


# ---------------------------------------------------------------------- #
#  Rendu
# ---------------------------------------------------------------------- #
def _style(el):
	css = [f"left:{flt(el.get('x'))}mm", f"top:{flt(el.get('y'))}mm",
		   f"width:{flt(el.get('w'))}mm", f"height:{flt(el.get('h'))}mm"]
	if el.get("taille"):
		css.append(f"font-size:{flt(el['taille'])}pt")
	if el.get("gras"):
		css.append("font-weight:700")
	if el.get("italique"):
		css.append("font-style:italic")
	if el.get("couleur"):
		css.append(f"color:{escape_html(el['couleur'])}")
	if el.get("align"):
		css.append(f"text-align:{escape_html(el['align'])}")
	if el.get("police"):
		css.append(f"font-family:{escape_html(el['police'])}")
	return ";".join(css)


def _tableau_notes(student, taille):
	from udshed.api.transcript import get_transcript_data

	data = get_transcript_data({"name": student, "niveau_actuel": frappe.db.get_value("Student", student, "niveau_actuel")})
	lignes = []
	for sem in data.get("semesters") or []:
		lignes.append(f"<tr class='sem'><td colspan='5'>{escape_html(sem['label'])} — {escape_html(sem['academic_year'])}"
					  f" · MPS {sem.get('mps') or 0} · {escape_html(sem.get('decision') or '')}</td></tr>")
		for ue in sem.get("ues") or []:
			lignes.append(
				f"<tr><td>{escape_html(ue.get('code') or '')}</td><td>{escape_html(ue.get('intitule') or '')}</td>"
				f"<td class='n'>{ue.get('credits') or ''}</td><td class='n'>{ue.get('note_finale') if ue.get('note_finale') is not None else ''}</td>"
				f"<td>{escape_html(ue.get('grade') or '')} {escape_html(ue.get('statut') or '')}</td></tr>")
	pied = (f"<tr class='sem'><td colspan='5'>Crédits validés : {data.get('total_credits_obtenus') or 0}/"
			f"{data.get('total_credits') or 0} · Décision : {escape_html(data.get('overall_decision') or '')}</td></tr>")
	return (f"<table class='notes' style='font-size:{flt(taille) or 8}pt'><thead><tr><th>Code</th><th>Unité d'enseignement</th>"
			f"<th>Crédits</th><th>Note /20</th><th>Grade · statut</th></tr></thead><tbody>{''.join(lignes)}{pied}</tbody></table>")


def html(modele, student, acte=None, signer=None):
	"""HTML complet du document (positions absolues en mm, images embarquées)."""
	largeur, hauteur = FORMATS.get(modele.format, FORMATS["A4 portrait"])
	ctx = contexte(student, modele, acte)
	if signer is None:
		signer = bool(acte and acte.signe_electroniquement)
	layout = json.loads(modele.layout or "{}") if isinstance(modele.layout, str) else (modele.layout or {})
	morceaux = []
	if modele.image_fond:
		morceaux.append(f"<img class='fond' src='{data_uri(modele.image_fond)}'>")
	for el in layout.get("elements") or []:
		t = el.get("type")
		style = _style(el)
		if t == "texte":
			try:
				texte = frappe.render_template(el.get("contenu") or "", ctx)
			except Exception:
				texte = el.get("contenu") or ""
			texte = escape_html(texte).replace("\n", "<br>")
			morceaux.append(f"<div class='el' style='{style}'>{texte}</div>")
		elif t == "image" and el.get("src"):
			morceaux.append(f"<img class='el' style='{style};object-fit:contain' src='{data_uri(el['src'])}'>")
		elif t == "logo":
			from udshed.api.school_setting import get_logo_data_uri

			morceaux.append(f"<img class='el' style='{style};object-fit:contain' src='{get_logo_data_uri()}'>")
		elif t == "photo":
			src = data_uri(frappe.db.get_value("Student", student, "photo"))
			morceaux.append(f"<img class='el' style='{style};object-fit:cover' src='{src}'>" if src
							else f"<div class='el photo-vide' style='{style}'>Photo</div>")
		elif t == "qr":
			morceaux.append(f"<img class='el' style='{style}' src='{qr_data_uri(ctx['acte'].lien_verification)}'>")
		elif t in ("signature", "cachet"):
			image = modele.image_signature if t == "signature" else modele.image_cachet
			if signer and image:
				morceaux.append(f"<img class='el' style='{style};object-fit:contain' src='{data_uri(image)}'>")
		elif t == "cadre":
			bordure = flt(el.get("bordure") if el.get("bordure") is not None else 0.5)
			fond = escape_html(el.get("fond") or "transparent")
			couleur = escape_html(el.get("couleur") or "#1f3c88")
			morceaux.append(f"<div class='el' style='{style};border:{bordure}mm solid {couleur};background:{fond};"
							f"border-radius:{flt(el.get('arrondi'))}mm'></div>")
		elif t == "tableau_notes":
			morceaux.append(f"<div class='el' style='{style};overflow:hidden'>{_tableau_notes(student, el.get('taille'))}</div>")
	return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@page {{ size: {largeur}mm {hauteur}mm; margin: 0; }}
html, body {{ margin: 0; padding: 0; }}
body {{ width: {largeur}mm; height: {hauteur}mm; position: relative; overflow: hidden;
	font-family: "DejaVu Sans", Arial, sans-serif; font-size: 11pt; color: #1b1f2a; }}
.fond {{ position: absolute; left: 0; top: 0; width: {largeur}mm; height: {hauteur}mm; object-fit: cover; }}
.el {{ position: absolute; box-sizing: border-box; line-height: 1.35; }}
.photo-vide {{ border: 0.3mm dashed #98a2b3; color: #98a2b3; display: flex; align-items: center; justify-content: center; }}
table.notes {{ width: 100%; border-collapse: collapse; }}
table.notes th, table.notes td {{ border: 0.2mm solid #c9ced8; padding: 0.6mm 1mm; text-align: left; }}
table.notes th {{ background: #eef2f8; }}
table.notes td.n {{ text-align: right; }}
table.notes tr.sem td {{ background: #f6f8fb; font-weight: 700; }}
</style></head><body>{''.join(morceaux)}</body></html>"""


def pdf(modele, student, acte=None, signer=None):
	from weasyprint import HTML

	return HTML(string=html(modele, student, acte, signer), base_url=frappe.utils.get_url()).write_pdf()


# ---------------------------------------------------------------------- #
#  Modèles par défaut (installation)
# ---------------------------------------------------------------------- #
def _t(x, y, w, h, contenu, taille=11, **k):
	return {"type": "texte", "x": x, "y": y, "w": w, "h": h, "contenu": contenu, "taille": taille, **k}


ENTETE_A4 = [
	{"type": "logo", "x": 15, "y": 12, "w": 28, "h": 28},
	_t(48, 14, 150, 9, "{{ etablissement.nom }}", 15, gras=True, couleur="#1f3c88"),
	_t(48, 23, 150, 7, "{{ etablissement.institut }}", 10, couleur="#475467"),
	_t(48, 30, 150, 7, "{{ etablissement.adresse }} {{ etablissement.telephone }}", 9, couleur="#475467"),
	{"type": "cadre", "x": 15, "y": 43, "w": 180, "h": 0.6, "bordure": 0.3, "couleur": "#1f3c88"},
]
PIED_SIGNE_A4 = [
	_t(110, 222, 85, 7, "Fait à {{ acte.lieu }}, le {{ acte.date }}", 10, align="center"),
	_t(110, 230, 85, 7, "{{ signataire.titre }}", 10, gras=True, align="center"),
	{"type": "cachet", "x": 112, "y": 238, "w": 32, "h": 32},
	{"type": "signature", "x": 140, "y": 240, "w": 45, "h": 22},
	_t(110, 265, 85, 7, "{{ signataire.nom }}", 10, align="center"),
	{"type": "qr", "x": 15, "y": 240, "w": 30, "h": 30},
	_t(15, 271, 90, 10, "N° {{ acte.numero }} — authenticité vérifiable par le QR code", 7, couleur="#667085"),
]

MODELES_DEFAUT = [
	{"titre": "Certificat de scolarité", "type_acte": "Certificat de scolarité", "format": "A4 portrait",
	 "libre_service": 1, "condition": "Inscrit pour l'année en cours", "mode_signature": "Électronique",
	 "elements": ENTETE_A4 + [
		 _t(15, 62, 180, 12, "CERTIFICAT DE SCOLARITÉ", 20, gras=True, align="center", couleur="#1f3c88"),
		 _t(15, 76, 180, 7, "Année académique {{ inscription.annee }}", 11, align="center"),
		 _t(25, 100, 160, 80,
			"Je soussigné(e), {{ signataire.titre }} de {{ etablissement.nom }}, certifie que "
			"{{ etudiant.nom_complet }}, {{ etudiant.ne_e }} le {{ etudiant.date_naissance }} à "
			"{{ etudiant.lieu_naissance }}, matricule {{ etudiant.matricule }}, est régulièrement inscrit(e) en "
			"{{ etudiant.niveau }} {{ etudiant.filiere }} au titre de l'année académique {{ inscription.annee }}.\n\n"
			"En foi de quoi le présent certificat lui est délivré pour servir et valoir ce que de droit.", 12),
	 ] + PIED_SIGNE_A4},
	{"titre": "Attestation d'inscription", "type_acte": "Attestation d'inscription", "format": "A4 portrait",
	 "libre_service": 0, "condition": "Inscrit pour l'année en cours", "mode_signature": "Électronique",
	 "elements": ENTETE_A4 + [
		 _t(15, 62, 180, 12, "ATTESTATION D'INSCRIPTION", 20, gras=True, align="center", couleur="#1f3c88"),
		 _t(25, 95, 160, 80,
			"{{ signataire.titre }} de {{ etablissement.nom }} atteste que {{ etudiant.nom_complet }}, matricule "
			"{{ etudiant.matricule }}, est inscrit(e) en {{ etudiant.niveau }} {{ etudiant.filiere }} pour l'année "
			"académique {{ inscription.annee }}.", 12),
	 ] + PIED_SIGNE_A4},
	{"titre": "Carte d'étudiant", "type_acte": "Carte d'étudiant", "format": "Carte (85,6 × 54 mm)",
	 "libre_service": 1, "condition": "Inscrit pour l'année en cours", "mode_signature": "Électronique",
	 "elements": [
		 {"type": "cadre", "x": 0, "y": 0, "w": 85.6, "h": 11, "bordure": 0, "fond": "#1f3c88", "couleur": "#1f3c88"},
		 {"type": "logo", "x": 2, "y": 1.5, "w": 8, "h": 8},
		 _t(11, 1.5, 72, 5, "{{ etablissement.nom }}", 7, gras=True, couleur="#ffffff"),
		 _t(11, 6, 72, 4, "CARTE D'ÉTUDIANT {{ inscription.annee }}", 5.5, couleur="#ffffff"),
		 {"type": "photo", "x": 3, "y": 14, "w": 20, "h": 25},
		 _t(26, 14, 57, 5, "{{ etudiant.nom_complet }}", 7, gras=True),
		 _t(26, 20, 57, 4, "Matricule : {{ etudiant.matricule }}", 6),
		 _t(26, 24.5, 57, 4, "{{ etudiant.niveau }} — {{ etudiant.filiere }}", 6),
		 _t(26, 29, 57, 4, "Né(e) le {{ etudiant.date_naissance }}", 6),
		 {"type": "qr", "x": 66, "y": 34, "w": 17, "h": 17},
		 {"type": "signature", "x": 30, "y": 38, "w": 22, "h": 10},
		 _t(3, 47, 60, 4, "Valable pour l'année {{ inscription.annee }}", 5, couleur="#667085"),
	 ]},
	{"titre": "Relevé de notes", "type_acte": "Relevé de notes", "format": "A4 portrait",
	 "libre_service": 1, "condition": "Résultats publiés", "mode_signature": "Électronique",
	 "elements": ENTETE_A4 + [
		 _t(15, 48, 180, 10, "RELEVÉ DE NOTES", 17, gras=True, align="center", couleur="#1f3c88"),
		 _t(15, 60, 180, 14, "{{ etudiant.nom_complet }} — matricule {{ etudiant.matricule }}\n"
							 "{{ etudiant.filiere }} · {{ etudiant.niveau }}", 10, align="center"),
		 {"type": "tableau_notes", "x": 15, "y": 78, "w": 180, "h": 140, "taille": 7.5},
	 ] + PIED_SIGNE_A4},
	{"titre": "Attestation de réussite", "type_acte": "Attestation de réussite", "format": "A4 portrait",
	 "libre_service": 0, "condition": "Diplômé du cycle", "mode_signature": "Électronique",
	 "elements": ENTETE_A4 + [
		 _t(15, 62, 180, 12, "ATTESTATION DE RÉUSSITE", 20, gras=True, align="center", couleur="#1f3c88"),
		 _t(25, 95, 160, 90,
			"{{ signataire.titre }} de {{ etablissement.nom }} atteste que {{ etudiant.nom_complet }}, "
			"{{ etudiant.ne_e }} le {{ etudiant.date_naissance }} à {{ etudiant.lieu_naissance }}, matricule "
			"{{ etudiant.matricule }}, a obtenu le diplôme de {{ diplome.intitule }}, session {{ diplome.annee }}, "
			"avec la mention {{ diplome.mention }}, par décision du jury du {{ diplome.date_jury }}.\n\n"
			"La présente attestation lui est délivrée en attendant la remise du diplôme original.", 12),
	 ] + PIED_SIGNE_A4},
	{"titre": "Diplôme", "type_acte": "Diplôme", "format": "A4 paysage", "libre_service": 0,
	 "condition": "Diplômé du cycle", "mode_signature": "Manuscrite",
	 "elements": [
		 {"type": "cadre", "x": 8, "y": 8, "w": 281, "h": 194, "bordure": 1.2, "couleur": "#1f3c88"},
		 {"type": "logo", "x": 134, "y": 14, "w": 28, "h": 28},
		 _t(20, 44, 257, 10, "{{ etablissement.nom }}", 18, gras=True, align="center", couleur="#1f3c88"),
		 _t(20, 62, 257, 16, "DIPLÔME", 30, gras=True, align="center", couleur="#1f3c88", police="serif"),
		 _t(30, 84, 237, 60,
			"Vu les résultats du jury du {{ diplome.date_jury }}, le diplôme de\n{{ diplome.intitule }}\n"
			"est décerné à {{ etudiant.nom_complet }}, {{ etudiant.ne_e }} le {{ etudiant.date_naissance }} "
			"à {{ etudiant.lieu_naissance }},\navec la mention {{ diplome.mention }}.", 14, align="center", police="serif"),
		 _t(170, 158, 110, 7, "Fait à {{ acte.lieu }}, le {{ acte.date }}", 10, align="center"),
		 _t(170, 166, 110, 7, "{{ signataire.titre }}", 10, gras=True, align="center"),
		 {"type": "qr", "x": 20, "y": 165, "w": 28, "h": 28},
		 _t(52, 186, 110, 6, "N° {{ acte.numero }}", 8, couleur="#667085"),
	 ]},
]


def creer_modeles_defaut():
	"""Crée les modèles absents (installation, migration). Ne modifie jamais un modèle existant."""
	for m in MODELES_DEFAUT:
		if frappe.db.exists("Modele Acte", m["titre"]):
			continue
		doc = frappe.get_doc({"doctype": "Modele Acte", "actif": 1, "signataire_titre": "Le Directeur des affaires académiques",
							  **{k: v for k, v in m.items() if k != "elements"},
							  "layout": json.dumps({"elements": m["elements"]}, ensure_ascii=False)})
		doc.insert(ignore_permissions=True)
