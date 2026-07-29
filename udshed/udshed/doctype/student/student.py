import frappe
from frappe.model.document import Document


class Student(Document):

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
