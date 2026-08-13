// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.ui.form.on("Session Examen", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.statut !== "Brouillon") {
			return;
		}
		frm.add_custom_button(__("Valider les notes"), function() {
			frappe.confirm(
				__("Valider toutes les notes de la session {0} ? Elles seront ensuite publiables.", [frm.doc.name]),
				() => {
					frappe.call("udshed.api.saisie_notes.valider_notes", {
						session: frm.doc.name
					}).then(r => {
						frappe.show_alert({
							message: __("Notes validées ({0}).", [r.message.validated]),
							indicator: "green"
						});
						frm.reload_doc();
					});
				}
			);
		});
		frm.add_custom_button(__("Publier"), function() {
			frappe.confirm(
				__("Publier la session {0} ? Les notes seront verrouillées.", [frm.doc.name]),
				() => {
					frappe.call("udshed.api.saisie_notes.publier_session", {
						session: frm.doc.name
					}).then(r => {
						frappe.show_alert({
							message: __("Session publiée."),
							indicator: "green"
						});
						frm.reload_doc();
					});
				}
			);
		}).addClass("btn-danger");
	}
});

frappe.ui.form.on("Session Examen Field of study Level", {
	filiere(frm, cdt, cdn){
        console.log("Filiere changed:", frm.doc.filiere);
		// met à jour le get_query du champ 'niveau' pour cette ligne
		frm.fields_dict['classes_concernees'].grid.update_docfield_property('niveau', 'get_query', function() {
			let row = locals[cdt][cdn];


			if (!row.filiere) {
				return {}; // pas de filtre si aucune filière
			}

			// console.log("Setting get_query for niveau with filiere:", locals);

			return {
				query: "udshed.api.course.get_levels",
				filters: { parent: row.filiere } // filtre Link vers Field of Study Level
			};
		});
	},
});