import frappe
from frappe.utils import now_datetime
from udshed.utils.niveaux import prochain_niveau


def get_context(context):
	"""Context du web form de réinscription.

	Fournit la liste des sessions de réinscription ouvertes pour
	le pré-remplissage de l'année académique.
	"""
	context.open_sessions = frappe.get_all(
		"Session Reinscription",
		filters={"statut": "Ouverte"},
		fields=["name", "academic_year", "date_ouverture", "date_cloture"],
	)
	return context


@frappe.whitelist(allow_guest=True)
def verify_student(matricule):
	"""Identifie un ancien étudiant par son matricule et prépare sa réinscription.

	Args:
		matricule: name/ID de l'étudiant (Student)

	Returns:
		dict: infos de l'étudiant, filière et niveau à proposer pour la réinscription.
	"""
	if not frappe.db.exists("Student", matricule):
		frappe.throw(f"Aucun étudiant trouvé avec le matricule {matricule}")

	student = frappe.get_doc("Student", matricule)

	derniere = frappe.get_all(
		"Academic Reregistration",
		filters={"student": matricule},
		fields=["filiere", "niveau", "semestre", "academic_year"],
		order_by="creation desc",
		limit_page_length=1,
	)

	filiere = derniere[0].filiere if derniere else student.filiere
	niveau = derniere[0].niveau if derniere else student.niveau_actuel
	semestre = derniere[0].semestre if derniere else None

	niveau_suivant = None
	if filiere and niveau:
		niveau_suivant = prochain_niveau(filiere, niveau)

	filiere_label = frappe.db.get_value("Field of study", filiere, "name_of_field") or filiere

	return {
		"exists": True,
		"student_name": f"{student.nom} {student.prenom}",
		"matricule": student.name,
		"email": student.email,
		"filiere": filiere,
		"filiere_label": filiere_label,
		"niveau": niveau,
		"niveau_suivant": niveau_suivant,
		"semestre": semestre,
	}


@frappe.whitelist()
def mes_reinscriptions(matricule):
	"""Liste les réinscriptions d'un étudiant pour consultation."""
	if not matricule or not frappe.db.exists("Student", matricule):
		frappe.throw("Veuillez identifier un étudiant valide avant de consulter.")

	liste = frappe.get_all(
		"Academic Reregistration",
		filters={"student": matricule},
		fields=["name", "academic_year", "niveau", "semestre", "statut", "creation", "fiche_telechargee"],
		order_by="creation desc",
	)

	resultat = []
	for r in liste:
		resultat.append({
			"name": r.name,
			"matricule": matricule,
			"academic_year": r.academic_year,
			"niveau": r.niveau or "",
			"semestre": r.semestre or "",
			"statut": r.statut or "",
			"creation": str(r.creation),
			"fiche_disponible": not r.fiche_telechargee,
			"fiche_telechargee": bool(r.fiche_telechargee),
		})
	return resultat


@frappe.whitelist()
def detail_reinscription(matricule, reinscription):
	"""Retourne l'historique d'une réinscription : résultats précédents + matières inscrites."""
	if not matricule or not frappe.db.exists("Student", matricule):
		frappe.throw("Veuillez identifier un étudiant valide avant de consulter.")

	doc = frappe.get_doc("Academic Reregistration", reinscription)

	if doc.student != matricule:
		frappe.throw("Cette réinscription ne correspond pas au matricule saisi.")

	return {
		"name": doc.name,
		"academic_year": doc.academic_year,
		"niveau": doc.niveau or "",
		"semestre": doc.semestre or "",
		"statut": doc.statut or "",
		"filiere": frappe.db.get_value("Field of study", doc.filiere, "name_of_field") or doc.filiere,
		"niveau_precedent": doc.niveau_precedent or "",
		"creation": str(doc.creation),
		"resultats_precedents": [
			{
				"intitule": r.intitule or r.teaching_unit,
				"semestre": r.semestre or "",
				"note": r.note,
				"valide": bool(r.valide),
				"est_dette": bool(r.est_dette),
			}
			for r in doc.resultats_precedents
		],
		"cours_inscrits": [
			{
				"intitule": m.intitule or m.teaching_unit,
				"semestre": m.semestre or "",
				"statut": m.statut or "",
				"inscrire": bool(m.inscrire),
				"motif": m.motif or "",
			}
			for m in doc.cours_inscrits
		],
	}


@frappe.whitelist()
def telecharger_fiche_reinscription(matricule, reinscription):
	"""Génère et télécharge la fiche PDF d'une réinscription validée.

	Téléchargement unique : le champ fiche_telechargee passe à 1.
	"""
	if not matricule or not frappe.db.exists("Student", matricule):
		frappe.throw("Étudiant introuvable.")

	doc = frappe.get_doc("Academic Reregistration", reinscription)

	if doc.student != matricule:
		frappe.throw("Cette fiche ne correspond pas au matricule saisi.")

	if doc.fiche_telechargee:
		frappe.throw("Cette fiche a déjà été téléchargée. Contactez la scolarité pour tout complément.")

	try:
		from frappe.utils.pdf import get_pdf
		pdf = get_pdf(_construire_fiche(doc), {"page-size": "A4"})
	except Exception:
		frappe.log_error(f"Échec de génération PDF de la fiche {doc.name}", frappe.get_traceback())
		frappe.throw("La génération du PDF a échoué. Réessayez plus tard.")

	frappe.db.set_value("Academic Reregistration", doc.name, "fiche_telechargee", 1)

	frappe.response["filecontent"] = pdf
	frappe.response["filename"] = f"Fiche_Reinscription_{doc.name}.pdf"
	frappe.response["type"] = "download"


