# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from udshed.api.candidature import (
	_nettoyer_telephone,
	get_school_logo_url,
	jeton_fiche_candidature,
	poser_cookie_fiche,
)
from udshed.utils import securite
from udshed.utils.campagne import annee_cible
from udshed.udshed.doctype.concours.concours import concours_pour_formation
from udshed.api.concours import (
	STATUT_AUTORISE,
	STATUT_DESISTE,
	STATUT_LISTE_ATTENTE,
	STATUTS_GERES_PAR_CONCOURS,
	candidat_non_admis_publie,
	envoyer_convocation,
	envoyer_resultat_liste_attente,
	inscrire_candidat,
	retirer_candidat,
	verifier_autorisation,
	verifier_retrait,
)


class SessionInscriptionCandidate(Document):

	def before_insert(self):
		if self.last_name:
			self.last_name = self.last_name.upper().strip()
		if self.first_name:
			self.first_name = self.first_name.upper().strip()
		modele_full_name = 'f"{first_name} {last_name}"'
		if not self.full_name or self.full_name == modele_full_name:
			self.full_name = " ".join(filter(None, [self.first_name, self.last_name]))
		# Champs absents du formulaire de candidature : on retire les valeurs par
		# défaut (Frappe applique la 1re option d'un Select et les defaults du
		# doctype) afin que le dossier soit vierge tant que ces infos ne sont pas
		# réellement renseignées.
		valeur_par_defaut = {
			"nationality": "CM",
			"religion": "CHRÉTIEN",
			"employment_status": "SANS EMPLOI",
			"marital_status": "CELIBATAIRE",
			"language": "FR",
			"handicap": "NON",
			"father_country": "CM",
			"mother_country": "CM",
			"sponsor_country": "CM",
			"entry_diploma": "BAC",
		}
		for champ, defaut in valeur_par_defaut.items():
			if self.get(champ) == defaut:
				self.set(champ, "")
		self.status_updated_on = frappe.utils.now_datetime()
		self._rattacher_campagne()

	def _rattacher_campagne(self):
		"""Un candidat ne dépose que pendant la période de dépôt d'une campagne.
		Le personnel peut saisir un dossier hors période (rattrapage) : il est
		alors rattaché à la campagne courante."""
		from udshed.utils import campagne as campagnes

		if self.session_inscription:
			return
		if securite.est_personnel():
			c = campagnes.campagne_ouverte() or campagnes.campagne_courante()
		else:
			c = campagnes.exiger_depot_ouvert()
		if not c:
			frappe.throw(_("Aucune campagne d'admission n'est configurée."))
		self.session_inscription = c.name

	def validate(self):
		for champ in ("phone", "parent_phone", "father_phone", "mother_phone", "sponsor_phone"):
			valeur = getattr(self, champ, None)
			if valeur:
				setattr(self, champ, _nettoyer_telephone(valeur))
		self._controler_centre()
		self._deduire_filiere_niveau_des_choix()
		self._rattacher_concours()
		self._controler_admission()
		self._proteger_statut_accepte()
		self._controler_statut_concours()
		if self.candidature_status == "Refusé" and not (self.status_comment or "").strip():
			frappe.throw(_("Le motif du rejet est obligatoire pour un statut « Refusé »."))

	def _controler_admission(self):
		"""« Accepté » est une offre de place, pas une inscription :
		- « Inscrit » n'est posé que par la finalisation (matricule, fiche étudiant) ;
		- « Désisté » passe par l'action « Enregistrer un désistement » (place reproposée) ;
		- l'admission fixe la date limite de finalisation."""
		if self.is_new():
			return
		avant = self.get_doc_before_save()
		ancien = avant.candidature_status if avant else None
		nouveau = self.candidature_status
		if ancien == nouveau:
			return
		if nouveau == "Inscrit":
			frappe.throw(
				_("Le statut « Inscrit » ne se pose pas à la main : il est attribué automatiquement "
				  "quand le candidat admis finalise son inscription (création du matricule).")
			)
		if nouveau == STATUT_DESISTE and not frappe.flags.admission_par_jury:
			frappe.throw(
				_("Utilisez l'action « Enregistrer un désistement » : elle demande le motif et "
				  "repropose la place au suivant de la liste d'attente.")
			)
		if nouveau == "Accepté":
			from udshed.api.concours_finalisation import echeance_finalisation

			self.finaliser_avant = echeance_finalisation(self)

	def _controler_centre(self):
		"""Le centre d'examen doit être l'un de ceux de la campagne (s'ils sont configurés)."""
		from udshed.utils.campagne import campagne_du_dossier, centres

		if not self.examination_centre or not (self.is_new() or self.has_value_changed("examination_centre")):
			return
		proposes = centres(campagne_du_dossier(self))
		if proposes and self.examination_centre not in proposes:
			frappe.throw(
				_("Centre d'examen « {0} » inconnu pour cette campagne. Centres proposés : {1}.").format(
					self.examination_centre, ", ".join(proposes)
				)
			)

	def _deduire_filiere_niveau_des_choix(self):
		"""Le formulaire ne collecte plus filière/niveau en haut de page : on les
		déduit donc du 1er choix. À la création on écrase les valeurs par défaut
		(frappe met automatiquement la 1re option d'un champ Select), ensuite on ne
		complète que si le dossier est encore vide."""
		if not self.is_new() and self.get("filiere") and self.get("niveau"):
			return
		rows = self.get("choix_de_formation") or []
		if not rows:
			return
		premier = rows[0]
		if premier.get("filiere") and (self.is_new() or not self.get("filiere")):
			self.filiere = premier.get("filiere")
		niveau_name = premier.get("niveau")
		if niveau_name and (self.is_new() or not self.get("niveau")):
			niveau_label = frappe.db.get_value(
				"Field of study Level", niveau_name, "level"
			)
			self.niveau = niveau_label or niveau_name

	def _rattacher_concours(self):
		"""Mode d'admission : « Concours » dès qu'une des formations demandées
		(1er, 2e ou 3e choix) est au programme d'un concours de la campagne,
		sinon « Dossier ». Recalculé tant que le dossier n'est pas tranché."""
		if not self.is_new() and self.candidature_status not in ("En attente", "Dossier en cours d'examen"):
			return
		concours = None
		for row in self.get("choix_de_formation") or []:
			concours = concours_pour_formation(self.session_inscription, row.get("filiere"), row.get("niveau"))
			if concours:
				break
		self.concours = concours
		self.mode_admission = "Concours" if concours else "Dossier"

	def _controler_statut_concours(self):
		"""Règles du circuit concours :
		- « Autorisé à concourir » : seulement pour un dossier rattaché à un concours ouvert ;
		- « Accepté » : pour un candidat au concours, seule la délibération du jury
		  le prononce (frappe.flags.admission_par_jury) ;
		- quitter « Autorisé à concourir » retire le candidat du concours, tant
		  qu'aucune note n'est saisie."""
		if self.is_new():
			return
		avant = self.get_doc_before_save()
		ancien = avant.candidature_status if avant else None
		nouveau = self.candidature_status
		if ancien == nouveau:
			return
		if nouveau == STATUT_AUTORISE:
			verifier_autorisation(self)
		if frappe.flags.admission_par_jury:
			return
		if nouveau in STATUTS_GERES_PAR_CONCOURS or ancien in STATUTS_GERES_PAR_CONCOURS:
			frappe.throw(
				_("Le statut « {0} » est géré par le concours (publication des résultats, "
				  "désistement) : il ne se modifie pas à la main.").format(
					nouveau if nouveau in STATUTS_GERES_PAR_CONCOURS else ancien)
			)
		if (
			nouveau == "Accepté"
			and self.mode_admission == "Concours"
			and not candidat_non_admis_publie(self)
		):
			frappe.throw(
				_("Ce candidat passe par le concours {0} : son admission sera prononcée par la "
				  "délibération du jury, pas manuellement.").format(self.concours)
			)
		if ancien == STATUT_AUTORISE:
			verifier_retrait(self)

	def after_insert(self):
		# Le candidat (invité) qui vient de soumettre peut télécharger SA fiche
		# depuis /candidature-success, sans exposer les fiches des autres.
		if frappe.session.user == "Guest":
			poser_cookie_fiche(self.name)
		self._send_candidate_email()
		self._send_coordinator_email()

	def on_update(self):
		old_doc = self.get_doc_before_save()
		if not old_doc:
			return
		if old_doc.candidature_status == self.candidature_status:
			return
		frappe.db.set_value(
			"Session Inscription Candidate",
			self.name,
			"status_updated_on",
			frappe.utils.now_datetime(),
			update_modified=False,
		)
		if self.candidature_status == STATUT_AUTORISE:
			fiche = inscrire_candidat(self)
			envoyer_convocation(fiche.name)
		elif old_doc.candidature_status == STATUT_AUTORISE and not frappe.flags.admission_par_jury:
			retirer_candidat(self)

		if self.candidature_status == "Accepté":
			_send_confirmation_email(self)
		elif self.candidature_status == STATUT_LISTE_ATTENTE:
			envoyer_resultat_liste_attente(self.name)
		elif self.candidature_status == "Refusé":
			_send_rejection_email(self, (self.status_comment or "").strip())
		# « Inscrit » : l'email du matricule est envoyé par la finalisation
		# (udshed/api/inscription.py), seule à poser ce statut.

	def _proteger_statut_accepte(self):
		"""Une fois une candidature acceptée, son statut ne peut plus être modifié,
		excepté son passage à « Inscrit » lors de la finalisation de l'inscription."""
		if not self.get("name"):
			return
		old_doc = self.get_doc_before_save()
		if not old_doc:
			return
		old_status = old_doc.candidature_status
		# Seul le désistement d'un admis au concours (géré par le concours) rouvre un « Accepté ».
		if old_status == "Accepté" and self.candidature_status == "Désisté" and frappe.flags.admission_par_jury:
			return
		if old_status in ("Accepté", "Inscrit") and self.candidature_status != old_status:
			frappe.throw(
				_(
					"Le statut d'une candidature déjà {0} est verrouillé et ne peut plus être modifié."
				).format(old_status)
			)

	def _send_candidate_email(self):
		if not self.email:
			frappe.logger().warning(
				f"Impossible d'envoyer l'accusé de réception : aucun e-mail renseigné pour le candidat {self.name}"
			)
			return

		setting = frappe.get_single("Udshed Setting")
		from udshed.utils.etablissement import etablissement

		subject = getattr(setting, "email_candidature_subject", None) or _(
			"Accusé de réception de votre candidature - {0}"
		).format(etablissement().nom)
		sender = _get_sender()

		try:
			frappe.sendmail(
				recipients=[self.email],
				sender=sender,
				subject=_(subject),
				template="candidature_receipt",
				args={
					"first_name": self.first_name,
					"last_name": self.last_name,
					"doc_name": self.name,
					"jeton_fiche": jeton_fiche_candidature(self.name),
					"niveau": self.niveau or "",
					"filiere": self.filiere or "",
					"base_url": frappe.utils.get_url(),
					"logo_url": get_school_logo_url(),
				},
				now=True,
			)
			frappe.logger().info(f"Email accusé de réception envoyé à {self.email} pour {self.name}")
		except Exception as e:
			frappe.log_error(
				message=str(e),
				title=f"Échec envoi e-mail candidat {self.name}",
			)

	def _destinataires_coordination(self):
		"""Coordonnateurs des niveaux demandés (1er, 2e, 3e choix), plus
		l'adresse générale des réglages si elle est renseignée."""
		emails = []
		niveaux = [row.get("niveau") for row in self.get("choix_de_formation") or [] if row.get("niveau")]
		for niveau in niveaux:
			teacher = frappe.db.get_value("Field of study Level", niveau, "coordonateur")
			email = frappe.db.get_value("Teacher", teacher, "email") if teacher else None
			if email and email not in emails:
				emails.append(email)
		general = frappe.db.get_single_value("Udshed Setting", "email_coordinateur")
		if general and general not in emails:
			emails.append(general)
		return emails

	def _send_coordinator_email(self):
		destinataires = self._destinataires_coordination()
		if not destinataires:
			frappe.logger().info("Aucun coordonnateur à notifier pour cette candidature.")
			return

		sender = _get_sender()

		choix_text = ""
		if self.choix_de_formation:
			lignes = []
			for row in self.choix_de_formation:
				lignes.append(
					f"<li>{row.get('choix', '')} — {row.get('filiere', '')} ({row.get('niveau', '')})</li>"
				)
			choix_text = "<ul>" + "".join(lignes) + "</ul>"

		try:
			frappe.sendmail(
				recipients=destinataires,
				sender=sender,
				subject=_("Nouvelle candidature reçue - {0} {1} ({2})").format(
					self.first_name, self.last_name, self.name
				),
				template="candidature_notification_coordinator",
				args={
					"first_name": self.first_name,
					"last_name": self.last_name,
					"doc_name": self.name,
					"email": self.email or "",
					"phone": self.phone or "",
					"niveau": self.niveau or "",
					"filiere": self.filiere or "",
					"examination_centre": self.examination_centre or "",
					"choix_text": choix_text,
					"birth_place": self.birth_place or "",
					"sexe": self.sexe or "",
					"logo_url": get_school_logo_url(),
				},
				now=True,
			)
			frappe.logger().info(
				f"Notification coordination envoyée à {', '.join(destinataires)} pour la candidature {self.name}"
			)
		except Exception as e:
			frappe.log_error(
				message=str(e),
				title=f"Échec notification coordonnateur pour {self.name}",
			)


