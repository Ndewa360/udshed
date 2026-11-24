"""Moteur de calcul du module Insight (source unique de vérité).

Toutes les statistiques (avancement pédagogique et coût des vacations) sont
calculées ici, à partir de données chargées en quelques requêtes.

Règles
------
Cours (Teaching Unit)
  Le volume de référence (« cible ») est celui du cours DE L'ANNÉE :
  CM + TD + TP du Teaching Unit (modifiable dans la grille), jamais celui du
  catalogue Course. Le TPE (travail personnel) n'est pas une heure encadrée.

Séances (Planning Item)
  Types normalisés : CM, TD, TP (heures de cours) ; CC, EXAMEN, RATTRAPAGE
  (évaluations, comptées à part, ni dans les heures ni dans la paie).
  - planifiée : toute séance non annulée ;
  - échue     : séance non annulée dont l'heure de fin est passée ;
  - pointée   : séance marquée « Fait » ;
  - annulée   : séance marquée « Annulée » (ignorée partout).
  Les durées sont exactes (minutes), sans troncature.

Cours liés (groupe de cours commun)
  Une séance planifiée via un cours du groupe compte pour CHAQUE cours du
  groupe (c'est le même enseignement) : progression identique à celle du
  planning.

Statut d'un cours
  sans_volume (cible nulle), non_planifie, en_cours, termine, depassement ;
  indicateurs : en_retard (réalisé < avancement attendu du semestre − 20 pts),
  planning_incomplet (planifié < cible), surplanifie (planifié > cible).

Finance (vacations)
  - seuls les enseignants « Vacataire » sont rémunérés ; les permanents ont
    un coût nul (heures de service) ;
  - tarif horaire par grade (Udshed Setting), clé = titre de l'enseignant,
    à défaut déduite de son grade ; un tarif manquant produit une alerte ;
  - plusieurs enseignants sur un même type (ex. deux CM) se partagent les
    heures : le tarif d'une heure est la moyenne de leurs tarifs ;
  - coût d'une séance = durée × tarif moyen du type, calculé UNE fois, puis
    réparti à parts égales entre les classes servies (tronc commun / cours
    liés) : les montants par classe, filière ou faculté s'additionnent ;
  - budget d'un enseignement (groupe de cours liés ou cours seul) = volume ×
    tarif, compté une fois, réparti de même entre ses classes.
"""

import calendar
import unicodedata
from datetime import date, datetime, timedelta

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime

TYPES_COURS = ("CM", "TD", "TP")
TYPES_EVALUATION = ("CC", "EXAMEN", "RATTRAPAGE")
LIBELLES_TYPES = {
	"CM": "Cours magistral (CM)", "TD": "Travaux dirigés (TD)", "TP": "Travaux pratiques (TP)",
	"CC": "Contrôle continu", "EXAMEN": "Examen", "RATTRAPAGE": "Rattrapage", "AUTRE": "Autre",
}
CHAMP_HEURES = {"CM": "nombre_dheure_cm", "TD": "nombre_dheure_td", "TP": "nombre_dheure_tp"}
STATUT_FAIT = "Fait"
STATUT_ANNULE = "Annulée"
SEUIL_RETARD = 0.20
MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
        "septembre", "octobre", "novembre", "decembre"]
# Correspondance grade -> titre de rémunération quand le titre n'est pas renseigné.
TITRE_PAR_GRADE = {"Pr": "Professeur", "Dr": "Chargé de Cours"}


def _sans_accents(texte):
	return unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode().lower()


def type_seance(libelle):
	"""« Traveaux Dirigés (TD) », « Travaux Dirigés (TD) », « TD »… -> code normalisé."""
	t = _sans_accents(libelle)
	if "rattrapage" in t:
		return "RATTRAPAGE"
	if "(cc)" in t or "controle" in t or "controlle" in t:
		return "CC"
	if "examen" in t:
		return "EXAMEN"
	for code in TYPES_COURS:
		if f"({code.lower()})" in t or t.strip() == code.lower():
			return code
	if t.startswith("cours"):
		return "CM"
	return "AUTRE"


