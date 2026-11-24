"""Formulaire « Demander une démo » de la landing page Udshed (/udshed).

Chaque demande est :
  - enregistrée comme Communication (reçue) : rien n'est perdu si l'envoi
    d'email échoue ou si aucun compte d'envoi n'est configuré ;
  - envoyée à contact@ndewa-360.com (adresse de contact d'Udshed / Ndewa360).
Protections : limitation de débit par IP, champ piège anti-robots, validation
et échappement de toutes les valeurs.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import escape_html, validate_email_address

CONTACT_UDSHED = "contact@ndewa-360.com"
_LONGUEURS = {"nom": 140, "etablissement": 180, "fonction": 140, "email": 180, "telephone": 40, "effectif": 40, "message": 3000}


def _nettoyer(valeur, longueur):
	return " ".join(str(valeur or "").split())[:longueur] if longueur < 1000 else str(valeur or "").strip()[:longueur]


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60 * 60)
def demander_demo(nom=None, etablissement=None, fonction=None, email=None, telephone=None,
                  effectif=None, message=None, consentement=None, site_web=None):
	# Champ piège invisible : un humain ne le remplit jamais.
	if site_web:
		return {"ok": True}

	v = {cle: _nettoyer(val, _LONGUEURS[cle]) for cle, val in {
		"nom": nom, "etablissement": etablissement, "fonction": fonction, "email": email,
		"telephone": telephone, "effectif": effectif, "message": message,
	}.items()}
	if not (v["nom"] and v["etablissement"] and v["email"]):
		frappe.throw(_("Merci d'indiquer votre nom, votre établissement et votre email."))
	if not validate_email_address(v["email"]):
		frappe.throw(_("Adresse email invalide."))
	if not frappe.utils.cint(consentement):
		frappe.throw(_("Merci d'accepter que vos informations soient utilisées pour vous recontacter."))

	sujet = _("Demande de démo Udshed — {0}").format(v["etablissement"])
	lignes = [
		("Nom", v["nom"]), ("Établissement", v["etablissement"]), ("Fonction", v["fonction"]),
		("Email", v["email"]), ("Téléphone", v["telephone"]), ("Effectif étudiants", v["effectif"]),
	]
	contenu = "<h3>Nouvelle demande de démo Udshed</h3><table>" + "".join(
		f"<tr><td><b>{escape_html(k)}</b></td><td>{escape_html(val or '—')}</td></tr>" for k, val in lignes
	) + "</table>" + (f"<p><b>Message :</b><br>{escape_html(v['message']).replace(chr(10), '<br>')}</p>" if v["message"] else "")

	frappe.get_doc({
		"doctype": "Communication",
		"communication_type": "Communication",
		"communication_medium": "Email",
		"sent_or_received": "Received",
		"subject": sujet,
		"content": contenu,
		"sender": v["email"],
		"sender_full_name": v["nom"],
		"recipients": CONTACT_UDSHED,
		"status": "Open",
	}).insert(ignore_permissions=True)

	try:
		frappe.sendmail(recipients=[CONTACT_UDSHED], subject=sujet, message=contenu, reply_to=v["email"], delayed=True)
	except Exception:
		# La demande reste enregistrée (Communication) : l'équipe la retrouvera.
		frappe.log_error(title="udshed: envoi demande de démo")
	return {"ok": True}
