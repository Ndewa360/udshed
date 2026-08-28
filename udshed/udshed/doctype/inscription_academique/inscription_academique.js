// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.ui.form.on("Inscription Academique", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Télécharger la fiche PDF"), function () {
				const url =
					"/api/method/frappe.utils.print_format.download_pdf" +
					"?doctype=Inscription%20Academique" +
					"&name=" + encodeURIComponent(frm.doc.name) +
					"&format=Fiche%20Officielle%20UDM" +
					"&no_letterhead=1";
				window.open(url, "_blank");
			}, __("Actions"));
		}
	},

	dossier_origine(frm) {
		if (frm.doc.dossier_origine) {
			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "Session Inscription Candidate",
					filters: { name: frm.doc.dossier_origine },
					fieldname: ["full_name", "email", "birthdate", "birth_place", "phone", "filiere", "niveau"],
				},
				callback(r) {
					if (r.message) {
						const d = r.message;
						if (!frm.doc.nom_prenom) frm.set_value("nom_prenom", d.full_name);
						if (!frm.doc.email) frm.set_value("email", d.email);
						if (!frm.doc.date_naissance) frm.set_value("date_naissance", d.birthdate);
						if (!frm.doc.lieu_naissance) frm.set_value("lieu_naissance", d.birth_place);
						if (!frm.doc.telephone) frm.set_value("telephone", d.phone);
						if (!frm.doc.filiere) frm.set_value("filiere", d.filiere);
						if (!frm.doc.classe) frm.set_value("classe", d.niveau);
					}
				},
			});
		}
	},
});
