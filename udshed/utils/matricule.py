"""Matricules étudiants : un seul format, configuré dans les réglages (Udshed Setting).

Repères du format (« Format des matricules ») :
  {AAAA} année de rentrée (2026)      {AA} ses deux derniers chiffres (26)
  {A}    son dernier chiffre (6)       {L}  la lettre (voir « Lettre des matricules »)
  {FIL}  code de la filière            {###} le numéro d'ordre (autant de # que de chiffres)
Exemple : {AA}{L}{###} → 26C095.

La lettre n'a pas de signification imposée : suite des campagnes d'admission (A, B, C…),
lettre fixe de l'établissement, ou lettre propre à chaque filière.
Le même format sert aux admissions et aux imports de listes ; un matricule déjà fourni
(import d'étudiants inscrits) est toujours conservé.
"""

import re

import frappe
from frappe import _

FORMAT_DEFAUT = "{AA}{L}{###}"
MODE_CAMPAGNE = "Suite des campagnes (A, B, C…)"
MODE_FIXE = "Lettre fixe"
MODE_FILIERE = "Lettre de la filière"
MODES = (MODE_CAMPAGNE, MODE_FIXE, MODE_FILIERE)

JETON = re.compile(r"\{(AAAA|AA|A|L|FIL|#+)\}")
MATRICULE_VALIDE = re.compile(r"^[A-Z0-9][A-Z0-9/_-]{2,29}$")
DOCTYPES = ("Inscription Academique", "Student")


def reglages():
	s = frappe.get_cached_doc("Udshed Setting")
	return frappe._dict(
		format=(s.get("format_matricule") or FORMAT_DEFAUT).strip(),
		mode=s.get("mode_lettre_matricule") or MODE_CAMPAGNE,
		lettre_fixe=(s.get("lettre_matricule_fixe") or "").strip().upper(),
	)


def annee_debut(academic_year):
	"""« 2026-2027 » → « 2026 »."""
	debut = str(academic_year or "").strip().split("-")[0].strip()
	return debut if debut.isdigit() else ""


def _indice_en_lettres(n):
	libelle = ""
	n = max(int(n or 1), 1)
	while n > 0:
		n, reste = divmod(n - 1, 26)
		libelle = chr(65 + reste) + libelle
	return libelle


def lettre_campagne(session_name=None, academic_year=None):
	"""Rang de la campagne parmi toutes les campagnes (A, B, C…).

	Campagne du dossier si connue ; sinon (import hors candidature) la campagne de l'année
	de rentrée ; sinon la campagne ouverte, puis la plus récente ; « A » s'il n'y en a aucune.
	"""
	sessions = frappe.get_all("Session Inscription", fields=["name", "academic_year", "status"],
							  order_by="academic_year asc, opening_date asc, creation asc")
	if not sessions:
		return "A"
	active = (
		next((s for s in sessions if session_name and s.name == session_name), None)
		or next((s for s in sessions if academic_year and s.academic_year == academic_year), None)
		or next((s for s in sessions if s.status == "Open"), None)
		or sessions[-1]
	)
	return _indice_en_lettres(sessions.index(active) + 1)


def lettre(conf, session_name=None, academic_year=None, filiere=None):
	if conf.mode == MODE_FIXE:
		return conf.lettre_fixe or "A"
	if conf.mode == MODE_FILIERE:
		propre = filiere and (frappe.db.get_value("Field of study", filiere, "lettre_matricule") or "").strip().upper()
		return propre or conf.lettre_fixe or "A"
	return lettre_campagne(session_name, academic_year)


def valider_format(fmt):
	"""Erreur claire si le format est inutilisable."""
	compteurs = [j for j in JETON.findall(fmt or "") if j.startswith("#")]
	if len(compteurs) != 1:
		frappe.throw(_("Le format des matricules doit contenir un seul numéro d'ordre, par exemple {###}."))
	if len(compteurs[0]) < 2:
		frappe.throw(_("Le numéro d'ordre doit compter au moins 2 chiffres ({##})."))
	reste = JETON.sub("", fmt)
	if "{" in reste or "}" in reste:
		frappe.throw(_("Repère inconnu dans le format des matricules : utilisez {AAAA}, {AA}, {A}, {L}, {FIL} et {###}."))
	exemple = rendre(fmt, "2026", "C", "INF", 95)
	if not MATRICULE_VALIDE.match(exemple):
		frappe.throw(_("Le format produit un matricule invalide ({0}) : lettres majuscules, chiffres, / _ - uniquement, 3 à 30 caractères.").format(exemple))