@frappe.whitelist(allow_guest=True)
def track_candidature(doc_name: str) -> dict:
	"""Rechercher une candidature par son numéro et retourner les infos de suivi.

	Accès public (allow_guest). Remplacé par l'espace « Mon dossier » (/mon-dossier),
	conservé pour les liens existants : ne renvoie plus de motif ni d'email.
	Seuls les champs utiles au suivi sont renvoyés.
	"""
	if not doc_name:
		frappe.throw(_("Veuillez saisir un numéro de dossier."))

	doc_name = doc_name.strip().upper()

	# Freine l'énumération des numéros de dossier (séquentiels).
	ip = securite.ip_client()
	securite.verifier_tentatives("suivi-candidature", ip, 30, 15 * 60)
	if not frappe.db.exists("Session Inscription Candidate", doc_name):
		securite.enregistrer_echec("suivi-candidature", ip, 15 * 60)

	doc = frappe.db.get_value(
		"Session Inscription Candidate",
		doc_name,
		[
			"name",
			"first_name",
			"last_name",
			"email",
			"niveau",
			"filiere",
			"examination_centre",
			"candidature_status",
			"status_updated_on",
			"status_comment",
			"creation",
		],
		as_dict=True,
	)

	if not doc:
		frappe.throw(
			_("Aucune candidature trouvée avec le numéro <b>{0}</b>.").format(doc_name)
		)

	return {
		"doc_name": doc.name,
		"first_name": doc.first_name,
		"last_name": doc.last_name,
		"niveau": doc.niveau or "",
		"filiere": doc.filiere or "",
		"examination_centre": doc.examination_centre or "",
		"status": doc.candidature_status or "En attente",
		"status_date": frappe.utils.format_datetime(doc.status_updated_on, "dd/MM/yyyy HH:mm")
			if doc.status_updated_on
			else frappe.utils.format_datetime(doc.creation, "dd/MM/yyyy HH:mm"),
		"submitted_on": frappe.utils.format_datetime(doc.creation, "dd/MM/yyyy HH:mm"),
		"detail_url": "/mon-dossier",
	}


