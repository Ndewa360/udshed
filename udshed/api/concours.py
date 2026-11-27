# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Concours d'entrée — phase 2 : inscription des candidats autorisés à concourir,
convocation par e-mail et listes d'émargement par centre."""

import secrets
import unicodedata

import frappe
from frappe import _

from udshed.udshed.doctype.concours.concours import _cle_matiere

STATUT_AUTORISE = "Autorisé à concourir"
STATUT_LISTE_ATTENTE = "Liste d'attente"
STATUT_DESISTE = "Désisté"
# Statuts de candidature posés uniquement par le concours (publication, désistement).
STATUTS_GERES_PAR_CONCOURS = (STATUT_LISTE_ATTENTE, STATUT_DESISTE)
# Statuts du concours pendant lesquels on peut encore autoriser des candidats.
STATUTS_CONCOURS_INSCRIPTION = ("Candidatures ouvertes", "Épreuves")
# Caractères sans ambiguïté de lecture (ni 0/O, ni 1/I) pour les codes d'anonymat.
ALPHABET_ANONYMAT = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


# --------------------------------------------------------------------------- #
#  Inscription / retrait d'un candidat
# --------------------------------------------------------------------------- #
def fiche_du_candidat(candidature):
	return frappe.db.get_value("Candidat Concours", {"candidature": candidature}, "name")


def verifier_autorisation(candidature):
	"""Contrôles avant de passer une candidature à « Autorisé à concourir »."""
	if candidature.mode_admission != "Concours" or not candidature.concours:
		frappe.throw(
			_("Ce dossier est en admission sur dossier : il ne peut pas être autorisé à concourir. "
			  "Aucune des formations demandées n'est au programme d'un concours.")
		)
	statut = frappe.db.get_value("Concours", candidature.concours, "statut")
	if statut not in STATUTS_CONCOURS_INSCRIPTION:
		frappe.throw(
			_("Le concours {0} est au statut « {1} » : on ne peut autoriser des candidats "
			  "qu'aux statuts « Candidatures ouvertes » ou « Épreuves ».").format(candidature.concours, statut)
		)
	if frappe.db.exists("Concours Epreuve", {"parent": candidature.concours, "parenttype": "Concours",
											  "notes_validees": 1}):
		frappe.throw(
			_("Des notes du concours {0} sont déjà validées : on ne peut plus ajouter de candidat.")
			.format(candidature.concours)
		)


def verifier_retrait(candidature):
	"""Un candidat ne peut plus être retiré du concours dès qu'une note est saisie."""
	fiche = fiche_du_candidat(candidature.name)
	if not fiche:
		return
	note_saisie = frappe.db.exists(
		"Candidat Concours Note",
		{"parent": fiche, "parenttype": "Candidat Concours", "saisie_le": ["is", "set"]},
	) or frappe.db.exists(
		"Candidat Concours Note",
		{"parent": fiche, "parenttype": "Candidat Concours", "note": ["!=", 0]},
	) or frappe.db.exists(
		"Candidat Concours Note", {"parent": fiche, "parenttype": "Candidat Concours", "absent": 1}
	)
	if note_saisie:
		frappe.throw(
			_("Des notes sont déjà saisies pour ce candidat au concours ({0}) : "
			  "il ne peut plus être retiré du concours.").format(fiche)
		)


