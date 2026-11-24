# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt
"""Concours d'entrée — phase 3 : saisie anonyme des notes, validation par épreuve,
levée de l'anonymat, calcul des moyennes, classement par filière et PV provisoire.

Règles :
  * les notes se saisissent par code d'anonymat ; la page de saisie ne montre
	jamais le nom ni le numéro de table ;
  * un correcteur ne saisit que les épreuves qui lui sont confiées (ou toutes si
	l'épreuve n'a pas de correcteur désigné) ; la scolarité saisit tout ;
  * une épreuve validée n'est plus modifiable ; l'anonymat ne se lève que quand
	toutes les épreuves sont validées, et le concours passe alors en Délibération ;
  * le classement place chaque candidat dans le meilleur de ses choix où il est
	classé en rang utile (affectation par ordre de préférence) ; les autres
	formations où il reste classé le mettent en liste d'attente.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime

from udshed.udshed.doctype.concours.concours import _cle_matiere

ROLES_SCOLARITE = ("System Manager", "Registration Manager")
ROLE_CORRECTEUR = "Correcteur"
ORDRE_CHOIX = {"1er choix": 1, "2nd Choix": 2, "3ieme Choix": 3}
REGLE_JURY = "Décision du jury"
REGLE_COEFFICIENT = "Meilleure note à l'épreuve de plus fort coefficient"
REGLE_AGE = "Candidat le plus jeune"


# --------------------------------------------------------------------------- #
#  Droits
# --------------------------------------------------------------------------- #
def _est_scolarite():
	return bool(set(frappe.get_roles()) & set(ROLES_SCOLARITE))


def _exiger_scolarite():
	if not _est_scolarite():
		frappe.throw(_("Action réservée au service de la scolarité."), frappe.PermissionError)


def _matieres(concours):
	"""Matières du concours dans l'ordre du tableau des épreuves, une entrée par
	matière même si elle est déclinée par filière (une seule note par candidat)."""
	matieres = {}
	for e in concours.epreuves:
		m = matieres.setdefault(
			_cle_matiere(e.matiere),
			{"cle": _cle_matiere(e.matiere), "matiere": e.matiere, "correcteurs": set(), "lignes": [], "validee": True},
		)
		if e.correcteur:
			m["correcteurs"].add(e.correcteur)
		m["lignes"].append(e)
		m["validee"] = m["validee"] and bool(e.notes_validees)
	return matieres


def _peut_saisir(matiere):
	if _est_scolarite():
		return True
	if ROLE_CORRECTEUR not in frappe.get_roles():
		return False
	return not matiere["correcteurs"] or frappe.session.user in matiere["correcteurs"]


def _matiere_ou_erreur(concours, matiere):
	m = _matieres(concours).get(_cle_matiere(matiere))
	if not m:
		frappe.throw(_("L'épreuve « {0} » n'existe pas dans le concours {1}.").format(matiere, concours.name))
	return m


def _note_saisie(row):
	return bool(row.absent or row.saisie_le)


# --------------------------------------------------------------------------- #
#  Saisie des notes (page « Saisie des notes du concours »)
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def concours_pour_saisie():
	"""Concours en cours d'épreuves et matières que l'utilisateur peut saisir."""
	resultat = []
	for nom in frappe.get_all("Concours", filters={"statut": ["in", ["Épreuves", "Délibération"]]},
							  order_by="creation desc", pluck="name"):
		doc = frappe.get_doc("Concours", nom)
		matieres = [
			{"matiere": m["matiere"], "validee": m["validee"], "peut_saisir": _peut_saisir(m)}
			for m in _matieres(doc).values()
		]
		matieres = [m for m in matieres if m["peut_saisir"]]
		if matieres:
			resultat.append({"name": doc.name, "titre": doc.titre, "statut": doc.statut,
							 "anonymat_leve": doc.anonymat_leve, "matieres": matieres})
	return {"concours": resultat, "scolarite": _est_scolarite()}


def _lignes_de_notes(concours_name, cle):
	fiches = frappe.get_all("Candidat Concours", {"concours": concours_name}, pluck="name")
	if not fiches:
		return []
	notes = frappe.get_all(
		"Candidat Concours Note",
		filters={"parenttype": "Candidat Concours", "parent": ["in", fiches]},
		fields=["name", "parent", "matiere", "note", "absent", "saisie_le"],
	)
	return [n for n in notes if _cle_matiere(n.matiere) == cle]


@frappe.whitelist()
def charger_copies(concours, matiere):
	"""Copies d'une épreuve : code d'anonymat et note uniquement."""
	doc = frappe.get_doc("Concours", concours)
	m = _matiere_ou_erreur(doc, matiere)
	if not _peut_saisir(m):
		frappe.throw(_("Vous n'êtes pas correcteur de l'épreuve « {0} ».").format(m["matiere"]), frappe.PermissionError)
	codes = dict(frappe.get_all("Candidat Concours", {"concours": concours}, ["name", "code_anonymat"], as_list=True))
	copies = [
		{
			"code": codes.get(n.parent),
			"note": n.note if n.saisie_le and not n.absent else None,
			"absent": n.absent,
			"saisie": _note_saisie(n),
		}
		for n in _lignes_de_notes(concours, m["cle"])
	]
	copies.sort(key=lambda c: c["code"] or "")
	return {
		"matiere": m["matiere"],
		"validee": m["validee"],
		"modifiable": doc.statut == "Épreuves" and not m["validee"] and not doc.anonymat_leve,
		"copies": copies,
		"total": len(copies),
		"saisies": sum(1 for c in copies if c["saisie"]),
		"absents": sum(1 for c in copies if c["absent"]),
	}


@frappe.whitelist()
def enregistrer_notes(concours, matiere, notes):
	"""notes : liste de {code, note, absent}. Une note vide efface la saisie."""
	notes = frappe.parse_json(notes) if isinstance(notes, str) else notes
	doc = frappe.get_doc("Concours", concours)
	m = _matiere_ou_erreur(doc, matiere)
	if not _peut_saisir(m):
		frappe.throw(_("Vous n'êtes pas correcteur de l'épreuve « {0} ».").format(m["matiere"]), frappe.PermissionError)
	if doc.statut != "Épreuves" or doc.anonymat_leve:
		frappe.throw(_("Le concours est au statut « {0} » : les notes ne sont plus modifiables.").format(doc.statut))
	if m["validee"]:
		frappe.throw(_("Les notes de « {0} » sont validées : demandez à la scolarité d'annuler la validation.")
					 .format(m["matiere"]))

	codes = dict(frappe.get_all("Candidat Concours", {"concours": concours}, ["name", "code_anonymat"], as_list=True))
	par_code = {codes.get(n.parent): n for n in _lignes_de_notes(concours, m["cle"])}

	maintenant, modifiees = now_datetime(), 0
	for ligne in notes or []:
		code = (ligne.get("code") or "").strip().upper()
		row = par_code.get(code)
		if not row:
			frappe.throw(_("Code d'anonymat inconnu pour cette épreuve : {0}").format(code or "?"))
		absent = 1 if ligne.get("absent") else 0
		valeur = ligne.get("note")
		valeur = None if valeur in (None, "") or absent else flt(str(valeur).replace(",", "."))
		if valeur is not None and not (0 <= valeur <= 20):
			frappe.throw(_("Code {0} : la note doit être comprise entre 0 et 20.").format(code))
		saisie = absent or valeur is not None
		frappe.db.set_value("Candidat Concours Note", row.name, {
			"note": valeur or 0,
			"absent": absent,
			"saisie_par": frappe.session.user if saisie else None,
			"saisie_le": maintenant if saisie else None,
		}, update_modified=False)
		modifiees += 1
	return {"enregistrees": modifiees}


@frappe.whitelist()
def valider_notes(concours, matiere):
	"""Fige les notes d'une épreuve. Toutes les copies doivent être saisies."""
	_exiger_scolarite()
	doc = frappe.get_doc("Concours", concours)
	m = _matiere_ou_erreur(doc, matiere)
	if doc.statut != "Épreuves":
		frappe.throw(_("On ne valide des notes qu'au statut « Épreuves »."))
	lignes = _lignes_de_notes(concours, m["cle"])
	if not lignes:
		frappe.throw(_("Aucune copie pour « {0} ».").format(m["matiere"]))
	manquantes = sum(1 for n in lignes if not _note_saisie(n))
	if manquantes:
		frappe.throw(_("{0} copie(s) de « {1} » n'ont ni note ni absence : complétez la saisie avant de valider.")
					 .format(manquantes, m["matiere"]))
	maintenant = now_datetime()
	for e in m["lignes"]:
		frappe.db.set_value("Concours Epreuve", e.name, {"notes_validees": 1, "validees_le": maintenant})
	return True


