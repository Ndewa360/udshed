"""Correction d'une note après coup (réclamation, erreur de saisie, jury…).

1. Verrou : la note d'une ANNÉE CLOSE (antérieure à l'année en cours des
   réglages) ne se modifie plus par la saisie : elle passe par une
   « Correction Note » motivée. L'enseignant de la matière la DEMANDE ; un
   coordonnateur ou le responsable des admissions l'APPROUVE (leurs propres
   demandes s'appliquent aussitôt, toujours enregistrées).
2. Historique : chaque correction garde avant / après / motif / auteurs, et
   la note a son historique de modifications (track_changes).
3. Cascade : résultat d'unité, résultats académiques de la session, décision
   annuelle, puis progression si elle n'a pas encore servi.
4. Réinscription déjà faite pour l'année suivante : dettes ajoutées / retirées
   si la décision de passage ne change pas ; sinon alerte à la scolarité
   (décision humaine : l'étudiant suit peut-être déjà ses cours).
5. L'étudiant est prévenu (email + notification).
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

DOCTYPE = "Correction Note"
ROLES_APPROBATION = {"System Manager", "Registration Manager", "Coordonateur"}

# Composantes corrigeables : (champ, libellé, drapeau de saisie)
COMPOSANTES = [
	("note_examen", "Examen", "examen_saisi"),
	("note_examen_rattrapage", "Rattrapage", "rattrapage_saisi"),
	("note_tp", "TP", "tp_saisi"),
	("note_cctp", "CCTP", "cctp_saisi"),
	("note_examtp", "Examen TP", "examtp_saisi"),
	("note_rapport", "Rapport", None),
	("note_competence", "Compétence", None),
]
PREFIXE_CC = "cc:"


# ---------------------------------------------------------------------- #
#  Année close et verrou
# ---------------------------------------------------------------------- #
def _debut(annee):
	try:
		return int(str(annee).split("-")[0])
	except (TypeError, ValueError):
		return None


def annee_close(academic_year):
	"""Vrai si l'année est antérieure à l'année en cours des réglages."""
	courante = frappe.db.get_single_value("Udshed Setting", "current_year")
	a, c = _debut(academic_year), _debut(courante)
	return bool(a and c and a < c)


def valeurs(note):
	"""Valeurs corrigeables d'une note : composantes + notes de CC (par ligne)."""
	res = {champ: note.get(champ) for champ, _l, _d in COMPOSANTES}
	for i, row in enumerate(note.get("notes_cc") or []):
		res[f"{PREFIXE_CC}{i}"] = row.note_cc
	return res


def _egal(a, b):
	# Les colonnes Currency ramènent une note absente à 0.0 : absent = 0.
	return round(flt(a or 0), 2) == round(flt(b or 0), 2)


def verifier_modification(note):
	"""Appelé par Session Examen Note.validate : une note existante d'une année
	close ne change plus hors d'une correction approuvée."""
	if note.is_new() or frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.correction_note_autorisee:
		return
	annee = frappe.db.get_value("Session Examen", note.session_examen, "academic_year")
	if not annee_close(annee):
		return
	avant = note.get_doc_before_save()
	if not avant:
		return
	v_avant, v_apres = valeurs(avant), valeurs(note)
	if all(_egal(v_avant.get(k), v_apres.get(k)) for k in set(v_avant) | set(v_apres)):
		return
	frappe.throw(
		_("L'année {0} est close : la note ne se modifie plus directement. Utilisez « Demander une correction » "
		  "sur la note (motif obligatoire, approbation par la coordination).").format(annee),
		title=_("Année close"),
	)


# ---------------------------------------------------------------------- #
#  Demande
# ---------------------------------------------------------------------- #
def peut_approuver(user=None):
	return bool(set(frappe.get_roles(user or frappe.session.user)) & ROLES_APPROBATION)


@frappe.whitelist()
def composantes_de_la_note(note):
	"""Composantes saisissables d'une note, pour le formulaire de demande."""
	from udshed.api.saisie_notes import _verifier_acces_enseignant

	doc = frappe.get_doc("Session Examen Note", note)
	_verifier_acces_enseignant(doc.teaching_unit)
	lignes = [{"champ": c, "composante": l, "valeur": doc.get(c)} for c, l, _d in COMPOSANTES
			  if doc.get(c) not in (None, "") or (_d and doc.get(_d))]
	for i, row in enumerate(doc.notes_cc or []):
		lignes.append({"champ": f"{PREFIXE_CC}{i}", "composante": row.cc_label or f"CC {i + 1}", "valeur": row.note_cc})
	return {"lignes": lignes, "note_finale": doc.note_finale, "peut_approuver": peut_approuver()}


