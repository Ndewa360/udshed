// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.ui.form.on("Session Examen", {
	validate(frm) {
		if (frm.doc.date_debut && frm.doc.date_de_fin) {
			if (frm.doc.date_debut > frm.doc.date_de_fin) {
				frappe.throw(__("La date initiale de la session doit être antérieure ou égale à la date finale."));
			}
		}
	},
	refresh(frm) {
		if (frm.is_new() || frm.doc.statut !== "Brouillon") {
			return;
		}
		// Publication programmée : décision prise d'avance, exécutée à l'heure dite.
		if (frm.doc.publier_le) {
			frm.dashboard.set_headline_alert(__("Publication programmée le {0}.", [frappe.datetime.str_to_user(frm.doc.publier_le)]), "blue");
		}
		frm.add_custom_button(frm.doc.publier_le ? __("Modifier la programmation") : __("Programmer la publication"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Programmer la publication"),
				fields: [
					{ fieldtype: "HTML", options: `<p class="text-muted small">${__("La session sera publiée automatiquement à la date choisie, si toutes ses notes sont alors validées. Sinon, vous serez prévenu.")}</p>` },
					{ fieldtype: "Datetime", fieldname: "publier_le", label: __("Publier le"), default: frm.doc.publier_le },
				],
				primary_action_label: __("Programmer"),
				primary_action(v) {
					frappe.call("udshed.notifications.api.programmer_publication", { session: frm.doc.name, publier_le: v.publier_le || "" })
						.then(() => { d.hide(); frm.reload_doc(); });
				},
				secondary_action_label: frm.doc.publier_le ? __("Annuler la programmation") : null,
				secondary_action: frm.doc.publier_le ? () => frappe.call("udshed.notifications.api.programmer_publication", { session: frm.doc.name, publier_le: "" })
					.then(() => { d.hide(); frm.reload_doc(); }) : null,
			});
			d.show();
		});
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