@frappe.whitelist()
def annuler_validation(concours, matiere):
	_exiger_scolarite()
	doc = frappe.get_doc("Concours", concours)
	m = _matiere_ou_erreur(doc, matiere)
	if doc.anonymat_leve:
		frappe.throw(_("L'anonymat est levé : les notes ne peuvent plus être rouvertes."))
	for e in m["lignes"]:
		frappe.db.set_value("Concours Epreuve", e.name, {"notes_validees": 0, "validees_le": None})
	return True


@frappe.whitelist()
def etat_saisie(concours):
	"""Avancement de la saisie, par matière (pour le formulaire du concours)."""
	frappe.has_permission("Concours", "read", concours, throw=True)
	doc = frappe.get_doc("Concours", concours)
	etat = []
	for m in _matieres(doc).values():
		lignes = _lignes_de_notes(concours, m["cle"])
		etat.append({"matiere": m["matiere"], "total": len(lignes),
					 "saisies": sum(1 for n in lignes if _note_saisie(n)), "validee": m["validee"]})
	return etat


# --------------------------------------------------------------------------- #
#  Levée de l'anonymat
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def lever_anonymat(concours):
	_exiger_scolarite()
	doc = frappe.get_doc("Concours", concours)
	if doc.anonymat_leve:
		frappe.throw(_("L'anonymat est déjà levé."))
	if doc.statut != "Épreuves":
		frappe.throw(_("L'anonymat se lève au statut « Épreuves » (statut actuel : {0}).").format(doc.statut))
	if not frappe.db.exists("Candidat Concours", {"concours": concours}):
		frappe.throw(_("Aucun candidat au concours."))
	non_validees = [m["matiere"] for m in _matieres(doc).values() if not m["validee"]]
	if non_validees:
		frappe.throw(_("Validez d'abord les notes de : {0}.").format(", ".join(non_validees)))
	doc.anonymat_leve = 1
	doc.anonymat_leve_le = now_datetime()
	doc.anonymat_leve_par = frappe.session.user
	doc.statut = "Délibération"
	doc.save()
	return True