@frappe.whitelist()
def demander_correction(note, lignes, motif_type, motif):
	"""Crée la demande ; appliquée aussitôt si l'auteur peut approuver."""
	if isinstance(lignes, str):
		lignes = json.loads(lignes)
	doc = frappe.get_doc({
		"doctype": DOCTYPE, "session_examen_note": note, "motif_type": motif_type, "motif": motif,
		"lignes": [{"champ": l["champ"], "nouvelle_valeur": l.get("nouvelle_valeur")} for l in lignes or []],
	})
	doc.insert()
	if peut_approuver():
		doc.reload()
		doc.approuver()
	return {"name": doc.name, "statut": frappe.db.get_value(DOCTYPE, doc.name, "statut")}


def preparer(doc):
	"""Complète la demande depuis la note : contexte, anciennes valeurs, contrôles."""
	from udshed.api.saisie_notes import _verifier_acces_enseignant

	note = frappe.get_doc("Session Examen Note", doc.session_examen_note)
	_verifier_acces_enseignant(note.teaching_unit)
	doc.student = note.student
	doc.teaching_unit = note.teaching_unit
	doc.session_examen = note.session_examen
	doc.academic_year = frappe.db.get_value("Session Examen", note.session_examen, "academic_year")
	if doc.is_new():
		doc.demandee_par = frappe.session.user
		doc.note_finale_avant = flt(note.note_finale)
	actuelles = valeurs(note)
	libelles = {c: l for c, l, _d in COMPOSANTES}
	for i, row in enumerate(note.notes_cc or []):
		libelles[f"{PREFIXE_CC}{i}"] = row.cc_label or f"CC {i + 1}"
	if not doc.lignes:
		frappe.throw(_("Indiquez au moins une note à corriger."))
	change = False
	for l in doc.lignes:
		if l.champ not in libelles:
			frappe.throw(_("Composante inconnue : {0}.").format(l.champ))
		if l.nouvelle_valeur is None or not (0 <= flt(l.nouvelle_valeur) <= 20):
			frappe.throw(_("{0} : la nouvelle note doit être comprise entre 0 et 20.").format(libelles[l.champ]))
		l.composante = libelles[l.champ]
		if doc.is_new():
			l.ancienne_valeur = actuelles.get(l.champ)
		change = change or not _egal(l.ancienne_valeur, l.nouvelle_valeur)
	if not change:
		frappe.throw(_("Les nouvelles notes sont identiques aux anciennes : aucune correction à faire."))
	if not (doc.motif or "").strip():
		frappe.throw(_("Le motif de la correction est obligatoire."))


# ---------------------------------------------------------------------- #
#  Application
# ---------------------------------------------------------------------- #
def appliquer(doc):
	if doc.statut != "En attente":
		frappe.throw(_("Cette demande est déjà traitée ({0}).").format(doc.statut))
	if not peut_approuver():
		frappe.throw(_("L'approbation d'une correction est réservée à la coordination et à la scolarité."),
					 frappe.PermissionError)
	note = frappe.get_doc("Session Examen Note", doc.session_examen_note)
	for l in doc.lignes:
		if l.champ.startswith(PREFIXE_CC):
			idx = int(l.champ[len(PREFIXE_CC):])
			if idx < len(note.notes_cc):
				note.notes_cc[idx].note_cc = flt(l.nouvelle_valeur)
		else:
			note.set(l.champ, flt(l.nouvelle_valeur))
			drapeau = next((d for c, _l, d in COMPOSANTES if c == l.champ), None)
			if drapeau:
				note.set(drapeau, 1)
	note.add_comment("Comment", _("Note corrigée ({0}) : {1} — {2}").format(doc.name, doc.motif_type, doc.motif))
	frappe.flags.correction_note_autorisee = True
	try:
		note.save(ignore_permissions=True)
	finally:
		frappe.flags.correction_note_autorisee = False

	consequences = recalculer_apres_correction(note)
	doc.db_set({
		"statut": "Appliquée", "traitee_par": frappe.session.user, "traitee_le": now_datetime(),
		"note_finale_apres": flt(note.note_finale), "bilan": "\n".join(consequences),
	})
	notifier_etudiant(doc, note)
	# Réclamation de note ouverte sur cette matière : la correction y est rattachée.
	from udshed.api.requetes import lier_correction

	lier_correction(doc)
	return {"statut": "Appliquée", "bilan": consequences}


