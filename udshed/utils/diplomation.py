"""Diplomation : jury de fin de cycle (Licence, Master, BTS).

1. « Rechercher les candidats » : étudiants inscrits (réinscription validée)
   l'année du jury en DERNIÈRE année du cycle de la filière.
2. Pour chacun, le cycle est validé si TOUS les niveaux du cycle sont
   entièrement acquis (unités validées, compensation, jury de délibération,
   acquis antérieurs via équivalences : udshed/utils/acquis.py).
3. Moyenne du cycle = moyenne des MPS des semestres du cycle ; mention LMD.
4. Le jury confirme (ou modifie, motif obligatoire) puis PROCLAME : un
   « Diplome Etudiant » est créé pour chaque diplômé ; attestation de réussite
   et diplôme deviennent disponibles (condition « Diplômé du cycle »).
"""

import frappe

from udshed.utils.compte_etudiant import notifier_etudiant
from udshed.utils.etablissement import nom_etudiant
from frappe import _
from frappe.utils import flt


def mention(moyenne):
	m = flt(moyenne)
	if m >= 18:
		return "Excellent"
	if m >= 16:
		return "Très bien"
	if m >= 14:
		return "Bien"
	if m >= 12:
		return "Assez bien"
	if m >= 10:
		return "Passable"
	return ""


def niveaux_du_cycle(filiere, cycle):
	from udshed.utils.niveaux import cycle_niveau, lignes_filiere

	lignes = [r for r in lignes_filiere(filiere) if cycle_niveau(r.level) == cycle]
	return sorted(lignes, key=lambda r: r.order or 0)


def bilan_cycle(student, filiere, cycle):
	"""Crédits validés / total sur tout le cycle, et moyenne des semestres."""
	from udshed.api.reregistration import _annee_resultats_etudiant
	from udshed.utils.acquis import bilan_niveau

	total = valides = 0.0
	annees, details = set(), []
	for niveau in niveaux_du_cycle(filiere, cycle):
		suivi = frappe.db.exists("Academic Reregistration", {"student": student, "niveau": niveau.level,
															  "filiere": filiere})
		annee = _annee_resultats_etudiant(student, niveau.level) if suivi else None
		if not annee:
			# Niveau jamais suivi (ex. admission directe en L3) : le jury
			# peut déclarer diplômé avec un motif.
			details.append(_("{0} : niveau non suivi dans l'établissement").format(niveau.level))
			total += 1  # niveau jamais suivi : le cycle n'est pas validé
			continue
		annees.add(annee)
		b = bilan_niveau(student, filiere, niveau.name, annee)
		total += b["total"]
		valides += b["valides"]
		if b["valides"] < b["total"]:
			details.append(_("{0} : {1}/{2} crédits").format(niveau.level, b["valides"], b["total"]))
	mps = frappe.get_all("Resultat Semestre", filters={"student": student, "academic_year": ["in", list(annees) or [""]]},
						 pluck="mps")
	moyenne = round(sum(flt(m) for m in mps) / len(mps), 2) if mps else 0
	return {"total": total, "valides": valides, "eligible": bool(total) and valides >= total,
			"moyenne": moyenne, "details": details}


def rechercher_candidats(jury):
	niveaux = niveaux_du_cycle(jury.filiere, jury.cycle)
	if not niveaux:
		frappe.throw(_("La filière {0} n'a aucun niveau du cycle {1}.").format(jury.filiere, jury.cycle))
	dernier = niveaux[-1].level
	etudiants = sorted(set(frappe.get_all(
		"Academic Reregistration",
		filters={"academic_year": jury.academic_year, "filiere": jury.filiere, "niveau": dernier, "statut": "Validée"},
		pluck="student")))
	jury.set("candidats", [])
	for student in etudiants:
		b = bilan_cycle(student, jury.filiere, jury.cycle)
		jury.append("candidats", {
			"student": student,
			"nom": nom_etudiant(student),
			"credits_valides": b["valides"], "credits_total": b["total"], "moyenne": b["moyenne"],
			"eligible": 1 if b["eligible"] else 0,
			"mention": mention(b["moyenne"]) if b["eligible"] else "",
			"decision": "Diplômé" if b["eligible"] else "Ajourné",
			"motif": "" if b["eligible"] else _("Cycle non validé : {0}").format("; ".join(b["details"])),
		})
	return len(etudiants)


def intitule(jury):
	if (jury.intitule_diplome or "").strip():
		return jury.intitule_diplome.strip()
	nom = frappe.db.get_value("Field of study", jury.filiere, "name_of_field") or jury.filiere
	return f"{jury.cycle} en {nom}"


def proclamer(jury):
	if jury.statut == "Proclamé":
		frappe.throw(_("Les résultats de ce jury sont déjà proclamés."))
	for c in jury.candidats:
		if c.decision == "Diplômé" and not c.eligible and not (c.motif or "").strip():
			frappe.throw(_("{0} : cycle non validé ; motivez la décision du jury pour le déclarer diplômé.").format(c.nom))
	diplomes = 0
	for c in jury.candidats:
		if c.decision != "Diplômé":
			continue
		if frappe.db.exists("Diplome Etudiant", {"student": c.student, "cycle": jury.cycle, "statut": "Délivré"}):
			continue
		frappe.get_doc({
			"doctype": "Diplome Etudiant", "student": c.student, "nom": c.nom, "intitule": intitule(jury),
			"cycle": jury.cycle, "filiere": jury.filiere, "academic_year": jury.academic_year,
			"date_jury": jury.date_jury, "jury": jury.name, "moyenne": c.moyenne,
			"mention": c.mention or mention(c.moyenne), "statut": "Délivré",
		}).insert(ignore_permissions=True)
		diplomes += 1
		user = frappe.db.get_value("Student", c.student, "utilisateur")
		notifier_etudiant(user, _("Félicitations : vous êtes diplômé(e) — {0}").format(intitule(jury)))
	bilan = _("{0} diplômé(s) sur {1} candidat(s).").format(diplomes, len(jury.candidats))
	jury.db_set({"statut": "Proclamé", "bilan": bilan})
	return {"diplomes": diplomes, "bilan": bilan}


def annuler(jury):
	if jury.statut != "Proclamé":
		frappe.throw(_("Ce jury n'est pas proclamé."))
	for nom in frappe.get_all("Diplome Etudiant", filters={"jury": jury.name, "statut": "Délivré"}, pluck="name"):
		frappe.db.set_value("Diplome Etudiant", nom, "statut", "Annulé")
	jury.db_set({"statut": "Brouillon", "bilan": _("Proclamation annulée.")})