# --------------------------------------------------------------------------- #
#  Moyennes et classement
# --------------------------------------------------------------------------- #
def _evaluer(concours, filiere, notes):
	"""Moyenne pondérée d'un candidat pour une filière, et motif d'élimination."""
	somme = poids = 0.0
	motifs = []
	for e in concours.epreuves_de_filiere(filiere):
		n = notes.get(_cle_matiere(e.matiere))
		coef = flt(e.coefficient)
		poids += coef
		if not n or n.absent:
			motifs.append(_("Absent en {0}").format(e.matiere))
			continue
		somme += flt(n.note) * coef
		if flt(e.note_eliminatoire) and flt(n.note) < flt(e.note_eliminatoire):
			motifs.append(_("Note éliminatoire en {0} ({1})").format(e.matiere, flt(n.note)))
	moyenne = round(somme / poids, 2) if poids else 0
	return moyenne, motifs


def _cle_departage(concours, filiere, notes, naissance):
	"""Critère secondaire selon la règle du concours (plus petit = mieux classé)."""
	if concours.regle_departage == REGLE_COEFFICIENT:
		epreuves = concours.epreuves_de_filiere(filiere)
		if epreuves:
			principale = max(epreuves, key=lambda e: flt(e.coefficient))
			n = notes.get(_cle_matiere(principale.matiere))
			return -(flt(n.note) if n and not n.absent else 0)
	if concours.regle_departage == REGLE_AGE and naissance:
		return -getdate(naissance).toordinal()  # le plus jeune est né le plus tard
	return 0