@frappe.whitelist(allow_guest=True)
def get_session_status() -> dict:
	"""État de la campagne d'admission pour le bandeau de la page d'accueil."""
	from udshed.utils.campagne import infos_publiques

	infos = infos_publiques()
	c = infos["campagne"]
	if not c:
		return {"status": "Aucune", "academic_year": "", "label": _("Aucune campagne de candidature"), "css_class": "draft"}
	libelles = {
		"ouverte": (_("Candidatures {0} ouvertes jusqu'au {1}").format(c["academic_year"], c["cloture"]), "open", "Open"),
		"a_venir": (_("Candidatures {0} : ouverture le {1}").format(c["academic_year"], c["ouverture"]), "draft", "Draft"),
		"close": (_("Candidatures {0} closes").format(c["academic_year"]), "closed", "Closed"),
	}
	label, css, statut = libelles.get(infos["etat"], (c["titre"], "draft", "Draft"))
	return {"status": statut, "academic_year": c["academic_year"], "label": label, "css_class": css,
			"route": infos["route_candidature"]}


# ---------------------------------------------------------------------------
# Dashboard API — Consultation des candidatures
# ---------------------------------------------------------------------------

def _build_filters(session=None, filiere=None, niveau=None, centre=None, statut=None):
	"""Construit les filtres pour les requêtes dashboard."""
	filters = {}
	if session:
		filters["session_inscription"] = session
	if filiere:
		filters["filiere"] = filiere
	if niveau:
		filters["niveau"] = niveau
	if centre:
		filters["examination_centre"] = centre
	if statut:
		filters["candidature_status"] = statut
	# Périmètre : un coordonnateur ne voit que ses filières, un agent de scolarité / un doyen les
	# siennes (ces API lisent la base directement : les hooks de liste ne s'appliquent pas).
	from udshed import permissions
	from udshed.utils import perimetre

	if permissions._coordonnateur_seul(frappe.session.user):
		coordonnees = permissions.filieres_coordonnees(frappe.session.user)
		if filiere and filiere not in coordonnees:
			frappe.throw(_("Cette filière n'est pas dans votre périmètre."), frappe.PermissionError)
		if not filiere:
			filters["filiere"] = ["in", coordonnees or ["∅"]]
	perimetre.filtre(filters)
	return filters