def _minutes(valeur):
	if isinstance(valeur, timedelta):
		return valeur.total_seconds() / 60
	if hasattr(valeur, "hour"):
		return valeur.hour * 60 + valeur.minute
	parties = str(valeur or "0:0").split(":")
	try:
		return int(parties[0]) * 60 + int(parties[1])
	except (ValueError, IndexError):
		return 0


def _pct(numerateur, denominateur):
	return round(100.0 * numerateur / denominateur, 1) if denominateur else 0.0


# ---------------------------------------------------------------------------
# Bornes des semestres
# ---------------------------------------------------------------------------
def bornes_annee(academic_year):
	"""(début, fin) de l'année académique d'après ses mois et années."""
	doc = frappe.db.get_value(
		"Academic Year", academic_year, ["start_month", "start_year", "end_month", "end_year"], as_dict=True
	)
	if not doc or not doc.start_year or not doc.end_year:
		return None
	def mois(nom, defaut):
		# Correspondance exacte après normalisation (« Févriér » -> « fevrier ») :
		# comparer des préfixes confondrait juin et juillet.
		cle = _sans_accents(nom).strip()
		return MOIS.index(cle) + 1 if cle in MOIS else defaut
	m_debut, m_fin = mois(doc.start_month, 9), mois(doc.end_month, 6)
	debut = date(int(doc.start_year), m_debut, 1)
	fin = date(int(doc.end_year), m_fin, calendar.monthrange(int(doc.end_year), m_fin)[1])
	return (debut, fin) if fin > debut else None


def bornes_semestre(academic_year, semestre, cache=None):
	"""Semestre 1 = première moitié de l'année, semestre 2 = seconde moitié."""
	cache = {} if cache is None else cache
	if academic_year not in cache:
		cache[academic_year] = bornes_annee(academic_year)
	annee = cache[academic_year]
	if not annee:
		return None
	debut, fin = annee
	milieu = debut + (fin - debut) / 2
	if semestre == "Semestre 1":
		return debut, milieu
	if semestre == "Semestre 2":
		return milieu, fin
	return debut, fin


def avancement_attendu(bornes, aujourd_hui=None):
	"""Part de la période écoulée (0 à 1)."""
	if not bornes:
		return None
	debut, fin = bornes
	aujourd_hui = aujourd_hui or getdate()
	if aujourd_hui <= debut:
		return 0.0
	if aujourd_hui >= fin:
		return 1.0
	return (aujourd_hui - debut).days / max(1, (fin - debut).days)