def inscrire_candidat(candidature):
	"""Crée la fiche Candidat Concours : numéro de table, code d'anonymat, une ligne
	de note par épreuve à composer et une ligne de résultat par formation demandée.
	Idempotent : renvoie la fiche existante si le candidat est déjà inscrit."""
	existante = fiche_du_candidat(candidature.name)
	if existante:
		return frappe.get_doc("Candidat Concours", existante)

	# Verrou sur la ligne du concours : numéros de table et codes restent uniques
	# même si plusieurs dossiers sont autorisés en même temps.
	frappe.db.get_value("Concours", candidature.concours, "name", for_update=True)
	concours = frappe.get_doc("Concours", candidature.concours)

	# Les noms de niveau sont numériques (« 20 ») : selon le chemin d'enregistrement,
	# la valeur du choix arrive en int ou en str. On compare donc en texte.
	formations = {(row.filiere, str(row.niveau)) for row in concours.filieres}
	resultats, notes, matieres_vues = [], [], set()
	for choix in candidature.get("choix_de_formation") or []:
		if (choix.filiere, str(choix.niveau)) not in formations:
			continue  # formation hors concours (sur dossier) : ignorée ici
		resultats.append({"choix": choix.choix, "filiere": choix.filiere, "niveau": choix.niveau})
		for epreuve in concours.epreuves_de_filiere(choix.filiere):
			cle = _cle_matiere(epreuve.matiere)
			if cle not in matieres_vues:
				matieres_vues.add(cle)
				notes.append({"matiere": epreuve.matiere})

	fiche = frappe.get_doc({
		"doctype": "Candidat Concours",
		"concours": concours.name,
		"candidature": candidature.name,
		"numero_table": _prochain_numero_table(concours.name, candidature.examination_centre),
		"code_anonymat": _nouveau_code_anonymat(concours.name),
		"notes": notes,
		"resultats": resultats,
	})
	fiche.insert(ignore_permissions=True)
	return fiche


def candidat_non_admis_publie(candidature):
	"""Vrai si le concours du candidat a publié ses résultats, qu'il n'y est pas
	admis et qu'il a demandé une formation hors concours : la scolarité peut alors
	l'accepter sur dossier pour ce choix-là. `candidature` : document."""
	fiche = frappe.db.get_value("Candidat Concours", {"candidature": candidature.name},
								["concours", "decision"], as_dict=True)
	if not fiche or fiche.decision not in ("Non admis", "Absent"):
		return False
	if frappe.db.get_value("Concours", fiche.concours, "statut") not in ("Résultats publiés", "Clôturé"):
		return False
	concours = frappe.get_doc("Concours", fiche.concours)
	formations = {(r.filiere, str(r.niveau)) for r in concours.filieres}
	return any((c.filiere, str(c.niveau)) not in formations for c in candidature.get("choix_de_formation") or [])


def envoyer_resultat_liste_attente(candidature):
	"""E-mail au candidat placé sur liste d'attente, avec son rang par formation."""
	from udshed.api.candidature import get_school_logo_url
	from udshed.udshed.doctype.session_inscription_candidate.session_inscription_candidate import _get_sender

	cand = frappe.get_doc("Session Inscription Candidate", candidature)
	fiche = fiche_du_candidat(candidature)
	if not cand.email or not fiche:
		return False
	fiche = frappe.get_doc("Candidat Concours", fiche)
	formations = []
	for r in fiche.resultats:
		if r.decision == STATUT_LISTE_ATTENTE:
			libelle = frappe.db.get_value("Field of study", r.filiere, "name_of_field") or r.filiere
			niveau = frappe.db.get_value("Field of study Level", r.niveau, "level") or r.niveau
			formations.append({"libelle": f"{libelle} — {niveau}", "rang": r.rang or "—"})
	concours = frappe.db.get_value("Concours", fiche.concours, ["titre", "academic_year"], as_dict=True)
	try:
		from udshed.notifications import emettre

		return bool(emettre(
			"concours_resultat", [{"email": cand.email, "phone": cand.phone}],
			_("Résultats du concours {0} : liste d'attente").format(concours.titre),
			sender=_get_sender(), reference=("Session Inscription Candidate", cand.name),
			template="concours_liste_attente",
			args={
				"first_name": cand.first_name, "last_name": cand.last_name, "doc_name": cand.name,
				"concours": concours.titre, "academic_year": concours.academic_year,
				"formations": formations, "logo_url": get_school_logo_url(),
			},
			now=True,
		))
	except Exception as e:
		frappe.log_error(message=str(e), title=f"Échec e-mail liste d'attente {cand.name}")
		return False