@frappe.whitelist()
def exporter_candidatures(session=None, filiere=None, niveau=None, centre=None, statut=None):
	"""Export CSV des candidatures (filtres de la page « Consultation des candidatures »)."""
	import csv
	import io

	securite.exiger_personnel()
	securite.exiger_permission("Session Inscription Candidate", "export")
	filters = _build_filters(session, filiere, niveau, centre, statut)
	meta = frappe.get_meta("Session Inscription Candidate")
	colonnes = [(c, l) for c, l in (
		("name", "N° dossier"), ("last_name", "Nom"), ("first_name", "Prénom"), ("email", "Email"),
		("phone", "Téléphone"), ("telephone", "Téléphone"), ("filiere", "Filière"), ("niveau", "Niveau"),
		("examination_centre", "Centre"), ("session_inscription", "Campagne"),
		("candidature_status", "Statut"), ("creation", "Soumis le"),
	) if c in ("name", "creation") or meta.has_field(c)]
	lignes = frappe.get_all("Session Inscription Candidate", filters=filters, fields=[c for c, _l in colonnes],
							order_by="creation desc")
	sortie = io.StringIO()
	ecrivain = csv.writer(sortie, delimiter=";")
	ecrivain.writerow([l for _c, l in colonnes])
	for r in lignes:
		ecrivain.writerow([frappe.utils.format_datetime(r.get(c), "dd/MM/yyyy") if c == "creation" else (r.get(c) or "")
							for c, _l in colonnes])
	frappe.response["filename"] = f"candidatures_{frappe.utils.nowdate()}.csv"
	frappe.response["filecontent"] = sortie.getvalue().encode("utf-8-sig")
	frappe.response["type"] = "download"
	frappe.response["content_type"] = "text/csv"


