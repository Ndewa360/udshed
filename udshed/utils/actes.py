"""Documents (actes académiques des étudiants, documents des enseignants) : modèles
dessinés, données, rendu PDF (et Word, voir documents_word.py), vérification.

Un modèle a un SUJET : « Étudiant » (certificat, carte, relevé…) ou « Enseignant »
(fiche de progression, règlement des vacations, convention, attestation d'enseignement).
Pour chaque type de document, un modèle « par défaut » est utilisé par tous.

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
  tableau_progression / tableau_vacations / tableau_enseignements  (documents enseignants)

Les variables disponibles sont décrites par `catalogue_variables()`.
"""

import base64
import json
import mimetypes
import os

import frappe
from frappe import _
from frappe.utils import escape_html, flt, format_date, getdate, today

SUJET_ETUDIANT = "Étudiant"
SUJET_ENSEIGNANT = "Enseignant"
TYPES_ENSEIGNANT = ("Fiche de progression des cours", "Fiche de règlement des vacations",
					"Convention de vacation", "Attestation d'enseignement")
TABLEAUX = ("tableau_notes", "tableau_progression", "tableau_vacations", "tableau_enseignements")

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
#  Formats français
# ---------------------------------------------------------------------- #
MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
		   "novembre", "décembre"]
SYMBOLES = {"XAF": "FCFA", "XOF": "FCFA", "EUR": "€", "USD": "$"}


def date_longue(valeur):
	"""26 novembre 2026 / 1er mars 2027."""
	if not valeur:
		return ""
	d = getdate(valeur)
	return f"{d.day}{'er' if d.day == 1 else ''} {MOIS_FR[d.month - 1]} {d.year}"


def montant(valeur, devise=None):
	"""6 500 FCFA (espaces fines pour les milliers, sans décimales)."""
	chiffres = f"{round(flt(valeur)):,}".replace(",", "\u202f")
	symbole = SYMBOLES.get(devise) or (frappe.db.get_value("Currency", devise, "symbol") if devise else "") or devise or ""
	return f"{chiffres} {symbole}".strip()


def en_lettres(valeur, devise=None):
	"""deux cent cinquante-sept mille neuf cent quatre-vingt-cinq francs CFA."""
	try:
		from num2words import num2words

		texte = num2words(int(round(flt(valeur))), lang="fr")
	except Exception:
		return montant(valeur, devise)
	unite = "francs CFA" if devise in ("XAF", "XOF") else (devise or "")
	return f"{texte} {unite}".strip()


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
			"date_naissance": date_longue(s.birth_date),
			"lieu_naissance": s.birth_place or "", "email": s.email or "", "cycle": s.cycle or "",
			"filiere": nom_filiere or filiere or "", "code_filiere": filiere or "",
			"niveau": insc.get("niveau") or s.niveau_actuel or "",
		}),
		"inscription": frappe._dict({"annee": insc.get("academic_year") or _annee_courante(),
									 "niveau": insc.get("niveau") or s.niveau_actuel or "",
									 "filiere": nom_filiere or filiere or ""}),
		"acte": frappe._dict({"numero": acte.name if acte else "ACTE-APERCU", "code": code, "lien_verification": lien,
							  "date": date_longue(acte.traite_le or acte.creation if acte else today()),
							  "type": modele.type_acte, "lieu": (etablissement().adresse or "").split(",")[-1].strip()}),
		"signataire": frappe._dict({"titre": modele.signataire_titre or "", "nom": modele.signataire_nom or ""}),
		"diplome": frappe._dict({"intitule": dip.get("intitule") or "", "mention": dip.get("mention") or "",
								 "moyenne": dip.get("moyenne") or "", "cycle": dip.get("cycle") or "",
								 "annee": dip.get("academic_year") or "", "numero": dip.get("name") or "",
								 "date_jury": date_longue(dip.get("date_jury"))}),
		"date_du_jour": date_longue(today()),
		"notes": frappe._dict({"lignes": lignes_notes(student)}) if _utilise_notes(modele) else frappe._dict({"lignes": []}),
	}


def _utilise_notes(modele):
	return "tableau_notes" in (modele.get("layout") or "") or bool(modele.get("modele_word"))