def retirer_candidat(candidature):
	fiche = fiche_du_candidat(candidature.name)
	if fiche:
		frappe.delete_doc("Candidat Concours", fiche, ignore_permissions=True)


def _code_centre(centre):
	"""« Bangangté » -> « BAN ». Préfixe des numéros de table du centre."""
	sans_accent = unicodedata.normalize("NFKD", centre or "").encode("ascii", "ignore").decode()
	lettres = "".join(c for c in sans_accent if c.isalpha()).upper()
	return lettres[:3] or "GEN"


def _prochain_numero_table(concours, centre):
	prefixe = _code_centre(centre)
	existants = frappe.get_all(
		"Candidat Concours",
		filters={"concours": concours, "numero_table": ["like", f"{prefixe}-%"]},
		pluck="numero_table",
	)
	numeros = [int(n.rsplit("-", 1)[1]) for n in existants if n.rsplit("-", 1)[-1].isdigit()]
	return f"{prefixe}-{max(numeros, default=0) + 1:04d}"


def _nouveau_code_anonymat(concours):
	"""Code aléatoire (et non séquentiel) : on ne peut pas le déduire du numéro de table."""
	for _essai in range(50):
		code = "".join(secrets.choice(ALPHABET_ANONYMAT) for _i in range(6))
		if not frappe.db.exists("Candidat Concours", {"concours": concours, "code_anonymat": code}):
			return code
	frappe.throw(_("Impossible de générer un code d'anonymat unique. Réessayez."))


# --------------------------------------------------------------------------- #
#  Convocation
# --------------------------------------------------------------------------- #
def _contexte_convocation(fiche):
	concours = frappe.get_doc("Concours", fiche.concours)
	candidature = frappe.get_doc("Session Inscription Candidate", fiche.candidature)
	matieres = {_cle_matiere(n.matiere) for n in fiche.notes}
	epreuves, vues = [], set()
	for e in concours.epreuves:
		cle = _cle_matiere(e.matiere)
		if cle in matieres and cle not in vues:
			vues.add(cle)
			epreuves.append({
				"matiere": e.matiere,
				"date": frappe.utils.format_datetime(e.date_epreuve, "dd/MM/yyyy à HH:mm") if e.date_epreuve else "",
			})
	formations = []
	for r in fiche.resultats:
		libelle = frappe.db.get_value("Field of study", r.filiere, "name_of_field") or r.filiere
		niveau = frappe.db.get_value("Field of study Level", r.niveau, "level") or r.niveau
		formations.append(f"{r.choix} : {libelle} — {niveau}")
	fmt = lambda d: frappe.utils.formatdate(d, "dd/MM/yyyy") if d else ""  # noqa: E731
	return candidature, {
		"first_name": candidature.first_name,
		"last_name": candidature.last_name,
		"doc_name": candidature.name,
		"concours": concours.titre,
		"academic_year": concours.academic_year,
		"numero_table": fiche.numero_table,
		"centre": fiche.centre_examen or "",
		"date_debut": fmt(concours.date_debut_epreuves),
		"date_fin": fmt(concours.date_fin_epreuves),
		"epreuves": epreuves,
		"formations": formations,
	}


def _nom_etablissement():
	from udshed.utils.etablissement import etablissement

	return etablissement().nom


def envoyer_convocation(fiche_name):
	"""Envoie la convocation. Un échec d'envoi est journalisé sans bloquer l'autorisation."""
	from udshed.api.candidature import get_school_logo_url
	from udshed.udshed.doctype.session_inscription_candidate.session_inscription_candidate import _get_sender

	fiche = frappe.get_doc("Candidat Concours", fiche_name)
	candidature, args = _contexte_convocation(fiche)
	if not candidature.email:
		frappe.logger().warning(f"Pas d'email pour {candidature.name} — convocation non envoyée.")
		return False
	args["logo_url"] = get_school_logo_url()
	try:
		from udshed.notifications import emettre

		return bool(emettre(
			"concours_convocation", [{"email": candidature.email, "phone": candidature.phone}],
			_("Convocation au concours {0} - {1}").format(args["concours"], _nom_etablissement()),
			sender=_get_sender(), reference=("Session Inscription Candidate", candidature.name),
			template="concours_convocation",
			args=args,
			now=True,
		))
	except Exception as e:
		frappe.log_error(message=str(e), title=f"Échec convocation concours {fiche.name}")
		return False