@frappe.whitelist()
def get_candidate_dashboard_stats(
	session=None, filiere=None, niveau=None, centre=None, statut=None
):
	"""Retourne les compteurs pour les cartes stats du dashboard."""
	securite.exiger_personnel()
	securite.exiger_permission("Session Inscription Candidate", "read")
	filters = _build_filters(session, filiere, niveau, centre, statut)

	counts = {}
	for label, status_val in [
		("total", None),
		("en_attente", "En attente"),
		("en_cours", "Dossier en cours d'examen"),
		("autorise", "Autorisé à concourir"),
		("liste_attente", "Liste d'attente"),
		("accepte", "Accepté"),
		("refuse", "Refusé"),
		("desiste", "Désisté"),
		("inscrit", "Inscrit"),
	]:
		if status_val:
			counts[label] = frappe.db.count(
				"Session Inscription Candidate",
				{**filters, "candidature_status": status_val},
			)
		else:
			counts[label] = frappe.db.count("Session Inscription Candidate", filters)

	return counts


@frappe.whitelist()
def get_candidates_list(
	session=None, filiere=None, niveau=None, centre=None,
	statut=None, start=0, limit=20,
):
	"""Liste paginée des candidats avec infos clés."""
	securite.exiger_personnel()
	securite.exiger_permission("Session Inscription Candidate", "read")
	filters = _build_filters(session, filiere, niveau, centre, statut)

	docs = frappe.get_all(
		"Session Inscription Candidate",
		filters=filters,
		fields=[
			"name", "first_name", "last_name", "filiere", "niveau",
			"examination_centre", "candidature_status", "creation",
			"session_inscription",
		],
		order_by="session_inscription asc, creation desc",
		start=start,
		limit_page_length=limit,
	)

	for d in docs:
		d.filiere_label = (
			frappe.db.get_value("Field of study", d.filiere, "name_of_field") or d.filiere
			if d.filiere else ""
		)
		d.submitted_on = frappe.utils.format_datetime(d.creation, "dd/MM/yyyy")
		d.session_label = (
			frappe.db.get_value("Session Inscription", d.session_inscription, "academic_year")
			if d.session_inscription else ""
		)

	total = frappe.db.count("Session Inscription Candidate", filters)
	return {"candidates": docs, "total": total}


