// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.ui.form.on("Session Reinscription", {
	validate(frm) {
		if (frm.doc.date_ouverture && frm.doc.date_cloture) {
			if (frm.doc.date_ouverture >= frm.doc.date_cloture) {
				frappe.msgprint("La date d'ouverture doit être antérieure à la date de clôture");
				frappe.validated = false;
			}
		}
	}
});