# ---------------------------------------------------------------------------
# Chargement des données
# ---------------------------------------------------------------------------
class Donnees:
	"""Données brutes d'une année académique, chargées en lot."""

	def __init__(self, academic_year, semestre=None):
		self.academic_year = academic_year
		self.semestre = semestre
		self.cours = {}          # tu -> dict (classes, heures, groupe…)
		self.classes = {}        # (filiere, niveau) -> dict (libellés, faculté)
		self.enseignants = {}    # teacher -> dict (nom, statut, titre)
		self.affectations = {}   # tu -> [(teacher, type)]
		self.seances = []        # dicts
		self.tarifs = {}         # titre -> prix horaire
		self._charger()

	def _charger(self):
		avec_groupe = frappe.db.has_column("Teaching Unit", "groupe_cours_commun")
		condition_semestre = "AND tu.semestre = %(semestre)s" if self.semestre else ""
		lignes = frappe.db.sql(
			f"""
			SELECT tu.name, tu.course, tu.intitule_cours, tu.semestre,
			       tu.nombre_dheure_cm, tu.nombre_dheure_td, tu.nombre_dheure_tp,
			       {"tu.groupe_cours_commun" if avec_groupe else "NULL"} AS groupe,
			       l.filiere, l.niveau, fs.name_of_field, fs.faculte, fl.level, fac.faculty_name
			FROM `tabTeaching Unit` tu
			INNER JOIN `tabCourse Field of study level item` l ON l.parent = tu.name AND l.parenttype = 'Teaching Unit'
			INNER JOIN `tabField of study` fs ON fs.name = l.filiere
			LEFT JOIN `tabField of study Level` fl ON fl.name = l.niveau
			LEFT JOIN `tabFaculty` fac ON fac.name = fs.faculte
			WHERE tu.academic_year = %(annee)s {condition_semestre}
			""",
			{"annee": self.academic_year, "semestre": self.semestre},
			as_dict=True,
		)
		for l in lignes:
			classe = (l.filiere, str(l.niveau))
			self.classes.setdefault(classe, {
				"filiere": l.filiere, "niveau": str(l.niveau),
				"filiere_libelle": l.name_of_field or l.filiere,
				"niveau_libelle": l.level or str(l.niveau),
				"faculte": l.faculte, "faculte_libelle": l.faculty_name or l.faculte or _("(sans faculté)"),
				"libelle": f"{l.name_of_field or l.filiere} — {l.level or l.niveau}",
			})
			c = self.cours.setdefault(l.name, {
				"name": l.name, "code": l.course, "intitule": l.intitule_cours or l.course,
				"semestre": l.semestre, "groupe": l.groupe or None, "classes": [],
				"heures": {t: flt(l.get(CHAMP_HEURES[t])) for t in TYPES_COURS},
			})
			if classe not in c["classes"]:
				c["classes"].append(classe)

		noms = list(self.cours)
		if noms:
			for a in frappe.get_all(
				"Course Teacher Item",
				filters={"parent": ["in", noms], "parenttype": "Teaching Unit"},
				fields=["parent", "enseignant", "type_de_cours"],
			):
				if a.enseignant:
					self.affectations.setdefault(a.parent, []).append((a.enseignant, type_seance(a.type_de_cours)))
		ids = sorted({e for lst in self.affectations.values() for e, _t in lst})
		if ids:
			for t in frappe.get_all(
				"Teacher", filters={"name": ["in", ids]},
				fields=["name", "full_name", "first_name", "last_name", "grade", "titre", "status"],
			):
				nom = t.full_name or " ".join(filter(None, [t.grade, t.first_name, t.last_name])) or t.name
				titre = t.titre or TITRE_PAR_GRADE.get(t.grade)
				self.enseignants[t.name] = {
					"name": t.name, "nom": nom, "titre": titre, "grade": t.grade,
					"vacataire": (t.status or "").strip().lower() != "permanent",
					"statut": t.status or "",
				}

		setting = frappe.get_single("Udshed Setting")
		for ligne in setting.get("configuration_des_paiements_par_grade") or []:
			if ligne.grade and ligne.grade not in self.tarifs:
				self.tarifs[ligne.grade] = flt(ligne.prix_heure)
		self.devise = setting.get("devise") or frappe.db.get_default("currency") or "XAF"

		# Groupes : membres d'un même enseignement (cours liés), dans l'année.
		self.groupes = {}
		for nom, c in self.cours.items():
			self.groupes.setdefault(c["groupe"] or nom, []).append(nom)
		self.groupe_de = {nom: (c["groupe"] or nom) for nom, c in self.cours.items()}

		if not noms:
			return
		items = frappe.get_all(
			"Planning Item",
			filters={"academic_year": self.academic_year, "cours": ["in", noms]},
			fields=["name", "cours", "type", "date", "period", "status"],
		)
		periodes = {}
		ids_periodes = sorted({i.period for i in items if i.period})
		if ids_periodes:
			for p in frappe.get_all(
				"Planning Period", filters={"name": ["in", ids_periodes]},
				fields=["name", "heure_de_debut", "heure_de_fin"],
			):
				periodes[p.name] = (_minutes(p.heure_de_debut), _minutes(p.heure_de_fin))
		maintenant = now_datetime()
		for i in items:
			debut_min, fin_min = periodes.get(i.period, (0, 0))
			jour = getdate(i.date) if i.date else None
			fin_dt = datetime.combine(jour, datetime.min.time()) + timedelta(minutes=fin_min) if jour else None
			annulee = (i.status or "") == STATUT_ANNULE
			self.seances.append({
				"name": i.name, "cours": i.cours, "type": type_seance(i.type), "date": jour,
				"minutes": max(0.0, fin_min - debut_min),
				"annulee": annulee,
				"echue": bool(fin_dt and fin_dt <= maintenant and not annulee),
				"faite": (i.status or "") == STATUT_FAIT,
			})

	# -- outils --------------------------------------------------------------
	def classes_du_groupe(self, tu):
		classes = []
		for membre in self.groupes.get(self.groupe_de.get(tu, tu), [tu]):
			for c in self.cours[membre]["classes"]:
				if c not in classes:
					classes.append(c)
		return classes

	def tarif(self, teacher):
		"""(tarif horaire, alerte éventuelle) d'un enseignant ; 0 pour un permanent."""
		info = self.enseignants.get(teacher)
		if not info:
			return 0.0, None
		if not info["vacataire"]:
			return 0.0, None
		if info["titre"] in self.tarifs:
			return self.tarifs[info["titre"]], None
		return 0.0, info["titre"] or _("(titre non renseigné)")

	def profs(self, tu, type_code):
		"""Enseignants assurant `type_code` pour cet enseignement : ceux du cours et
		de ses cours liés (la séance commune peut être assurée par l'un d'eux)."""
		vus = []
		for membre in self.groupes.get(self.groupe_de.get(tu, tu), [tu]):
			for e, t in self.affectations.get(membre, []):
				if t == type_code and e not in vus:
					vus.append(e)
		return vus

	def tarif_moyen(self, tu, type_code):
		"""Tarif d'une heure de `type_code` (moyenne des enseignants qui se la partagent)."""
		profs = self.profs(tu, type_code)
		if not profs:
			return 0.0
		return sum(self.tarif(e)[0] for e in profs) / len(profs)

	def budget_cours(self, tu):
		c = self.cours[tu]
		return sum(c["heures"][t] * self.tarif_moyen(tu, t) for t in TYPES_COURS)