@frappe.whitelist()
def calculer_classement(concours):
	"""Calcule moyennes, rangs et propositions (Admis / Liste d'attente / Non admis)."""
	_exiger_scolarite()
	doc = frappe.get_doc("Concours", concours)
	if not doc.anonymat_leve or doc.statut != "Délibération":
		frappe.throw(_("Le classement se calcule après la levée de l'anonymat, au statut « Délibération »."))

	fiches = frappe.get_all("Candidat Concours", {"concours": concours}, ["name", "candidature", "numero_table"])
	naissances = dict(frappe.get_all(
		"Session Inscription Candidate", {"name": ["in", [f.candidature for f in fiches] or [""]]},
		["name", "birthdate"], as_list=True,
	))
	formations = {(r.filiere, str(r.niveau)): r for r in doc.filieres}
	lignes = []  # une entrée par (candidat, formation demandée)
	for f in fiches:
		fiche = frappe.get_doc("Candidat Concours", f.name)
		notes = {_cle_matiere(n.matiere): n for n in fiche.notes}
		for r in fiche.resultats:
			cle_formation = (r.filiere, str(r.niveau))
			if cle_formation not in formations:
				continue
			moyenne, motifs = _evaluer(doc, r.filiere, notes)
			seuil = doc.moyenne_minimale_de(r.filiere, r.niveau)
			lignes.append(frappe._dict(
				row=r.name, fiche=f.name, table=f.numero_table or "", formation=cle_formation,
				ordre=ORDRE_CHOIX.get(r.choix, 9), moyenne=moyenne, elimine=bool(motifs),
				motif="; ".join(motifs) if motifs else (
					_("Moyenne inférieure au seuil ({0})").format(seuil) if moyenne < seuil else ""),
				classable=not motifs and moyenne >= seuil,
				departage=_cle_departage(doc, r.filiere, notes, naissances.get(f.candidature)),
			))

	cle_tri = lambda l: (-l.moyenne, l.departage)  # noqa: E731
	# Affectation par ordre de préférence (Gale-Shapley côté candidat) : chaque
	# candidat demande ses formations dans l'ordre de ses choix ; une formation
	# garde les meilleurs dans la limite de ses places.
	voeux = {}
	for l in lignes:
		if l.classable:
			voeux.setdefault(l.fiche, []).append(l)
	for v in voeux.values():
		v.sort(key=lambda l: l.ordre)
	retenus = {k: [] for k in formations}
	prochain = {fiche: 0 for fiche in voeux}
	libres = list(voeux)
	while libres:
		fiche = libres.pop()
		if prochain[fiche] >= len(voeux[fiche]):
			continue
		voeu = voeux[fiche][prochain[fiche]]
		prochain[fiche] += 1
		places = int(formations[voeu.formation].places or 0)
		liste = sorted(retenus[voeu.formation] + [voeu], key=lambda l: (cle_tri(l), l.table))
		retenus[voeu.formation], rejetes = liste[:places], liste[places:]
		libres.extend(l.fiche for l in rejetes)

	admis = {l.fiche: l.formation for liste in retenus.values() for l in liste}
	ordre_admis = {l.fiche: l.ordre for liste in retenus.values() for l in liste}
	resume = []
	for formation, conf in formations.items():
		de_la_formation = [l for l in lignes if l.formation == formation]
		classables = sorted([l for l in de_la_formation if not l.elimine], key=lambda l: (cle_tri(l), l.table))
		# Rang « sportif » : deux candidats à égalité parfaite ont le même rang.
		rang, precedent = 0, None
		for i, l in enumerate(classables, start=1):
			if cle_tri(l) != precedent:
				rang, precedent = i, cle_tri(l)
			l.rang = rang
		dernier_admis = retenus[formation][-1] if retenus[formation] else None
		for l in de_la_formation:
			if admis.get(l.fiche) == formation:
				l.proposition = "Admis"
			elif not l.classable:
				l.proposition = "Non admis"  # éliminé ou sous le seuil : le motif l'explique
			elif admis.get(l.fiche) and ordre_admis[l.fiche] < l.ordre:
				l.proposition = ""
				l.motif = _("Admis sur un choix prioritaire")
			else:
				l.proposition = "Liste d'attente"
		# Ex æquo à départager par le jury : égalité parfaite entre le dernier admis
		# et au moins un candidat resté en liste d'attente.
		for l in de_la_formation:
			l.ex_aequo = bool(
				doc.regle_departage == REGLE_JURY and dernier_admis and l.classable
				and cle_tri(l) == cle_tri(dernier_admis)
				and any(cle_tri(x) == cle_tri(dernier_admis) and x.proposition == "Liste d'attente"
						for x in de_la_formation)
			)
		for l in de_la_formation:
			frappe.db.set_value("Candidat Concours Resultat", l.row, {
				"moyenne": l.moyenne, "rang": l.rang or 0, "elimine": int(l.elimine),
				"motif": l.motif, "proposition": l.proposition, "ex_aequo": int(l.ex_aequo),
			}, update_modified=False)
		resume.append({
			"filiere": formation[0], "niveau": conf.niveau, "places": conf.places,
			"candidats": len(de_la_formation),
			"admis": sum(1 for l in de_la_formation if l.proposition == "Admis"),
			"attente": sum(1 for l in de_la_formation if l.proposition == "Liste d'attente"),
			"non_admis": sum(1 for l in de_la_formation if l.proposition == "Non admis"),
			"ex_aequo": sum(1 for l in de_la_formation if l.ex_aequo),
		})
	doc.db_set("classement_calcule_le", now_datetime())
	return resume


