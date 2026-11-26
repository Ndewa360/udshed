"""Vacations et progression des cours d'un enseignant (fiches et attestations).

S'appuie sur le moteur d'Insight (udshed.insight.moteur.Donnees) : mêmes cours de l'année,
mêmes affectations, mêmes tarifs par grade, même partage des heures entre co-enseignants
d'un type de séance et entre cours liés. Les montants sont donc ceux d'Insight financier.

Règles configurables (Udshed Setting, section « Vacations ») :
  - séances payées : pointées « Fait » (défaut) ou toutes les séances passées ;
  - coefficient par type (CM, TD, TP ; 1 par défaut = même tarif) ;
  - retenue à la source en % du brut (0 par défaut).
Montant = heures payées × tarif horaire du grade × coefficient du type.
Seuls les vacataires sont rémunérés ; un permanent a des heures mais un montant nul.
"""

from datetime import date, datetime, timedelta

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime

from udshed.insight import moteur

BASE_FAIT = "Séances pointées « Fait »"
BASE_PASSEES = "Séances passées (prévues au planning)"
PERIODES = ("Année complète", "Semestre 1", "Semestre 2")


def reglages():
	s = frappe.get_cached_doc("Udshed Setting")
	return frappe._dict(
		base=s.get("base_paiement_vacations") or BASE_FAIT,
		coef={"CM": flt(s.get("coef_vacation_cm")) or 1.0, "TD": flt(s.get("coef_vacation_td")) or 1.0,
			  "TP": flt(s.get("coef_vacation_tp")) or 1.0},
		retenue=flt(s.get("taux_retenue_vacations")),
	)


def bornes(academic_year, periode=None, debut=None, fin=None):
	"""(début, fin, libellé) de la période demandée."""
	if debut or fin:
		d, f = getdate(debut) if debut else None, getdate(fin) if fin else None
		libelle = _("du {0} au {1}").format(frappe.utils.format_date(d) if d else "…", frappe.utils.format_date(f) if f else "…")
		return d, f, libelle
	if periode in ("Semestre 1", "Semestre 2"):
		from udshed.utils.actes import date_longue

		b = moteur.bornes_semestre(academic_year, periode)
		return (b[0], b[1], _("{0}, du {1} au {2}").format(_(periode), date_longue(b[0]), date_longue(b[1]))) if b \
			else (None, None, _(periode))
	b = moteur.bornes_annee(academic_year)
	if not b:
		return None, None, _("année {0}").format(academic_year)
	from udshed.utils.actes import date_longue

	return b[0], b[1], _("du {0} au {1}").format(date_longue(b[0]), date_longue(b[1]))


def _dans(jour, debut, fin):
	return jour is not None and (debut is None or jour >= debut) and (fin is None or jour <= fin)