@frappe.whitelist()
def renvoyer_convocation(fiche):
	frappe.has_permission("Candidat Concours", "write", fiche, throw=True)
	if not envoyer_convocation(fiche):
		frappe.throw(_("La convocation n'a pas pu être envoyée. Consultez le journal des erreurs."))
	return True


# --------------------------------------------------------------------------- #
#  Listes d'émargement
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def telecharger_liste_emargement(concours, centre=None):
	"""PDF : une liste par centre (ou celle d'un seul centre), triée par numéro de
	table, avec une case de signature par épreuve. Pas de code d'anonymat."""
	frappe.has_permission("Concours", "read", concours, throw=True)
	doc = frappe.get_doc("Concours", concours)
	filtres = {"concours": concours}
	if centre:
		filtres["centre_examen"] = centre
	fiches = frappe.get_all(
		"Candidat Concours",
		filters=filtres,
		fields=["name", "numero_table", "nom_complet", "centre_examen"],
		order_by="numero_table asc",
	)
	if not fiches:
		frappe.throw(_("Aucun candidat autorisé à concourir pour ces critères."))

	par_centre = {}
	for f in fiches:
		par_centre.setdefault(f.centre_examen or _("Sans centre"), []).append(f)

	epreuves, vues = [], set()
	for e in doc.epreuves:
		if _cle_matiere(e.matiere) not in vues:
			vues.add(_cle_matiere(e.matiere))
			epreuves.append(e.matiere)
	# Matières composées par chaque candidat (une case grisée sinon).
	notes = frappe.get_all(
		"Candidat Concours Note",
		filters={"parenttype": "Candidat Concours", "parent": ["in", [f.name for f in fiches]]},
		fields=["parent", "matiere"],
	)
	compose = {(n.parent, _cle_matiere(n.matiere)) for n in notes}
	for f in fiches:
		f.cases = [(f.name, _cle_matiere(m)) in compose for m in epreuves]

	settings = frappe.get_single("Udshed Setting")
	html = frappe.render_template(
		open(frappe.get_app_path("udshed", "public", "print_templates", "concours_emargement.html"),
			 encoding="utf-8").read(),
		{
			"concours": doc,
			"centres": sorted(par_centre.items()),
			"epreuves": epreuves,
			"school_name": settings.school_name or "",
			"logo_file": "file://" + frappe.get_app_path("udshed", "public", "images", "logo.png"),
			"date_emission": frappe.utils.formatdate(frappe.utils.today(), "dd/MM/yyyy"),
		},
	)
	from weasyprint import HTML

	pdf = HTML(string=html, base_url=frappe.utils.get_url()).write_pdf()
	suffixe = f"_{_code_centre(centre)}" if centre else ""
	frappe.response["filename"] = f"Emargement_{doc.name}{suffixe}.pdf"
	frappe.response["filecontent"] = pdf
	frappe.response["type"] = "download"
	frappe.response["content_type"] = "application/pdf"


@frappe.whitelist()
def centres_du_concours(concours):
	"""Centres et effectifs, pour le bouton « Liste d'émargement »."""
	frappe.has_permission("Concours", "read", concours, throw=True)
	return frappe.get_all(
		"Candidat Concours",
		filters={"concours": concours},
		fields=["centre_examen as centre", {"COUNT": "*", "as": "effectif"}],
		group_by="centre_examen",
		order_by="centre_examen asc",
	)
