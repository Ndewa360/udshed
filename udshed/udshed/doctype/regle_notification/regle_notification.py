# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class RegleNotification(Document):
	def validate(self):
		import frappe

		for champ in ("sujet_personnalise", "message_personnalise"):
			if (self.get(champ) or "").strip():
				try:
					frappe.render_template(self.get(champ), {"sujet": "", "message": "", "lien": "", "destinataire": ""})
				except Exception as e:
					frappe.throw(frappe._("Texte personnalisé invalide : {0}").format(e))