def lignes_notes(student):
	from udshed.api.transcript import get_transcript_data

	data = get_transcript_data({"name": student, "niveau_actuel": frappe.db.get_value("Student", student, "niveau_actuel")})
	lignes = []
	for sem in data.get("semesters") or []:
		lignes.append({"code": sem["label"], "intitule": f"{sem['academic_year']} · MPS {sem.get('mps') or 0}",
					   "credits": "", "note": "", "grade": sem.get("decision") or "", "_gras": True})
		for ue in sem.get("ues") or []:
			lignes.append({"code": ue.get("code") or "", "intitule": ue.get("intitule") or "",
						   "credits": ue.get("credits") or "",
						   "note": ue.get("note_finale") if ue.get("note_finale") is not None else "",
						   "grade": " ".join(x for x in [ue.get("grade"), ue.get("statut")] if x)})
	return lignes


# ---------------------------------------------------------------------- #
#  Documents des enseignants
# ---------------------------------------------------------------------- #
def _h(valeur):
	"""Heures lisibles : 12 / 12,5."""
	v = round(flt(valeur), 2)
	return (f"{v:g}").replace(".", ",")


def _argent(valeur, devise):
	return montant(valeur, devise)


def contexte_enseignant(teacher, modele, acte=None, params=None):
	"""Variables des documents enseignants (fiches, convention, attestation)."""
	from udshed.utils import vacations
	from udshed.utils.etablissement import etablissement

	params = frappe._dict(params or {})
	t = frappe.get_doc("Teacher", teacher)
	annee = params.academic_year or (acte.get("academic_year") if acte else None) or _annee_courante()
	f = vacations.fiche(teacher, annee, params.periode or (acte.get("periode") if acte else None))
	devise = f.devise
	code = acte.code_verification if acte else "APERCU"
	lien = frappe.utils.get_url(f"/verifier-acte?code={code}")
	nom_complet = " ".join(x for x in [t.grade, t.first_name, t.last_name] if x) or t.name
	conv_nom = params.convention or (acte.get("convention") if acte else None) or frappe.db.get_value(
		"Convention Vacation", {"teacher": teacher, "academic_year": annee}, "name", order_by="creation desc")
	conv = frappe.get_doc("Convention Vacation", conv_nom) if conv_nom else frappe._dict()
	lignes_vac = [{**lg, "type": lg["type"], "fait": _h(lg["fait"]), "prevu": _h(lg["prevu"]),
				   "planifie": _h(lg["planifie"]), "taux": _argent(lg["taux"] * lg["coef"], devise),
				   "montant": _argent(lg["montant"], devise), "avancement": f"{lg['avancement']:g} %".replace(".", ",")}
				  for lg in f.lignes]
	cours = {}
	for lg in f.lignes:
		c = cours.setdefault(lg["cours"], {"intitule": lg["intitule"], "classes": lg["classes"],
										  "semestre": lg["semestre"] or "", "prevu": 0.0, "fait": 0.0})
		c["prevu"] += lg["prevu"]
		c["fait"] += lg["fait"]
	enseignements = [{**c, "prevu": _h(c["prevu"]), "fait": _h(c["fait"])} for c in cours.values()]
	date_doc = (acte.get("genere_le") or acte.get("creation")) if acte else None
	etab = etablissement()
	document = frappe._dict({"numero": acte.name if acte else "DOC-APERCU", "code": code, "lien_verification": lien,
							  "date": date_longue(date_doc or today()), "type": modele.type_acte,
							  "lieu": (etab.adresse or "").split(",")[-1].strip()})
	return {
		"etablissement": etab,
		"enseignant": frappe._dict({
			"nom_complet": nom_complet, "nom": t.last_name or "", "prenom": t.first_name or "",
			"grade": t.grade or "", "titre": t.get("titre") or f.titre or "", "statut": t.status or "",
			"specialite": t.get("specialite") or "", "diplome": t.get("diplome") or "", "email": t.email or "",
			"telephone": t.get("phone") or "", "universite": t.get("universite_rattache") or "",
			"ville": t.get("ville_de_residence") or "",
			"faculte": (frappe.db.get_value("Faculty", t.faculte, "faculty_name") if t.get("faculte") else "") or "",
		}),
		"annee": annee,
		"inscription": frappe._dict({"annee": annee}),
		"periode": frappe._dict({"libelle": f.periode, "debut": date_longue(f.debut), "fin": date_longue(f.fin)}),
		"vacations": frappe._dict({
			"heures_prevues": _h(f.heures_prevues), "heures_faites": _h(f.heures_faites),
			"taux": _argent(f.taux, devise), "brut": _argent(f.brut, devise), "retenue": _argent(f.retenue, devise),
			"taux_retenue": f"{flt(f.taux_retenue):g} %".replace(".", ","), "net": _argent(f.net, devise),
			"net_lettres": en_lettres(f.net, devise), "devise": devise, "base": f.base,
			"lignes": lignes_vac,
		}),
		"progression": frappe._dict({
			"heures_prevues": _h(f.heures_prevues), "heures_planifiees": _h(f.heures_planifiees),
			"heures_faites": _h(f.heures_faites),
			"avancement": f"{(round(100 * f.heures_faites / f.heures_prevues, 1) if f.heures_prevues else 0):g} %".replace(".", ","),
			"lignes": lignes_vac,
		}),
		"enseignements": enseignements,
		"convention": frappe._dict({
			"numero": conv.get("name") or "", "volume_horaire": _h(conv.get("volume_horaire") or f.heures_prevues),
			"taux": _argent(conv.get("taux_horaire") or f.taux, devise),
			"montant_previsionnel": _argent(conv.get("montant_previsionnel") or 0, devise),
			"date_debut": date_longue(conv.get("date_debut") or f.debut),
			"date_fin": date_longue(conv.get("date_fin") or f.fin),
			"date_signature": date_longue(conv.get("date_signature")),
		}),
		"acte": document,
		"document": document,
		"signataire": frappe._dict({"titre": modele.signataire_titre or "", "nom": modele.signataire_nom or ""}),
		"date_du_jour": date_longue(today()),
	}


