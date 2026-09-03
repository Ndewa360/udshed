import frappe
from frappe.model.document import Document


@frappe.whitelist()
def get_current_student_profile():
	"""Retourne le profil de l'étudiant connecté (page espace étudiant)."""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw("Vous devez être connecté pour accéder à votre espace étudiant.")

	filters = frappe._dict()
	if frappe.db.exists("Student", {"utilisateur": user}):
		filters["utilisateur"] = user
	elif frappe.db.exists("Student", {"email": user}):
		filters["email"] = user
	else:
		frappe.throw("Aucun profil étudiant n'est lié à votre compte.")

	student = frappe.get_doc("Student", filters)
	filiere_label = ""
	if student.filiere:
		filiere_label = frappe.db.get_value("Field of study", student.filiere, "name_of_field") or student.filiere

	return {
		"matricule": student.matricule or student.name,
		"nom": student.nom or "",
		"prenom": student.prenom or "",
		"nom_complet": f"{student.nom or ''} {student.prenom or ''}".strip(),
		"cycle": student.cycle or "",
		"niveau_actuel": student.niveau_actuel or "",
		"email": student.email or "",
		"sexe": student.sexe or "",
		"phone": student.phone or "",
		"parent_phone": student.parent_phone or "",
		"email_parent": student.email_parent or "",
		"birth_date": frappe.utils.format_date(student.birth_date) if student.birth_date else "",
		"birth_place": student.birth_place or "",
		"photo": student.photo or "",
		"filiere": student.filiere or "",
		"filiere_label": filiere_label,
	}


class Student(Document):

	def validate(self):
		self.definir_nom_complet()
		self.determiner_cycle()

	def definir_nom_complet(self):
		self.nom_complet = f"{self.matricule or ''} - {self.nom or ''} {self.prenom or ''}".strip()

	def determiner_cycle(self):
		niveau = self.niveau_actuel
		if not niveau:
			return

		if niveau.startswith("Licence"):
			self.cycle = "Licence"
		elif niveau.startswith("Master"):
			self.cycle = "Master"
		elif niveau.startswith("BTS"):
			self.cycle = "BTS"
		else:
			self.cycle = "Licence"

	def before_save(self):
		# Le matricule = le nom auto-généré STU-0001
		# Disponible seulement après la première sauvegarde
		if self.name and not self.name.startswith("new-"):
			self.matricule = self.name

	def after_insert(self):
		# Après insertion le name est disponible → on met à jour le matricule
		self.db_set("matricule", self.name)

		# Crée automatiquement un compte utilisateur Frappe lié à l'étudiant
		if not frappe.db.exists("User", self.email):
			user = frappe.get_doc({
				"doctype": "User",
				"email": self.email,
				"first_name": self.nom,
				"last_name": self.prenom,
				"send_welcome_email": 0,
				"roles": [
					{"role": "Student"}
				]
			})
			user.insert(ignore_permissions=True)
		else:
			user = frappe.get_doc("User", self.email)

		# Lie l'utilisateur à l'étudiant
		self.db_set("utilisateur", user.name)

	def after_delete(self):
		# Supprime le compte utilisateur quand l'étudiant est supprimé
		if self.utilisateur and frappe.db.exists("User", self.utilisateur):
			frappe.delete_doc("User", self.utilisateur, ignore_permissions=True)
