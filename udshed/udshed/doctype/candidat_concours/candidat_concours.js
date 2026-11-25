// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.ui.form.on("Candidat Concours", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Renvoyer la convocation"), () => {
			frappe.confirm(__("Renvoyer la convocation par e-mail au candidat ?"), () => {
				frappe.call({
					method: "udshed.api.concours.renvoyer_convocation",
					args: { fiche: frm.doc.name },
					freeze: true,
				}).then(() => frappe.show_alert({ message: __("Convocation envoyée"), indicator: "green" }));
			});
		});
		frm.add_custom_button(__("Voir la candidature"), () => {
			frappe.set_route("Form", "Session Inscription Candidate", frm.doc.candidature);
		});

		// La décision du jury ne se saisit que pendant la délibération.
		frappe.db.get_value("Concours", frm.doc.concours, "statut").then((r) => {
			const deliberation = (r.message || {}).statut === "Délibération";
			frm.fields_dict.resultats.grid.update_docfield_property("decision", "read_only", deliberation ? 0 : 1);
			frm.fields_dict.resultats.grid.refresh();
			if (deliberation) {
				frm.set_intro(__("Délibération en cours : réglez la « Décision du jury » de chaque formation dans le tableau des résultats."), "blue");
			}
		});
	},
});