def contexte_pour(modele, sujet, acte=None, params=None):
	"""Contexte selon le sujet du modèle (`sujet` = Student ou Teacher)."""
	if (modele.get("sujet") or SUJET_ETUDIANT) == SUJET_ENSEIGNANT:
		return contexte_enseignant(sujet, modele, acte, params)
	return contexte(sujet, modele, acte)


def colonnes_tableau(t):
	"""(en-têtes, clés, liste source pour les modèles Word) d'un tableau."""
	return {
		"tableau_notes": (["Code", "Unité d'enseignement", "Crédits", "Note /20", "Grade · statut"],
						   ["code", "intitule", "credits", "note", "grade"], "notes.lignes"),
		"tableau_progression": (["Cours", "Classes", "Type", "Prévu (h)", "Fait (h)", "Avancement"],
								 ["intitule", "classes", "type", "prevu", "fait", "avancement"], "progression.lignes"),
		"tableau_vacations": (["Cours", "Classes", "Type", "Heures", "Taux horaire", "Montant"],
							   ["intitule", "classes", "type", "fait", "taux", "montant"], "vacations.lignes"),
		"tableau_enseignements": (["Cours", "Classes", "Semestre", "Heures prévues", "Heures assurées"],
								   ["intitule", "classes", "semestre", "prevu", "fait"], "enseignements"),
	}[t]


def lignes_tableau(t, ctx, sujet):
	if t == "tableau_notes":
		return (ctx.get("notes") or {}).get("lignes") or lignes_notes(sujet)
	if t == "tableau_enseignements":
		return ctx.get("enseignements") or []
	bloc = ctx.get("progression" if t == "tableau_progression" else "vacations") or {}
	lignes = list(bloc.get("lignes") or [])
	if t == "tableau_vacations" and lignes:
		lignes.append({"intitule": "Total", "classes": "", "type": "", "fait": bloc.get("heures_faites"),
					   "taux": "", "montant": bloc.get("brut"), "_gras": True})
	if t == "tableau_progression" and lignes:
		lignes.append({"intitule": "Total", "classes": "", "type": "", "prevu": bloc.get("heures_prevues"),
					   "fait": bloc.get("heures_faites"), "avancement": bloc.get("avancement"), "_gras": True})
	return lignes


def _tableau_html(t, ctx, sujet, taille):
	if t == "tableau_notes":
		return _tableau_notes(sujet, taille)
	entetes, cles, _source = colonnes_tableau(t)
	lignes = lignes_tableau(t, ctx, sujet)
	corps = "".join(
		"<tr" + (" class='sem'" if lg.get("_gras") else "") + ">" + "".join(
			f"<td{' class=n' if i >= 3 else ''}>{escape_html(str(lg.get(c) if lg.get(c) is not None else ''))}</td>"
			for i, c in enumerate(cles)) + "</tr>"
		for lg in lignes) or f"<tr><td colspan='{len(cles)}'>Aucun enseignement pour cette période.</td></tr>"
	return (f"<table class='notes' style='font-size:{flt(taille) or 8}pt'><thead><tr>"
			+ "".join(f"<th>{escape_html(h)}</th>" for h in entetes) + f"</tr></thead><tbody>{corps}</tbody></table>")