def _construire_fiche(doc):
	"""Construit le HTML de la fiche de réinscription."""
	student = frappe.get_doc("Student", doc.student)
	filiere_label = frappe.db.get_value("Field of study", doc.filiere, "name_of_field") or doc.filiere
	nom_ecole = frappe.db.get_single_value("Udshed Setting", "school_name") or ""

	lignes_cours = "\n".join(
		f"<tr><td>{r.intitule or r.teaching_unit}</td>"
		f"<td style='text-align:center'>{r.semestre or ''}</td>"
		f"<td style='text-align:center'>{r.statut or ''}</td>"
		f"<td style='text-align:center'>{'Oui' if r.inscrire else 'Non'}</td>"
		f"<td>{r.motif or ''}</td></tr>"
		for r in doc.cours_inscrits
	)

	lignes_resultats = "\n".join(
		f"<tr><td>{r.intitule or r.teaching_unit}</td>"
		f"<td style='text-align:center'>{r.semestre or ''}</td>"
		f"<td style='text-align:center'>{r.note or 0}/20</td>"
		f"<td style='text-align:center'>{'Validé' if r.valide else 'Dette'}</td></tr>"
		for r in doc.resultats_precedents
	)

	date_demande = doc.creation.strftime("%d/%m/%Y %H:%M") if hasattr(doc.creation, "strftime") else doc.creation

	return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Fiche de réinscription {doc.name}</title>
<style>
	body {{ font-family: Arial, sans-serif; font-size: 12px; color: #333; }}
	h1 {{ text-align: center; font-size: 18px; margin: 0 0 2px; }}
	h2 {{ text-align: center; font-size: 14px; margin: 0 0 18px; font-weight: normal; }}
	h3 {{ font-size: 13px; margin: 14px 0 6px; }}
	.info {{ width: 100%; border-collapse: collapse; margin-bottom: 18px; }}
	.info td {{ padding: 3px 6px; }}
	.info td.l {{ font-weight: bold; width: 140px; }}
	table.data {{ width: 100%; border-collapse: collapse; margin-bottom: 18px; }}
	table.data th, table.data td {{ border: 1px solid #666; padding: 4px 6px; }}
	table.data th {{ background: #eee; }}
	.pied {{ margin-top: 24px; font-size: 11px; color: #666; }}
</style>
</head>
<body>
	<h1>{nom_ecole}</h1>
	<h2>FICHE DE RÉINSCRIPTION — {doc.academic_year}</h2>

	<h3>Identité de l'étudiant</h3>
	<table class="info">
		<tr>
			<td class="l">Nom :</td><td>{student.nom}</td>
			<td class="l">Prénom :</td><td>{student.prenom}</td>
		</tr>
		<tr>
			<td class="l">Matricule :</td><td>{student.name}</td>
			<td class="l">Email :</td><td>{student.email or "—"}</td>
		</tr>
		<tr>
			<td class="l">Filière :</td><td>{filiere_label}</td>
			<td class="l">Niveau :</td><td>{doc.niveau}</td>
		</tr>
		<tr>
			<td class="l">Semestre :</td><td>{doc.semestre}</td>
			<td class="l">Réf. :</td><td>{doc.name}</td>
		</tr>
		<tr>
			<td class="l">Date :</td><td>{date_demande}</td>
			<td class="l">Statut :</td><td>{doc.statut}</td>
		</tr>
	</table>

	<h3>Matières inscrites ({len(doc.cours_inscrits)})</h3>
	<table class="data">
		<thead>
			<tr><th>Intitulé</th><th>Semestre</th><th>Statut</th><th>À inscrire</th><th>Motif</th></tr>
		</thead>
		<tbody>{lignes_cours or "<tr><td colspan='5' style='text-align:center'>Aucune matière</td></tr>"}</tbody>
	</table>

	<h3>Résultats de l'année précédente ({len(doc.resultats_precedents)})</h3>
	<table class="data">
		<thead>
			<tr><th>Intitulé</th><th>Semestre</th><th>Note</th><th>Résultat</th></tr>
		</thead>
		<tbody>{lignes_resultats or "<tr><td colspan='4' style='text-align:center'>Aucun résultat</td></tr>"}</tbody>
	</table>

	<p class="pied">Document généré automatiquement le {now_datetime().strftime("%d/%m/%Y à %H:%M")}. Ce document ne vaut pas preuve de paiement.</p>
</body>
</html>"""