def refuser(doc, motif):
	if doc.statut != "En attente":
		frappe.throw(_("Cette demande est déjà traitée ({0}).").format(doc.statut))
	if not peut_approuver():
		frappe.throw(_("Le refus d'une correction est réservé à la coordination et à la scolarité."),
					 frappe.PermissionError)
	if not (motif or "").strip():
		frappe.throw(_("Indiquez le motif du refus."))
	doc.db_set({"statut": "Refusée", "traitee_par": frappe.session.user, "traitee_le": now_datetime(),
				"motif_refus": motif})
	if doc.demandee_par and doc.demandee_par != frappe.session.user:
		_notifier_utilisateurs([doc.demandee_par], _("Correction de note refusée : {0}").format(doc.name),
							   _("Motif : {0}").format(motif), DOCTYPE, doc.name)


# ---------------------------------------------------------------------- #
#  Cascade
# ---------------------------------------------------------------------- #
def recalculer_apres_correction(note):
	"""Recalcule tout ce qui dépend de la note ; retourne la liste des conséquences."""
	from udshed.api.progression import calculer_progression
	from udshed.api.resultat_academique import _calculer_resultat_annee, _calculer_resultat_session
	from udshed.api.saisie_notes import TYPE_NORMALE

	consequences = []
	sess = frappe.db.get_value("Session Examen", note.session_examen, ["academic_year", "semestre"], as_dict=True)
	annee = sess.academic_year
	# Résultat d'unité : recalculé par Session Examen Note.on_update.
	# Résultats académiques de la matière (meilleure note normale / rattrapage).
	for s in frappe.get_all("Session Examen", filters={"academic_year": annee, "semestre": sess.semestre,
													   "type_dexamen": TYPE_NORMALE}, pluck="name"):
		if frappe.db.exists("Session Examen Note", {"session_examen": s, "student": note.student,
													"teaching_unit": note.teaching_unit, "statut": "Publié"}):
			_calculer_resultat_session(note.student, s, teaching_unit=note.teaching_unit)
			consequences.append(_("Résultat de la matière recalculé."))
			break
	try:
		_calculer_resultat_annee(note.student, annee)
		consequences.append(_("Décision annuelle {0} recalculée.").format(annee))
	except Exception:
		frappe.log_error(title=f"Correction de note : décision annuelle {note.student} {annee}")

	prog = frappe.db.get_value("Progression Academique", {"student": note.student, "annee_source": annee},
							   ["name", "statut", "niveau_cible", "reinscription", "corrigee"], as_dict=True)
	if prog and (prog.reinscription or prog.corrigee):
		consequences.extend(_reinscription_deja_faite(note, annee, prog))
	else:
		doc = calculer_progression(note.student, annee)
		if doc:
			consequences.append(_("Progression {0} recalculée : {1}.").format(annee, doc.statut))
	return consequences


