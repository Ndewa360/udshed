// Jury de diplomation : recherche des candidats, proclamation, annulation.
frappe.ui.form.on("Jury Diplomation", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.statut !== "Proclamé") {
			frm.add_custom_button(__("Rechercher les candidats"), () =>
				frm.call("rechercher_candidats").then((r) => {
					frappe.show_alert({ message: __("{0} candidat(s) trouvé(s).", [r.message || 0]), indicator: "green" });
					frm.reload_doc();
				}));
			if ((frm.doc.candidats || []).length) {
				frm.add_custom_button(__("Proclamer les résultats"), () =>
					frappe.confirm(__("Proclamer ? Un diplôme sera créé pour chaque étudiant déclaré « Diplômé »."), () =>
						frm.call("proclamer").then((r) => {
							frappe.msgprint((r.message || {}).bilan || __("Résultats proclamés."));
							frm.reload_doc();
						}))).addClass("btn-primary");
			}
		} else {
			frm.add_custom_button(__("Annuler la proclamation"), () =>
				frappe.confirm(__("Annuler ? Les diplômes créés par ce jury seront annulés."), () =>
					frm.call("annuler_proclamation").then(() => frm.reload_doc())));
		}
	},
});