def catalogue_variables(sujet=SUJET_ETUDIANT):
	if sujet == SUJET_ENSEIGNANT:
		return [
			("etablissement.nom", "Nom de l'établissement"), ("etablissement.adresse", "Adresse"),
			("enseignant.nom_complet", "Nom complet"), ("enseignant.grade", "Grade"), ("enseignant.titre", "Titre"),
			("enseignant.statut", "Statut (permanent / vacataire)"), ("enseignant.specialite", "Spécialité"),
			("enseignant.diplome", "Diplôme"), ("enseignant.universite", "Université de rattachement"),
			("enseignant.faculte", "Faculté"), ("enseignant.telephone", "Téléphone"), ("enseignant.email", "E-mail"),
			("annee", "Année académique"), ("periode.libelle", "Période"), ("periode.debut", "Début de période"),
			("periode.fin", "Fin de période"),
			("progression.heures_prevues", "Heures prévues"), ("progression.heures_faites", "Heures faites"),
			("progression.avancement", "Avancement (%)"),
			("vacations.taux", "Taux horaire"), ("vacations.brut", "Montant brut"), ("vacations.retenue", "Retenue"),
			("vacations.taux_retenue", "Taux de retenue"), ("vacations.net", "Net à payer"),
			("vacations.net_lettres", "Net à payer en lettres"),
			("convention.numero", "N° de convention"), ("convention.volume_horaire", "Volume horaire convenu"),
			("convention.taux", "Taux de la convention"), ("convention.montant_previsionnel", "Montant prévisionnel"),
			("convention.date_debut", "Début de la convention"), ("convention.date_fin", "Fin de la convention"),
			("document.numero", "Numéro du document"), ("document.date", "Date du document"),
			("document.lieu", "Lieu"), ("signataire.titre", "Titre du signataire"), ("signataire.nom", "Nom du signataire"),
			("date_du_jour", "Date du jour"),
		]
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