def _reinscription_deja_faite(note, annee, prog):
	"""Progression déjà utilisée : dettes mises à jour si la décision ne change
	pas, sinon alerte (décision humaine)."""
	from udshed.api.progression import evaluer_progression
	from udshed.api.reregistration import _dettes_reportees, _resolve_level_name, get_next_academic_year

	student_doc = frappe.get_doc("Student", note.student)
	filiere = frappe.db.get_value("Progression Academique", prog.name, "filiere_source") or student_doc.filiere
	niveau = frappe.db.get_value("Progression Academique", prog.name, "niveau_source")
	nouvelle = evaluer_progression(student_doc, filiere, niveau, annee)
	annee_suivante = get_next_academic_year(annee)
	reg_name = frappe.db.get_value("Academic Reregistration", {"student": note.student, "academic_year": annee_suivante,
															   "statut": "Validée"}, "name")
	if nouvelle.get("statut") != prog.statut or (nouvelle.get("niveau_cible") or None) != (prog.niveau_cible or None):
		message = _("La correction d'une note de {0} change la décision de passage de {1} : « {2} » devient « {3} » "
					"({4}). La réinscription {5} n'a pas été modifiée : décision de la scolarité requise.").format(
			annee, note.student, prog.statut, nouvelle.get("statut"), nouvelle.get("motif") or "",
			reg_name or _("(aucune)"))
		frappe.get_doc("Progression Academique", prog.name).add_comment("Comment", message)
		if reg_name:
			frappe.get_doc("Academic Reregistration", reg_name).add_comment("Comment", message)
		_alerter_scolarite(_("Décision de passage à revoir : {0}").format(note.student), message,
						   "Academic Reregistration" if reg_name else "Progression Academique", reg_name or prog.name)
		return [message]

	if not reg_name:
		return [_("Décision de passage inchangée ({0}).").format(prog.statut)]
	reg = frappe.get_doc("Academic Reregistration", reg_name)
	niveau_name = _resolve_level_name(filiere, niveau)
	sans = []
	attendues = {d["teaching_unit"]: d for d in _dettes_reportees(note.student, filiere, niveau, niveau_name,
																  annee, annee_suivante, sans)}
	actuelles = {c.teaching_unit for c in reg.cours_inscrits if c.source == "dette"}
	retirees = actuelles - set(attendues)
	ajoutees = set(attendues) - actuelles
	if not (retirees or ajoutees):
		return [_("Décision de passage et dettes inchangées.")]
	reg.cours_inscrits = [c for c in reg.cours_inscrits if not (c.source == "dette" and c.teaching_unit in retirees)]
	for tu in ajoutees:
		d = attendues[tu]
		reg.append("cours_inscrits", {"teaching_unit": tu, "intitule": d["intitule"], "semestre": d["semestre"],
									  "statut": "Inscrit", "inscrire": 1, "est_obligatoire": 1, "source": "dette",
									  "verrouille": 1, "motif": d["motif"], "credits": d["credits"]})
	reg.flags.ignore_validate = True
	reg.flags.ignore_mandatory = True
	reg.save(ignore_permissions=True)
	intitules = lambda tus: ", ".join(frappe.db.get_value("Teaching Unit", t, "intitule_cours") or t for t in tus)
	message = _("Réinscription {0} mise à jour après correction de note : dettes retirées [{1}], ajoutées [{2}].").format(
		reg.name, intitules(retirees) or "—", intitules(ajoutees) or "—")
	reg.add_comment("Comment", message)
	return [message]


# ---------------------------------------------------------------------- #
#  Notifications
# ---------------------------------------------------------------------- #
def _notifier_utilisateurs(users, sujet, message, doctype, name):
	for user in set(users):
		if not user or user in ("Administrator", "Guest") or not frappe.db.get_value("User", user, "enabled"):
			continue
		frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert", "subject": sujet,
						"email_content": message, "document_type": doctype, "document_name": name}
					   ).insert(ignore_permissions=True)


def _alerter_scolarite(sujet, message, doctype, name):
	users = []
	for role in ("Registration Manager", "Agent de scolarité"):
		users += frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
	_notifier_utilisateurs(users, sujet, message, doctype, name)


def notifier_etudiant(doc, note):
	student = frappe.db.get_value("Student", note.student, ["email", "utilisateur", "nom", "prenom"], as_dict=True)
	if not student:
		return
	matiere = frappe.db.get_value("Teaching Unit", note.teaching_unit, "intitule_cours") or note.teaching_unit
	from udshed.utils.compte_etudiant import notifier_etudiant

	notifier_etudiant(student.utilisateur, _("Note corrigée : {0}").format(matiere),
					  _("{0} : {1} → {2}/20").format(matiere, doc.note_finale_avant, note.note_finale))
	if not student.email:
		return
	try:
		from udshed.utils.etablissement import etablissement

		frappe.sendmail(
			recipients=[student.email],
			subject=_("Correction de votre note de {0} - {1}").format(matiere, etablissement().nom),
			template="correction_note",
			args={"nom": " ".join(x for x in [student.nom, student.prenom] if x), "matiere": matiere,
				  "annee": doc.academic_year, "avant": doc.note_finale_avant, "apres": note.note_finale,
				  "motif_type": doc.motif_type, "lien": frappe.utils.get_url("/app/mon-espace-etudiant")},
			delayed=True,
		)
	except Exception:
		frappe.log_error(title=f"Email de correction de note {doc.name}")