# ---------------------------------------------------------------------------
# Calcul
# ---------------------------------------------------------------------------
def calculer(donnees, classes_retenues=None, enseignant=None, type_filtre=None, aujourd_hui=None):
	"""Calcule toutes les statistiques pour un sous-ensemble de classes.

	`classes_retenues` : ensemble de (filière, niveau) à analyser (None = toutes).
	`enseignant` : limite aux cours qu'il assure (directement ou via un cours lié)
	et, en finance, à SA rémunération.
	`type_filtre` : code de type de séance (CM, TD, TP, CC, EXAMEN, RATTRAPAGE).
	"""
	d = donnees
	retenue = (lambda c: True) if classes_retenues is None else (lambda c: c in classes_retenues)

	cours_retenus = [nom for nom, c in d.cours.items() if any(retenue(cl) for cl in c["classes"])]
	if enseignant:
		cours_retenus = [
			nom for nom in cours_retenus
			if any(e == enseignant for m in d.groupes[d.groupe_de[nom]] for e, _t in d.affectations.get(m, []))
		]
	retenus = set(cours_retenus)

	cache_bornes = {}
	stats = {}
	for nom in cours_retenus:
		c = d.cours[nom]
		types_cibles = [type_filtre] if type_filtre in TYPES_COURS else ([] if type_filtre else list(TYPES_COURS))
		attendu = avancement_attendu(bornes_semestre(d.academic_year, c["semestre"], cache_bornes), aujourd_hui)
		stats[nom] = {
			"name": nom, "code": c["code"], "intitule": c["intitule"], "semestre": c["semestre"],
			"classes": [d.classes[cl]["libelle"] for cl in c["classes"]],
			"classes_cles": [cl for cl in c["classes"] if retenue(cl)],
			"lie": len(d.groupes[d.groupe_de[nom]]) > 1,
			"tronc_commun": len(c["classes"]) > 1,
			"enseignants": sorted({d.enseignants.get(e, {}).get("nom", e) for e, _t in d.affectations.get(nom, [])}),
			"cible": sum(c["heures"][t] for t in types_cibles),
			"planifie": 0.0, "echu": 0.0, "pointe": 0.0,
			"seances": 0, "annulees": 0, "evaluations": 0,
			"types": {t: 0 for t in LIBELLES_TYPES},
			"attendu": attendu,
			"budget": 0.0, "engage": 0.0, "realise": 0.0,
		}

	# Séances : chaque séance compte pour tous les cours retenus de son groupe.
	semaines = {}
	alertes_tarifs = {}
	parts_classes = {}   # classe -> {"budget", "engage", "realise"} (finance additive)

	def part(classe, champ, montant):
		if retenue(classe):
			parts_classes.setdefault(classe, {"budget": 0.0, "engage": 0.0, "realise": 0.0})[champ] += montant

	for s in d.seances:
		if s["cours"] not in d.cours:
			continue
		if type_filtre and s["type"] != type_filtre:
			continue
		concernes = [m for m in d.groupes[d.groupe_de[s["cours"]]] if m in retenus]
		if not concernes:
			continue
		heures = s["minutes"] / 60.0
		est_cours = s["type"] in TYPES_COURS
		for m in concernes:
			st = stats[m]
			if s["annulee"]:
				st["annulees"] += 1
				continue
			st["seances"] += 1
			st["types"][s["type"]] += 1
			if not est_cours:
				st["evaluations"] += 1
				continue
			st["planifie"] += heures
			if s["echue"]:
				st["echu"] += heures
			if s["faite"]:
				st["pointe"] += heures
		if s["annulee"] or not est_cours:
			continue

		# Coût de la séance, calculé une fois, réparti entre les classes servies.
		if enseignant:
			profs = d.profs(s["cours"], s["type"])
			cout = heures * d.tarif(enseignant)[0] / len(profs) if enseignant in profs else 0.0
		else:
			cout = heures * d.tarif_moyen(s["cours"], s["type"])
		classes = d.classes_du_groupe(s["cours"])
		for cl in classes:
			part(cl, "engage", cout / len(classes))
			if s["echue"]:
				part(cl, "realise", cout / len(classes))
		for m in concernes:
			# Part du cours = ses classes / classes servies (les classes d'un groupe
			# sont disjointes : une classe ne suit qu'un cours d'un même groupe).
			partage = len(d.cours[m]["classes"]) / len(classes)
			stats[m]["engage"] += cout * partage
			if s["echue"]:
				stats[m]["realise"] += cout * partage

		if s["date"]:
			lundi = s["date"] - timedelta(days=s["date"].weekday())
			sem = semaines.setdefault(lundi, {"planifie": 0.0, "echu": 0.0, "engage": 0.0, "realise": 0.0})
			sem["planifie"] += heures
			sem["engage"] += cout
			if s["echue"]:
				sem["echu"] += heures
				sem["realise"] += cout

	# Budgets : un par enseignement (groupe), réparti entre ses classes.
	vus = set()
	for nom in cours_retenus:
		g = d.groupe_de[nom]
		if g in vus:
			continue
		vus.add(g)
		membres = d.groupes[g]
		if enseignant:
			def budget_membre(m):
				total = 0.0
				for t in TYPES_COURS:
					profs = d.profs(m, t)
					if enseignant in profs:
						total += d.cours[m]["heures"][t] * d.tarif(enseignant)[0] / len(profs)
				return total
		else:
			budget_membre = d.budget_cours
		budget = max((budget_membre(m) for m in membres), default=0.0)
		classes = d.classes_du_groupe(nom)
		for cl in classes:
			part(cl, "budget", budget / len(classes))
		for m in membres:
			if m in stats:
				stats[m]["budget"] += budget * len(d.cours[m]["classes"]) / len(classes)

	# Alertes de tarification (enseignants des cours retenus).
	for nom in cours_retenus:
		for e, _t in d.affectations.get(nom, []):
			_tarif, manquant = d.tarif(e)
			if manquant:
				alertes_tarifs.setdefault(manquant, set()).add(d.enseignants.get(e, {}).get("nom", e))

	# Statuts des cours.
	for st in stats.values():
		cible, planifie, echu = st["cible"], st["planifie"], st["echu"]
		if cible <= 0:
			st["statut"] = "sans_volume"
		elif planifie <= 0:
			st["statut"] = "non_planifie"
		elif echu > cible + 1e-6:
			st["statut"] = "depassement"
		elif echu >= cible - 1e-6:
			st["statut"] = "termine"
		else:
			st["statut"] = "en_cours"
		st["completion"] = _pct(echu, cible)
		st["couverture"] = _pct(planifie, cible)
		st["planning_incomplet"] = cible > 0 and planifie + 1e-6 < cible
		st["surplanifie"] = cible > 0 and planifie > cible + 1e-6
		st["en_retard"] = bool(
			cible > 0 and st["attendu"] is not None and st["statut"] in ("non_planifie", "en_cours")
			and echu / cible < st["attendu"] - SEUIL_RETARD
		)
		st["attendu_pct"] = round(100 * st["attendu"], 1) if st["attendu"] is not None else None

	return {
		"stats": stats,
		"parts_classes": parts_classes,
		"semaines": semaines,
		"alertes_tarifs": {k: sorted(v) for k, v in alertes_tarifs.items()},
	}