ROLES_DECISION = ("System Manager", "Registration Manager", "Agent de scolarité")
ROLES_RESPONSABLE = ("System Manager", "Registration Manager")


def droits_candidature(doc):
	"""Actions que l'utilisateur courant peut faire sur ce dossier (pour l'écran
	de consultation ; le serveur revérifie chaque action)."""
	from udshed.api.concours import candidat_non_admis_publie

	roles = set(frappe.get_roles())
	decide = bool(roles & set(ROLES_DECISION)) and frappe.has_permission(
		"Session Inscription Candidate", "write", doc=doc
	)
	statut = doc.candidature_status or "En attente"
	en_examen = statut in ("En attente", "Dossier en cours d'examen")
	# Non-admis au concours renvoyé en étude de dossier : acceptation sur dossier permise.
	accepte_dossier = doc.mode_admission != "Concours" or (
		statut == "Dossier en cours d'examen" and candidat_non_admis_publie(doc)
	)
	return {
		"decider": decide,
		"mettre_en_cours": decide and statut == "En attente",
		"accepter": decide and en_examen and accepte_dossier,
		"autoriser_concours": decide and en_examen and doc.mode_admission == "Concours" and not accepte_dossier,
		"rejeter": decide and en_examen,
		"desister": bool(roles & set(ROLES_RESPONSABLE)) and statut in ("Accepté", "Liste d'attente"),
	}


