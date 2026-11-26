"""Documents des enseignants : progression, règlement des vacations, convention, attestation.

Enseignant (son compte) :
  mes_documents()            ses documents disponibles, sa convention, le résumé de l'année
  telecharger(type_acte, …)  PDF ou Word d'un document en libre-service (progression ;
                             règlement des vacations s'il est vacataire ; sa convention envoyée)
Responsable des partenariats (et System Manager) :
  tableau()                  heures, montants et conventions de chaque enseignant de l'année
  telecharger(…, teacher=X)  n'importe quel document, pour n'importe quel enseignant
  creer_conventions()        conventions « Brouillon » pour les vacataires qui n'en ont pas
  modele_vierge(modele)      modèle Word (avec ses variables) à retoucher puis redéposer
Chaque document produit est tracé (« Document Enseignant ») avec un code vérifiable (QR).
"""

import json
import secrets

import frappe
from frappe import _
from frappe.utils import now_datetime

from udshed.utils import actes as moteur
from udshed.utils import documents_word, vacations

ROLES_PARTENARIATS = {"System Manager", "Responsable des partenariats"}
ROLES_LECTURE = ROLES_PARTENARIATS | {"Comptable"}
ROLES_MODELES = {"System Manager", "Responsable Diplomation", "Responsable des partenariats"}
REGLEMENT = "Fiche de règlement des vacations"
CONVENTION = "Convention de vacation"


def _roles():
	return set(frappe.get_roles())


def _gestionnaire():
	return frappe.session.user == "Administrator" or bool(_roles() & ROLES_PARTENARIATS)


def _exiger(roles):
	if frappe.session.user != "Administrator" and not (_roles() & roles):
		frappe.throw(_("Action réservée au service des partenariats enseignants."), frappe.PermissionError)


def _moi():
	from udshed.api.planning_permission import _teacher_name

	teacher = _teacher_name(frappe.session.user)
	if not teacher:
		frappe.throw(_("Aucune fiche enseignant n'est liée à votre compte."), frappe.PermissionError)
	return teacher


def _annee(academic_year=None):
	from udshed.utils.session_academique import annee_session

	return academic_year or annee_session()


def _code():
	while True:
		code = secrets.token_hex(6).upper()
		if not frappe.db.exists("Document Enseignant", {"code_verification": code}) and not frappe.db.exists(
				"Acte Academique", {"code_verification": code}):
			return code


def _convention(teacher, annee):
	return frappe.db.get_value("Convention Vacation", {"teacher": teacher, "academic_year": annee,
														"statut": ["!=", "Résiliée"]},
							   ["name", "statut", "convention_signee", "volume_horaire", "taux_horaire"], as_dict=True)


# ---------------------------------------------------------------------- #
#  Enseignant
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def mes_documents(academic_year=None, periode=None):
	teacher = _moi()
	annee = _annee(academic_year)
	f = vacations.fiche(teacher, annee, periode)
	conv = _convention(teacher, annee)
	documents = []
	for type_acte in moteur.TYPES_ENSEIGNANT:
		nom = moteur.modele_par_defaut(type_acte)
		if not nom:
			continue
		m = frappe.get_cached_doc("Modele Acte", nom)
		possible, message = _autorise(m, teacher, f.vacataire, conv)
		documents.append({"type_acte": type_acte, "modele": nom, "possible": possible, "message": message})
	return {
		"enseignant": teacher, "nom": f.nom, "vacataire": f.vacataire, "annee": annee, "periode": f.periode,
		"heures_prevues": f.heures_prevues, "heures_faites": f.heures_faites,
		"net": f.net if f.vacataire else None, "devise": f.devise, "lignes": f.lignes,
		"documents": documents,
		"convention": {"name": conv.name, "statut": conv.statut, "signee": bool(conv.convention_signee)} if conv else None,
		"historique": frappe.get_all("Document Enseignant", filters={"teacher": teacher},
									 fields=["name", "type_document", "academic_year", "periode", "genere_le"],
									 order_by="creation desc", limit=10),
	}