def fiche(teacher, academic_year, periode=None, debut=None, fin=None, donnees=None):
	"""Lignes (cours × type) et totaux d'un enseignant pour une année / une période."""
	conf = reglages()
	d = donnees or moteur.Donnees(academic_year)
	b_debut, b_fin, libelle_periode = bornes(academic_year, periode, debut, fin)
	tarif, alerte = d.tarif(teacher)
	info = d.enseignants.get(teacher) or {}
	maintenant = now_datetime()
	lignes = {}

	def ligne(tu, type_code):
		c = d.cours[tu]
		cle = (tu, type_code)
		if cle not in lignes:
			classes = [d.classes[cl]["libelle"] for cl in d.classes_du_groupe(tu)]
			profs = d.profs(tu, type_code)
			lignes[cle] = {
				"cours": tu, "code": c["code"], "intitule": c["intitule"], "semestre": c["semestre"],
				"classes": ", ".join(classes), "type": type_code, "type_libelle": moteur.LIBELLES_TYPES.get(type_code, type_code),
				"prevu": round(c["heures"].get(type_code, 0.0) / max(1, len(profs)), 2) if teacher in profs else 0.0,
				"planifie": 0.0, "fait": 0.0, "seances_faites": 0,
				"taux": tarif, "coef": conf.coef.get(type_code, 1.0), "montant": 0.0,
			}
		return lignes[cle]

	# Cours où l'enseignant intervient (directement ou via un cours lié), heures prévues.
	for tu, affectations in d.affectations.items():
		for e, type_code in affectations:
			if e == teacher and type_code in moteur.TYPES_COURS and tu in d.cours:
				ligne(tu, type_code)

	# Séances : une séance d'un cours du groupe compte pour l'enseignant s'il assure ce type.
	for s in d.seances:
		if s["annulee"] or s["type"] not in moteur.TYPES_COURS or s["cours"] not in d.cours:
			continue
		profs = d.profs(s["cours"], s["type"])
		if teacher not in profs or not _dans(s["date"], b_debut, b_fin):
			continue
		heures = s["minutes"] / 60.0 / len(profs)
		lg = ligne(s["cours"], s["type"])
		lg["planifie"] += heures
		payee = s["faite"] if conf.base == BASE_FAIT else bool(s["date"] and datetime.combine(s["date"], datetime.min.time()) <= maintenant)
		if payee:
			lg["fait"] += heures
			lg["seances_faites"] += 1

	resultat = []
	for lg in sorted(lignes.values(), key=lambda x: (x["semestre"] or "", x["intitule"] or "", x["type"])):
		lg["planifie"] = round(lg["planifie"], 2)
		lg["fait"] = round(lg["fait"], 2)
		lg["montant"] = round(lg["fait"] * lg["taux"] * lg["coef"], 2)
		lg["avancement"] = moteur._pct(lg["fait"], lg["prevu"])
		resultat.append(lg)

	brut = round(sum(lg["montant"] for lg in resultat), 2)
	retenue = round(brut * conf.retenue / 100.0, 2)
	net = round(brut - retenue, 2)
	return frappe._dict({
		"enseignant": teacher, "nom": info.get("nom") or teacher, "vacataire": bool(info.get("vacataire")),
		"statut": info.get("statut") or "", "titre": info.get("titre") or "",
		"annee": academic_year, "periode": libelle_periode,
		"debut": b_debut, "fin": b_fin,
		"lignes": resultat, "devise": d.devise,
		"heures_prevues": round(sum(lg["prevu"] for lg in resultat), 2),
		"heures_planifiees": round(sum(lg["planifie"] for lg in resultat), 2),
		"heures_faites": round(sum(lg["fait"] for lg in resultat), 2),
		"taux": tarif, "brut": brut, "taux_retenue": conf.retenue, "retenue": retenue, "net": net,
		"alerte_tarif": alerte, "base": conf.base,
	})


def tableau(academic_year, periode=None, vacataires_seulement=False):
	"""Une ligne par enseignant intervenant dans l'année (tableau de bord des partenariats)."""
	d = moteur.Donnees(academic_year)
	ids = sorted({e for lst in d.affectations.values() for e, _t in lst})
	conventions = {
		c.teacher: c for c in frappe.get_all(
			"Convention Vacation", filters={"academic_year": academic_year},
			fields=["name", "teacher", "statut", "convention_signee"], order_by="creation asc")
	} if frappe.db.table_exists("Convention Vacation") else {}
	lignes = []
	for teacher in ids:
		f = fiche(teacher, academic_year, periode, donnees=d)
		if vacataires_seulement and not f.vacataire:
			continue
		conv = conventions.get(teacher)
		lignes.append({
			"enseignant": teacher, "nom": f.nom, "statut": f.statut, "vacataire": f.vacataire, "titre": f.titre,
			"heures_prevues": f.heures_prevues, "heures_faites": f.heures_faites,
			"avancement": moteur._pct(f.heures_faites, f.heures_prevues),
			"taux": f.taux, "brut": f.brut, "net": f.net, "alerte_tarif": f.alerte_tarif,
			"convention": conv.name if conv else None, "convention_statut": conv.statut if conv else None,
		})
	lignes.sort(key=lambda x: (not x["vacataire"], x["nom"]))
	return {"annee": academic_year, "devise": d.devise, "lignes": lignes}


def montant_en_lettres(montant, devise=None):
	try:
		from frappe.utils import money_in_words

		return money_in_words(montant, devise)
	except Exception:
		return ""
