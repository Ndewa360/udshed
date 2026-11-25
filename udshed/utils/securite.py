"""Primitives de sécurité partagées par les endpoints udshed.

- Jetons signés (HMAC-SHA256) pour les liens publics (fiches PDF, formulaire
  d'inscription) : la clé est celle du site, jamais une valeur codée en dur.
- Limitation des tentatives échouées (anti force brute) stockée dans Redis.
- Contrôles d'accès alignés sur la configuration Frappe : rôles des Pages
  Desk et permissions des DocTypes, réglables depuis l'interface.
"""

import hashlib
import hmac

import frappe
from frappe import _

# Rôles du personnel : toute personne qui n'est pas uniquement « Student ».
ROLES_PERSONNEL = frozenset(
	{
		"System Manager",
		"Coordonateur",
		"Planning Manager",
		"Registration Manager",
		"Agent de scolarité",
		"Comptable",
		"Correcteur",
		"Responsable Diplomation",
		"Teacher",
	}
)


# ---------------------------------------------------------------------------
# Jetons signés
# ---------------------------------------------------------------------------
def _cle_site():
	"""Clé secrète du site.

	`secret_key` si elle est définie dans site_config.json, sinon la clé de
	chiffrement du site (toujours présente : Frappe la génère au besoin).
	"""
	from frappe.utils.password import get_encryption_key

	cle = frappe.conf.get("secret_key") or get_encryption_key()
	return str(cle).encode("utf-8")


def signer(*parties):
	"""Signature HMAC-SHA256 (hex) des `parties` (converties en texte)."""
	message = "\n".join(str(p if p is not None else "") for p in parties)
	return hmac.new(_cle_site(), message.encode("utf-8"), hashlib.sha256).hexdigest()


def verifier_signature(signature, *parties):
	"""Vrai si `signature` correspond aux `parties` (comparaison à temps constant)."""
	if not signature:
		return False
	return hmac.compare_digest(signer(*parties), str(signature))


# ---------------------------------------------------------------------------
# Limitation des tentatives échouées
# ---------------------------------------------------------------------------
def _cle_tentatives(portee, identifiant):
	return f"udshed:tentatives:{portee}:{str(identifiant or '').strip().casefold()}"


def verifier_tentatives(portee, identifiant, maximum, fenetre_sec):
	"""Bloque si `identifiant` a déjà échoué `maximum` fois dans la fenêtre."""
	if not identifiant:
		return
	nb = frappe.cint(frappe.cache.get_value(_cle_tentatives(portee, identifiant)))
	if nb >= maximum:
		minutes = max(1, fenetre_sec // 60)
		frappe.throw(
			_("Trop de tentatives infructueuses. Réessayez dans {0} minute(s).").format(minutes),
			frappe.RateLimitExceededError,
		)


def enregistrer_echec(portee, identifiant, fenetre_sec):
	"""Comptabilise un échec pour `identifiant` (fenêtre glissante simple)."""
	if not identifiant:
		return
	cle = _cle_tentatives(portee, identifiant)
	nb = frappe.cint(frappe.cache.get_value(cle)) + 1
	frappe.cache.set_value(cle, nb, expires_in_sec=fenetre_sec)


def reinitialiser_tentatives(portee, identifiant):
	if identifiant:
		frappe.cache.delete_value(_cle_tentatives(portee, identifiant))


def ip_client():
	return getattr(frappe.local, "request_ip", None) or "inconnue"


# ---------------------------------------------------------------------------
# Contrôles d'accès
# ---------------------------------------------------------------------------
def est_administrateur(user=None):
	user = user or frappe.session.user
	return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def est_personnel(user=None):
	"""Vrai si l'utilisateur a au moins un rôle du personnel."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(ROLES_PERSONNEL & set(frappe.get_roles(user)))


def exiger_connexion():
	if frappe.session.user == "Guest":
		frappe.throw(_("Vous devez être connecté(e)."), frappe.PermissionError)


def exiger_personnel():
	"""Réservé au personnel (refuse les invités et les comptes étudiants)."""
	exiger_connexion()
	if not est_personnel():
		frappe.throw(_("Accès réservé au personnel de l'établissement."), frappe.PermissionError)


def exiger_roles(*roles):
	"""Refuse l'accès si l'utilisateur n'a aucun des `roles` (Administrator passe)."""
	exiger_connexion()
	if frappe.session.user == "Administrator":
		return
	if not set(roles) & set(frappe.get_roles()):
		frappe.throw(_("Vous n'avez pas les droits nécessaires pour cette opération."), frappe.PermissionError)


def exiger_acces_page(*pages):
	"""Autorise si l'utilisateur peut ouvrir au moins une des Pages Desk.

	Les rôles des pages sont la référence : l'API suit exactement ce que
	l'interface autorise, et reste réglable depuis « Page » / « Role Permission
	for Page and Report ».
	"""
	exiger_connexion()
	if frappe.session.user == "Administrator":
		return
	for page in pages:
		if frappe.db.exists("Page", page) and frappe.get_doc("Page", page).is_permitted():
			return
	frappe.throw(_("Vous n'avez pas accès à cette fonctionnalité."), frappe.PermissionError)


def exiger_acces_rapport(*rapports):
	"""Autorise si l'utilisateur peut ouvrir au moins un des rapports (Report)."""
	exiger_connexion()
	if frappe.session.user == "Administrator":
		return
	for rapport in rapports:
		if frappe.db.exists("Report", rapport) and frappe.get_doc("Report", rapport).is_permitted():
			return
	frappe.throw(_("Vous n'avez pas accès à ce rapport."), frappe.PermissionError)


def exiger_permission(doctype, ptype="read", doc=None):
	"""Applique la permission Frappe du DocType (et du document si fourni)."""
	exiger_connexion()
	frappe.has_permission(doctype, ptype, doc=doc, throw=True)