def _autorise(modele, teacher, vacataire, conv):
	"""(possible, message) pour l'enseignant lui-même."""
	if modele.type_acte == CONVENTION:
		if conv and conv.statut in ("Envoyée à l'enseignant", "Signée"):
			return True, ""
		return False, _("Votre convention n'a pas encore été établie par le service des partenariats.")
	if not modele.libre_service:
		return False, _("Document délivré par le service des partenariats.")
	if modele.type_acte == REGLEMENT and not vacataire:
		return False, _("Réservé aux enseignants vacataires.")
	return True, ""


@frappe.whitelist()
def telecharger(type_acte, format="pdf", teacher=None, academic_year=None, periode=None, convention=None):
	gestion = _gestionnaire()
	moi = None if gestion else _moi()
	if teacher and not gestion and teacher != moi:
		frappe.throw(_("Vous ne pouvez télécharger que vos propres documents."), frappe.PermissionError)
	teacher = teacher or moi or _moi()
	annee = _annee(academic_year)
	nom = moteur.modele_par_defaut(type_acte)
	if not nom:
		frappe.throw(_("Aucun modèle actif pour « {0} ». Créez-en un ou réactivez le modèle par défaut.").format(type_acte))
	m = frappe.get_doc("Modele Acte", nom)
	conv = _convention(teacher, annee)
	if not gestion:
		vacataire = (frappe.db.get_value("Teacher", teacher, "status") or "").strip().lower() != "permanent"
		possible, message = _autorise(m, teacher, vacataire, conv)
		if not possible:
			frappe.throw(message, frappe.PermissionError)
	if type_acte == CONVENTION:
		convention = convention or (conv.name if conv else None)
		if not convention:
			frappe.throw(_("Créez d'abord la convention de vacation de cet enseignant pour l'année {0}.").format(annee))
	doc = frappe.get_doc({
		"doctype": "Document Enseignant", "teacher": teacher, "modele": m.name, "type_document": type_acte,
		"academic_year": annee, "periode": periode or vacations.PERIODES[0], "convention": convention,
		"code_verification": _code(), "genere_par": frappe.session.user, "genere_le": now_datetime(),
		"signe_electroniquement": 1 if m.mode_signature == "Électronique" else 0,
	}).insert(ignore_permissions=True)
	params = {"academic_year": annee, "periode": periode, "convention": convention}
	ctx = moteur.contexte_enseignant(teacher, m, doc, params)
	doc.db_set("donnees", json.dumps({"enseignant": ctx["enseignant"], "annee": annee, "type": type_acte,
									  "etablissement": {"nom": ctx["etablissement"].get("nom")}},
									 ensure_ascii=False, default=str), update_modified=False)
	nom_fichier = f"{type_acte}-{ctx['enseignant'].nom or teacher}-{annee}".replace(" ", "_").replace("'", "")
	if format == "docx":
		_repondre(documents_word.docx(m, teacher, doc, params=params), nom_fichier + ".docx",
				  "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
	else:
		_repondre(moteur.pdf(m, teacher, doc, params=params), nom_fichier + ".pdf", "application/pdf")


def _repondre(contenu, nom, type_mime):
	frappe.response["filename"] = nom
	frappe.response["filecontent"] = contenu
	frappe.response["type"] = "download"
	frappe.response["content_type"] = type_mime


# ---------------------------------------------------------------------- #
#  Service des partenariats
# ---------------------------------------------------------------------- #
@frappe.whitelist()
def tableau(academic_year=None, periode=None, vacataires=0):
	_exiger(ROLES_LECTURE)
	return vacations.tableau(_annee(academic_year), periode, bool(frappe.utils.cint(vacataires)))


@frappe.whitelist()
def synthese_convention(convention):
	"""Tout ce qui concerne une convention : heures, montants, cours, documents, scan signé."""
	_exiger(ROLES_LECTURE)
	conv = frappe.get_doc("Convention Vacation", convention)
	f = vacations.fiche(conv.teacher, conv.academic_year)
	documents = frappe.get_all("Document Enseignant", filters={"teacher": conv.teacher, "academic_year": conv.academic_year},
							   fields=["name", "type_document", "periode", "genere_le", "genere_par"], order_by="creation desc")
	return {
		"enseignant": f.nom, "statut_enseignant": f.statut, "vacataire": f.vacataire, "devise": f.devise,
		"heures_prevues": f.heures_prevues, "heures_planifiees": f.heures_planifiees, "heures_faites": f.heures_faites,
		"taux": f.taux, "brut": f.brut, "retenue": f.retenue, "net": f.net, "alerte_tarif": f.alerte_tarif,
		"volume_convenu": conv.volume_horaire, "taux_convenu": conv.taux_horaire,
		"montant_previsionnel": conv.montant_previsionnel, "lignes": f.lignes, "documents": documents,
		"scan": conv.convention_signee or None,
	}


@frappe.whitelist()
def apercu(type_acte, teacher=None, academic_year=None, periode=None, convention=None):
	"""Aperçu à l'écran (PDF affiché, non tracé) d'un document enseignant."""
	gestion = _gestionnaire()
	if not gestion and (not teacher or teacher != _moi()):
		_exiger(ROLES_PARTENARIATS)
	teacher = teacher or _moi()
	nom = moteur.modele_par_defaut(type_acte)
	if not nom:
		frappe.throw(_("Aucun modèle actif pour « {0} ».").format(type_acte))
	m = frappe.get_doc("Modele Acte", nom)
	params = {"academic_year": _annee(academic_year), "periode": periode, "convention": convention}
	frappe.response["filename"] = f"apercu-{type_acte}.pdf".replace(" ", "_").replace("'", "")
	frappe.response["filecontent"] = moteur.pdf(m, teacher, None, signer=False, params=params)
	frappe.response["type"] = "pdf"


@frappe.whitelist()
def creer_conventions(academic_year=None):
	"""Conventions « Brouillon » pour chaque vacataire de l'année qui n'en a pas."""
	_exiger(ROLES_PARTENARIATS)
	annee = _annee(academic_year)
	crees = []
	for ligne in vacations.tableau(annee, vacataires_seulement=True)["lignes"]:
		if ligne["convention"]:
			continue
		conv = frappe.get_doc({"doctype": "Convention Vacation", "teacher": ligne["enseignant"], "academic_year": annee,
							   "statut": "Brouillon"}).insert()
		crees.append(conv.name)
	return {"crees": crees}


@frappe.whitelist()
def modele_vierge(modele):
	"""Modèle Word par défaut (variables {{ … }}), à retoucher puis déposer sur le modèle."""
	_exiger(ROLES_MODELES)
	m = frappe.get_doc("Modele Acte", modele)
	_repondre(documents_word.modele_vierge(m), f"modele-{m.name}.docx".replace(" ", "_").replace("'", ""),
			  "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@frappe.whitelist()
def telecharger_acte_word(acte):
	"""Version Word d'un acte étudiant (mêmes droits que le PDF)."""
	from udshed.api import actes as api_actes

	doc = frappe.get_doc("Acte Academique", acte)
	staff = bool(_roles() & api_actes.ROLES_ACTES)
	if not staff:
		if doc.student != api_actes._mon_etudiant().name:
			frappe.throw(_("Ce document ne vous appartient pas."), frappe.PermissionError)
		if doc.statut != "Disponible":
			frappe.throw(_("Ce document n'est pas encore disponible (statut : {0}).").format(doc.statut))
	m = frappe.get_doc("Modele Acte", doc.modele)
	_repondre(documents_word.docx(m, doc.student, doc), f"{doc.type_acte}-{doc.name}.docx".replace(" ", "_"),
			  "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