def _morceaux(fmt, annee, lettre_, code_filiere):
	"""(préfixe, nb_chiffres, suffixe) autour du numéro d'ordre."""
	valeurs = {"AAAA": annee, "AA": annee[-2:], "A": annee[-1:], "L": lettre_, "FIL": (code_filiere or "").upper()}
	avant, nb, apres, vu = [], 0, [], False
	pos = 0
	for m in JETON.finditer(fmt):
		(apres if vu else avant).append(fmt[pos:m.start()])
		jeton = m.group(1)
		if jeton.startswith("#"):
			nb, vu = len(jeton), True
		else:
			(apres if vu else avant).append(valeurs[jeton])
		pos = m.end()
	(apres if vu else avant).append(fmt[pos:])
	return "".join(avant).upper(), nb, "".join(apres).upper()


def rendre(fmt, annee, lettre_, code_filiere, numero):
	prefixe, nb, suffixe = _morceaux(fmt, annee, lettre_, code_filiere)
	return f"{prefixe}{str(numero).zfill(nb)}{suffixe}"


def gabarit(academic_year, session_name=None, filiere=None, lettre_forcee=None):
	conf = reglages()
	annee = annee_debut(academic_year)
	if not annee:
		frappe.throw(_("Aucune année académique valide pour générer le matricule ({0}).").format(academic_year or "—"))
	code = frappe.db.get_value("Field of study", filiere, "field_of_study_code") if filiere else ""
	l_ = lettre_forcee or lettre(conf, session_name, academic_year, filiere)
	prefixe, nb, suffixe = _morceaux(conf.format, annee, l_, code)
	return prefixe, nb, suffixe


def _max_numero(prefixe, suffixe):
	motif = "^" + re.escape(prefixe) + "[0-9]+" + re.escape(suffixe) + "$"
	debut = len(prefixe) + 1
	maximum = 0
	for doctype in DOCTYPES:
		row = frappe.db.sql(
			f"""SELECT MAX(CAST(SUBSTRING(matricule, %(debut)s, CHAR_LENGTH(matricule) - %(lg)s) AS UNSIGNED))
			FROM `tab{doctype}` WHERE matricule LIKE %(like)s AND matricule REGEXP %(motif)s""",
			{"debut": debut, "lg": len(prefixe) + len(suffixe), "like": prefixe.replace("%", r"\%") + "%", "motif": motif},
		)
		maximum = max(maximum, int((row[0][0] if row and row[0] else 0) or 0))
	return maximum


def generer(academic_year, session_name=None, filiere=None, lettre_forcee=None):
	"""Prochain matricule libre, sous verrou SQL (pas de doublon sous concurrence)."""
	prefixe, nb, suffixe = gabarit(academic_year, session_name, filiere, lettre_forcee)
	cle = f"udshed_matricule:{prefixe}"
	lignes = frappe.db.sql("SELECT GET_LOCK(%s, 10)", (cle,))
	if not lignes or lignes[0][0] != 1:
		frappe.throw(_("Impossible de générer le matricule (concurrence). Réessayez."))
	try:
		return f"{prefixe}{str(_max_numero(prefixe, suffixe) + 1).zfill(nb)}{suffixe}"
	finally:
		try:
			frappe.db.sql("SELECT RELEASE_LOCK(%s)", (cle,))
		except Exception:
			pass


@frappe.whitelist()
def apercu(format_matricule=None, mode_lettre_matricule=None, lettre_matricule_fixe=None):
	"""Prochain matricule avec les réglages saisis (formulaire des réglages, avant enregistrement)."""
	if not frappe.has_permission("Udshed Setting", "read"):
		frappe.throw(_("Réservé aux personnes qui gèrent les réglages."), frappe.PermissionError)
	fmt = (format_matricule or FORMAT_DEFAUT).strip()
	valider_format(fmt)
	annee = frappe.db.get_single_value("Udshed Setting", "current_year") or ""
	conf = frappe._dict(format=fmt, mode=mode_lettre_matricule or MODE_CAMPAGNE,
						lettre_fixe=(lettre_matricule_fixe or "").strip().upper())
	filiere = frappe.db.get_value("Field of study", {}, "name") if conf.mode == MODE_FILIERE else None
	debut = annee_debut(annee) or str(frappe.utils.getdate().year)
	code = frappe.db.get_value("Field of study", filiere, "field_of_study_code") if filiere else "INF"
	prefixe, nb, suffixe = _morceaux(fmt, debut, lettre(conf, academic_year=annee, filiere=filiere), code)
	return {"exemple": f"{prefixe}{str(_max_numero(prefixe, suffixe) + 1).zfill(nb)}{suffixe}",
			"annee": annee, "filiere": filiere}