def html(modele, student, acte=None, signer=None, params=None):
	"""HTML complet du document (positions absolues en mm, images embarquées).

	`student` est le sujet du document : un Student, ou un Teacher pour un modèle « Enseignant »."""
	largeur, hauteur = FORMATS.get(modele.format, FORMATS["A4 portrait"])
	ctx = contexte_pour(modele, student, acte, params)
	enseignant = (modele.get("sujet") or SUJET_ETUDIANT) == SUJET_ENSEIGNANT
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
			src = "" if enseignant else data_uri(frappe.db.get_value("Student", student, "photo"))
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
		elif t in TABLEAUX:
			apres = ""
			if el.get("texte_apres"):
				try:
					texte_apres = frappe.render_template(el["texte_apres"], ctx)
				except Exception:
					texte_apres = el["texte_apres"]
				apres = (f"<div class='apres' style='font-size:{flt(el.get('taille_apres')) or 10}pt'>"
						 f"{escape_html(texte_apres).replace(chr(10), '<br>')}</div>")
			morceaux.append(f"<div class='el' style='{style};overflow:hidden'>"
							f"{_tableau_html(t, ctx, student, el.get('taille'))}{apres}</div>")
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
.apres {{ margin-top: 3mm; line-height: 1.45; }}
</style></head><body>{''.join(morceaux)}</body></html>"""


def pdf(modele, student, acte=None, signer=None, params=None):
	from weasyprint import HTML

	return HTML(string=html(modele, student, acte, signer, params), base_url=frappe.utils.get_url()).write_pdf()


def modele_par_defaut(type_acte):
	"""Modèle utilisé pour un type de document : celui marqué « par défaut », sinon le premier actif."""
	return (frappe.db.get_value("Modele Acte", {"type_acte": type_acte, "actif": 1, "par_defaut": 1}, "name")
			or frappe.db.get_value("Modele Acte", {"type_acte": type_acte, "actif": 1}, "name", order_by="creation asc"))


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


ENTETE_ENS = [
	{"type": "logo", "x": 15, "y": 12, "w": 24, "h": 24},
	_t(44, 13, 125, 8, "{{ etablissement.nom }}", 14, gras=True, couleur="#1f3c88"),
	_t(44, 21, 125, 6, "{{ etablissement.institut }}", 9.5, couleur="#475467"),
	_t(44, 27, 125, 6, "{{ etablissement.adresse }} {{ etablissement.telephone }}", 8.5, couleur="#475467"),
	{"type": "qr", "x": 171, "y": 12, "w": 24, "h": 24},
	{"type": "cadre", "x": 15, "y": 39, "w": 180, "h": 0.6, "bordure": 0.3, "couleur": "#1f3c88"},
]
IDENTITE_ENS = [
	_t(15, 64, 180, 14,
	   "Enseignant : {{ enseignant.nom_complet }}   ·   Statut : {{ enseignant.statut }}\n"
	   "Titre : {{ enseignant.titre }}   ·   Spécialité : {{ enseignant.specialite }}", 10),
]
DEUX_SIGNATURES = [
	_t(15, 228, 180, 7, "Fait à {{ document.lieu }}, le {{ document.date }}", 9.5),
	_t(15, 238, 85, 7, "L'enseignant", 10, gras=True, align="center"),
	_t(110, 238, 85, 7, "{{ signataire.titre }}", 10, gras=True, align="center"),
	{"type": "signature", "x": 130, "y": 246, "w": 45, "h": 20},
	_t(110, 268, 85, 7, "{{ signataire.nom }}", 10, align="center"),
	_t(15, 282, 180, 6, "Document N° {{ document.numero }} — authenticité vérifiable par le QR code", 7, couleur="#667085"),
]


def _tableau(type_, y, h, apres, taille_apres=10):
	return {"type": type_, "x": 15, "y": y, "w": 180, "h": h, "taille": 8, "texte_apres": apres,
			"taille_apres": taille_apres}


MODELES_ENSEIGNANT = [
	{"titre": "Fiche de progression des cours", "type_acte": "Fiche de progression des cours", "sujet": SUJET_ENSEIGNANT,
	 "format": "A4 portrait", "libre_service": 1, "condition": "Aucune", "mode_signature": "Manuscrite",
	 "elements": ENTETE_ENS + [
		 _t(15, 46, 180, 10, "FICHE DE PROGRESSION DES COURS", 16, gras=True, align="center", couleur="#1f3c88"),
		 _t(15, 56, 180, 6, "Année académique {{ annee }} — période {{ periode.libelle }}", 9.5, align="center"),
	 ] + IDENTITE_ENS + [
		 _tableau("tableau_progression", 82, 140,
				  "Heures prévues : {{ progression.heures_prevues }} h   ·   heures faites : {{ progression.heures_faites }} h"
				  "   ·   avancement : {{ progression.avancement }}"),
	 ] + DEUX_SIGNATURES},
	{"titre": "Fiche de règlement des vacations", "type_acte": "Fiche de règlement des vacations",
	 "sujet": SUJET_ENSEIGNANT, "format": "A4 portrait", "libre_service": 1, "condition": "Aucune",
	 "mode_signature": "Manuscrite",
	 "elements": ENTETE_ENS + [
		 _t(15, 46, 180, 10, "FICHE DE RÈGLEMENT DES VACATIONS", 16, gras=True, align="center", couleur="#1f3c88"),
		 _t(15, 56, 180, 6, "Année académique {{ annee }} — période {{ periode.libelle }}", 9.5, align="center"),
	 ] + IDENTITE_ENS + [
		 _tableau("tableau_vacations", 82, 140,
				  "Montant brut : {{ vacations.brut }}   ·   retenue ({{ vacations.taux_retenue }}) : {{ vacations.retenue }}\n"
				  "NET À PAYER : {{ vacations.net }}\n"
				  "Arrêté la présente fiche à la somme de {{ vacations.net_lettres }}."),
	 ] + DEUX_SIGNATURES},
	{"titre": "Convention de vacation", "type_acte": "Convention de vacation", "sujet": SUJET_ENSEIGNANT,
	 "format": "A4 portrait", "libre_service": 0, "condition": "Aucune", "mode_signature": "Manuscrite",
	 "elements": ENTETE_ENS + [
		 _t(15, 46, 180, 10, "CONVENTION DE VACATION", 16, gras=True, align="center", couleur="#1f3c88"),
		 _t(15, 56, 180, 6, "N° {{ convention.numero }} — Année académique {{ annee }}", 9.5, align="center"),
		 _t(15, 66, 180, 26,
			"Entre {{ etablissement.nom }}, représenté par {{ signataire.titre }}, d'une part,\n"
			"et {{ enseignant.nom_complet }}, {{ enseignant.titre }}, spécialité {{ enseignant.specialite }}, "
			"ci-après « l'enseignant vacataire », d'autre part,\nil a été convenu ce qui suit.", 10),
		 _t(15, 94, 180, 12,
			"Article 1 — Objet. L'enseignant vacataire assure, au titre de l'année académique {{ annee }}, "
			"les enseignements suivants :", 10),
		 _tableau("tableau_enseignements", 107, 117,
				  "Article 2 — Volume horaire. Le volume convenu est de {{ convention.volume_horaire }} heures.\n"
				  "Article 3 — Rémunération. Chaque heure effectivement assurée est rémunérée au taux de "
				  "{{ convention.taux }}, sur la base de la fiche de règlement des vacations.\n"
				  "Article 4 — Durée. La présente convention court du {{ convention.date_debut }} au {{ convention.date_fin }}.\n"
				  "Article 5 — Obligations. L'enseignant vacataire s'engage à respecter le planning, à assurer les "
				  "évaluations et à remettre les notes dans les délais fixés.", 9.5),
	 ] + DEUX_SIGNATURES},
	{"titre": "Attestation d'enseignement", "type_acte": "Attestation d'enseignement", "sujet": SUJET_ENSEIGNANT,
	 "format": "A4 portrait", "libre_service": 0, "condition": "Aucune", "mode_signature": "Électronique",
	 "elements": [e for e in ENTETE_ENS if e.get("type") != "qr"] + [
		 _t(15, 50, 180, 12, "ATTESTATION D'ENSEIGNEMENT", 18, gras=True, align="center", couleur="#1f3c88"),
		 _t(20, 70, 170, 24,
			"Je soussigné(e), {{ signataire.titre }} de {{ etablissement.nom }}, atteste que "
			"{{ enseignant.nom_complet }} ({{ enseignant.statut }}) a assuré, au titre de l'année académique "
			"{{ annee }}, les enseignements suivants :", 11),
		 {**_tableau("tableau_enseignements", 96, 122,
					 "soit un volume total de {{ progression.heures_faites }} heures.\n\n"
					 "En foi de quoi la présente attestation lui est délivrée pour servir et valoir ce que de droit.", 11),
		  "x": 20, "w": 170, "taille": 8.5},
		 _t(110, 222, 85, 7, "Fait à {{ document.lieu }}, le {{ document.date }}", 10, align="center"),
		 _t(110, 230, 85, 7, "{{ signataire.titre }}", 10, gras=True, align="center"),
		 {"type": "cachet", "x": 112, "y": 238, "w": 32, "h": 32},
		 {"type": "signature", "x": 140, "y": 240, "w": 45, "h": 22},
		 _t(110, 265, 85, 7, "{{ signataire.nom }}", 10, align="center"),
		 {"type": "qr", "x": 15, "y": 240, "w": 30, "h": 30},
		 _t(15, 271, 90, 10, "N° {{ document.numero }} — authenticité vérifiable par le QR code", 7, couleur="#667085"),
	 ]},
]


def creer_modeles_defaut():
	"""Crée les modèles absents (installation, migration). Ne modifie jamais un modèle existant."""
	for m in MODELES_DEFAUT + MODELES_ENSEIGNANT:
		if frappe.db.exists("Modele Acte", m["titre"]):
			continue
		# Premier modèle de son type : il devient le modèle par défaut.
		par_defaut = 0 if frappe.db.exists("Modele Acte", {"type_acte": m["type_acte"], "par_defaut": 1}) else 1
		doc = frappe.get_doc({"doctype": "Modele Acte", "actif": 1, "par_defaut": par_defaut,
							  "signataire_titre": "Le Directeur des affaires académiques", "sujet": SUJET_ETUDIANT,
							  **{k: v for k, v in m.items() if k != "elements"},
							  "layout": json.dumps({"elements": m["elements"]}, ensure_ascii=False)})
		doc.insert(ignore_permissions=True)