@frappe.whitelist()
def options_consultation():
	"""Valeurs des filtres de l'écran de consultation (rien de figé)."""
	securite.exiger_personnel()
	securite.exiger_permission("Session Inscription Candidate", "read")
	from udshed.utils.campagne import centres

	niveaux = sorted({n for n in frappe.get_all("Session Inscription Candidate", pluck="niveau", distinct=True) if n})
	tous_centres = set()
	for nom in frappe.get_all("Session Inscription", pluck="name"):
		tous_centres.update(centres(frappe.get_cached_doc("Session Inscription", nom)))
	tous_centres.update(c for c in frappe.get_all("Session Inscription Candidate", pluck="examination_centre",
												  distinct=True) if c)
	statuts = (frappe.get_meta("Session Inscription Candidate").get_field("candidature_status").options or "").split("\n")
	return {"niveaux": niveaux, "centres": sorted(tous_centres), "statuts": [s for s in statuts if s]}


@frappe.whitelist()
def get_candidate_detail(name):
	"""Détail complet d'un candidat (y compris child tables)."""
	securite.exiger_personnel()
	doc = frappe.get_doc("Session Inscription Candidate", name)
	securite.exiger_permission("Session Inscription Candidate", "read", doc=doc)

	choix = []
	for row in doc.choix_de_formation:
		filiere_label = frappe.db.get_value("Field of study", row.filiere, "name_of_field") if row.filiere else ""
		choix.append({"choix": row.choix, "filiere": filiere_label, "niveau": row.niveau})

	diplomes = []
	for row in doc.diplome_formation:
		diplomes.append({
			"diplome": row.diplome,
			"year": row.year,
			"serie": row.serie__field_of_study,
			"lieu": row.place_of_acquisition,
			"mention": row.mention,
		})

	return {
		"droits": droits_candidature(doc),
		"name": doc.name,
		"first_name": doc.first_name,
		"last_name": doc.last_name,
		"full_name": doc.full_name,
		"birthdate": frappe.utils.format_date(doc.birthdate) if doc.birthdate else "",
		"birth_place": doc.birth_place or "",
		"sexe": doc.sexe or "",
		"phone": doc.phone or "",
		"email": doc.email or "",
		"parent_phone": doc.parent_phone or "",
		"email_parent": doc.email_parent or "",
		"home_city": doc.home_city or "",
		"filiere": doc.filiere or "",
		"filiere_label": (
			frappe.db.get_value("Field of study", doc.filiere, "name_of_field")
			if doc.filiere else ""
		),
		"niveau": doc.niveau or "",
		"examination_centre": doc.examination_centre or "",
		"choix_de_formation": choix,
		"diplome_formation": diplomes,
		"birth_certificate": doc.birth_certificate or "",
		"access_diploma_copy": doc.access_diploma_copy or "",
		"id_photo": doc.id_photo or "",
		"remittance_receipt": doc.remittance_receipt or "",
		"candidature_status": doc.candidature_status or "En attente",
		"mode_admission": doc.mode_admission or "Dossier",
		"concours": doc.concours or "",
		"status_updated_on": (
			frappe.utils.format_datetime(doc.status_updated_on, "dd/MM/yyyy HH:mm")
			if doc.status_updated_on else ""
		),
		"status_comment": doc.status_comment or "",
		"submitted_on": frappe.utils.format_datetime(doc.creation, "dd/MM/yyyy HH:mm"),
	}