# --------------------------------------------------------------------------- #
#  PV : classement provisoire (phase 3) et délibération (phase 4)
# --------------------------------------------------------------------------- #
ORDRE_PROPOSITION = {"Admis": 0, "Liste d'attente": 1, "": 2, "Désisté": 3, "Non admis": 4}


@frappe.whitelist()
def telecharger_pv_classement(concours, filiere=None):
	_exiger_scolarite()
	doc = frappe.get_doc("Concours", concours)
	if not doc.classement_calcule_le:
		frappe.throw(_("Calculez d'abord le classement."))
	_pdf_pv(doc, filiere, final=False)


def _pdf_pv(doc, filiere=None, final=False):
	"""PV par filière. final=False : propositions du classement ; final=True :
	décisions du jury (PV de délibération)."""
	concours = doc.name
	colonne = "decision" if final else "proposition"
	fiches = {f.name: f for f in frappe.get_all(
		"Candidat Concours", {"concours": concours}, ["name", "numero_table", "nom_complet", "centre_examen", "motif_desistement"])}
	notes = {}
	for n in frappe.get_all("Candidat Concours Note",
							{"parenttype": "Candidat Concours", "parent": ["in", list(fiches) or [""]]},
							["parent", "matiere", "note", "absent"]):
		notes[(n.parent, _cle_matiere(n.matiere))] = "ABS" if n.absent else f"{flt(n.note):.2f}"
	resultats = frappe.get_all(
		"Candidat Concours Resultat", {"parenttype": "Candidat Concours", "parent": ["in", list(fiches) or [""]]},
		["parent", "choix", "filiere", "niveau", "moyenne", "rang", "elimine", "motif", "proposition",
		 "ex_aequo", "decision"],
	)

	sections = []
	for conf in doc.filieres:
		if filiere and conf.filiere != filiere:
			continue
		epreuves = [{"matiere": e.matiere, "coefficient": e.coefficient} for e in doc.epreuves_de_filiere(conf.filiere)]
		lignes = []
		for r in resultats:
			if r.filiere != conf.filiere or str(r.niveau) != str(conf.niveau):
				continue
			f = fiches[r.parent]
			lignes.append({
				**r, "numero_table": f.numero_table, "nom_complet": f.nom_complet, "centre": f.centre_examen,
				"notes": [notes.get((r.parent, _cle_matiere(e["matiere"])), "") for e in epreuves],
				"verdict": r.get(colonne) or "",
			})
			if lignes[-1]["verdict"] == "Désisté" and f.motif_desistement:
				lignes[-1]["motif"] = _("Désistement : {0}").format(f.motif_desistement)
		lignes.sort(key=lambda l: (ORDRE_PROPOSITION.get(l["verdict"], 2), l["rang"] or 9999,
								   -(l["moyenne"] or 0), l["numero_table"] or ""))
		sections.append({
			"filiere": conf.filiere,
			"libelle": frappe.db.get_value("Field of study", conf.filiere, "name_of_field") or conf.filiere,
			"niveau": frappe.db.get_value("Field of study Level", conf.niveau, "level") or conf.niveau,
			"places": conf.places,
			"seuil": doc.moyenne_minimale_de(conf.filiere, conf.niveau),
			"epreuves": epreuves,
			"lignes": lignes,
			"admis": sum(1 for l in lignes if l["verdict"] == "Admis"),
			"attente": sum(1 for l in lignes if l["verdict"] == "Liste d'attente"),
			"desistes": sum(1 for l in lignes if l["verdict"] == "Désisté"),
			"ex_aequo": 0 if final else sum(1 for l in lignes if l["ex_aequo"]),
		})
	if not sections:
		frappe.throw(_("Aucune filière ne correspond."))

	settings = frappe.get_single("Udshed Setting")
	html = frappe.render_template(
		open(frappe.get_app_path("udshed", "public", "print_templates", "concours_pv_classement.html"),
			 encoding="utf-8").read(),
		{
			"concours": doc,
			"sections": sections,
			"final": final,
			"publie": doc.statut in ("Résultats publiés", "Clôturé"),
			"membres_jury": [m.strip() for m in (doc.membres_jury or "").splitlines() if m.strip()],
			"school_name": settings.school_name or "",
			"logo_file": "file://" + frappe.get_app_path("udshed", "public", "images", "logo.png"),
			"date_emission": frappe.utils.formatdate(frappe.utils.today(), "dd/MM/yyyy"),
			"calcule_le": frappe.utils.format_datetime(doc.classement_calcule_le, "dd/MM/yyyy à HH:mm"),
			"date_deliberation": frappe.utils.formatdate(doc.date_deliberation, "dd/MM/yyyy") if doc.date_deliberation else "",
		},
	)
	from weasyprint import HTML

	pdf = HTML(string=html, base_url=frappe.utils.get_url()).write_pdf()
	prefixe = "PV_deliberation" if final else "PV_classement_provisoire"
	frappe.response["filename"] = f"{prefixe}_{doc.name}{'_' + filiere if filiere else ''}.pdf"
	frappe.response["filecontent"] = pdf
	frappe.response["type"] = "download"
	frappe.response["content_type"] = "application/pdf"