# ---------------------------------------------------------------------------
# Agrégation
# ---------------------------------------------------------------------------
def agreger(donnees, resultat, cours_noms, classes=None):
	"""Totaux d'un ensemble de cours (heures) et de classes (finance)."""
	stats = resultat["stats"]
	lignes = [stats[n] for n in cours_noms if n in stats]
	cible = sum(s["cible"] for s in lignes)
	planifie = sum(s["planifie"] for s in lignes)
	echu = sum(s["echu"] for s in lignes)
	pointe = sum(s["pointe"] for s in lignes)
	attendu_pondere = sum((s["attendu"] or 0) * s["cible"] for s in lignes if s["attendu"] is not None)
	statuts = {k: 0 for k in ("non_planifie", "en_cours", "termine", "depassement", "sans_volume")}
	for s in lignes:
		statuts[s["statut"]] += 1
	parts = resultat["parts_classes"]
	cles = classes if classes is not None else list(parts)
	budget = sum(parts.get(c, {}).get("budget", 0.0) for c in cles)
	engage = sum(parts.get(c, {}).get("engage", 0.0) for c in cles)
	realise = sum(parts.get(c, {}).get("realise", 0.0) for c in cles)
	return {
		"cours": len(lignes),
		"cible": round(cible, 2), "planifie": round(planifie, 2), "echu": round(echu, 2), "pointe": round(pointe, 2),
		"completion": _pct(echu, cible), "couverture": _pct(planifie, cible), "taux_pointage": _pct(pointe, echu),
		"attendu": round(100 * attendu_pondere / cible, 1) if cible else None,
		"seances": sum(s["seances"] for s in lignes),
		"annulees": sum(s["annulees"] for s in lignes),
		"evaluations": sum(s["evaluations"] for s in lignes),
		"statuts": statuts,
		"en_retard": sum(1 for s in lignes if s["en_retard"]),
		"planning_incomplet": sum(1 for s in lignes if s["planning_incomplet"]),
		"surplanifie": sum(1 for s in lignes if s["surplanifie"]),
		"budget": round(budget, 2), "engage": round(engage, 2), "realise": round(realise, 2),
		"taux_engage": _pct(engage, budget), "taux_realise": _pct(realise, budget),
	}