@frappe.whitelist()
def update_candidate_status(name, new_status, comment=None):
	"""Change le statut d'un candidat. Motif obligatoire si Refusé."""
	if new_status == "Refusé" and not comment:
		frappe.throw(_("Le motif du rejet est obligatoire."))

	securite.exiger_personnel()
	doc = frappe.get_doc("Session Inscription Candidate", name)
	# Droit d'écriture vérifié AVANT tout changement, désistement compris.
	securite.exiger_permission("Session Inscription Candidate", "write", doc=doc)

	if new_status == STATUT_DESISTE:
		from udshed.api.concours_finalisation import desister_candidature

		old_status = doc.candidature_status
		desister_candidature(name, comment)
		return {"ok": True, "old_status": old_status, "new_status": new_status}
	old_status = doc.candidature_status

	doc.candidature_status = new_status
	if comment:
		doc.status_comment = comment
	doc.status_updated_on = frappe.utils.now_datetime()
	doc.save()

	# Les emails (confirmation / rejet / validation) sont envoyés dans on_update

	return {"ok": True, "old_status": old_status, "new_status": new_status}


# ---------------------------------------------------------------------------
# Emails — Confirmation + Validation
# ---------------------------------------------------------------------------

def _nom_etablissement():
	from udshed.utils.etablissement import etablissement

	return etablissement().nom


def _get_sender():
	"""Return the formatted sender name from Udshed Setting."""
	setting = frappe.get_single("Udshed Setting")
	sender_name = getattr(setting, "email_candidature_sender_name", None) or "Udshed"
	email_account = frappe.db.get_value("Email Account", {"default_outgoing": 1}, "email_id")
	if email_account:
		return f"{sender_name} <{email_account}>"
	return None


def _send_confirmation_email(doc):
	"""Email envoyé au candidat quand sa candidature est Acceptée."""
	if not doc.email:
		frappe.logger().warning(
			f"Pas d'email pour {doc.name} — email confirmation non envoyé."
		)
		return

	sender = _get_sender()
	academic_year = annee_cible(doc)
	filiere_label = frappe.db.get_value("Field of study", doc.filiere, "name_of_field") if doc.filiere else ""

	try:
		frappe.sendmail(
			recipients=[doc.email],
			sender=sender,
			subject=_("Félicitations, votre candidature a été acceptée - {0}").format(_nom_etablissement()),
			template="candidature_confirmation",
			args={
				"first_name": doc.first_name,
				"last_name": doc.last_name,
				"doc_name": doc.name,
				"academic_year": academic_year,
				"filiere": filiere_label,
				"niveau": doc.niveau or "",
				"centre": doc.examination_centre or "",
				"date_limite": frappe.utils.format_date(doc.finaliser_avant) if doc.get("finaliser_avant") else "",
				"lien_admission": frappe.utils.get_url("/mon-dossier"),
				"logo_url": get_school_logo_url(),
			},
			now=True,
		)
		frappe.logger().info(f"Email confirmation envoyé à {doc.email} pour {doc.name}")
	except Exception as e:
		frappe.log_error(
			message=str(e), title=f"Échec email confirmation {doc.name}"
		)


def _send_rejection_email(doc, motif=None):
	"""Email envoyé au candidat quand sa candidature est Refusée."""
	if not doc.email:
		frappe.logger().warning(
			f"Pas d'email pour {doc.name} — email rejet non envoyé."
		)
		return

	sender = _get_sender()
	academic_year = annee_cible(doc)
	filiere_label = frappe.db.get_value("Field of study", doc.filiere, "name_of_field") if doc.filiere else ""

	motif = (motif or doc.status_comment or "").strip()

	try:
		frappe.sendmail(
			recipients=[doc.email],
			sender=sender,
			subject=_("Résultat de votre candidature - {0}").format(_nom_etablissement()),
			template="candidature_rejection",
			args={
				"first_name": doc.first_name,
				"last_name": doc.last_name,
				"doc_name": doc.name,
				"academic_year": academic_year,
				"filiere": filiere_label,
				"niveau": doc.niveau or "",
				"motif": motif,
				"logo_url": get_school_logo_url(),
			},
			now=True,
		)
		frappe.logger().info(f"Email rejet envoyé à {doc.email} pour {doc.name}")
	except Exception as e:
		frappe.log_error(
			message=str(e), title=f"Échec email rejet {doc.name}"
		)
