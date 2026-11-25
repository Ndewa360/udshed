// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.listview_settings["Session Inscription Candidate"] = {
	get_indicator(doc) {
		const colors = {
			"En attente": "orange",
			"Dossier en cours d'examen": "blue",
			"Autorisé à concourir": "purple",
			"Liste d'attente": "yellow",
			"Accepté": "green",
			"Refusé": "red",
			"Désisté": "darkgrey",
			"Inscrit": "purple",
		};
		return [__(doc.candidature_status || "En attente"), colors[doc.candidature_status] || "gray", "candidature_status," + (doc.candidature_status || "En attente")];
	},

	onload(listview) {
		listview.page.add_action_item(
			__("Changer le statut"),
			() => change_status(listview),
			"arrow-right"
		);
	},
};

// « Accepté » est une offre de place : le candidat devient étudiant (« Inscrit », matricule)
// seulement en finalisant son inscription sur le portail. S'il ne vient pas, on enregistre
// son désistement : la place est reproposée au suivant de la liste d'attente.
frappe.ui.form.on("Session Inscription Candidate", {
	refresh(frm) {
		if (frm.is_new()) return;
		const statut = frm.doc.candidature_status;
		if (statut === "Accepté" && frm.doc.finaliser_avant) {
			const depasse = frappe.datetime.get_diff(frm.doc.finaliser_avant, frappe.datetime.get_today()) < 0;
			frm.dashboard.set_headline(
				depasse
					? __("Délai de finalisation dépassé ({0}) : la place sera libérée lors de la prochaine tâche quotidienne.", [frappe.datetime.str_to_user(frm.doc.finaliser_avant)])
					: __("Admis : en attente de la finalisation de l'inscription par le candidat, au plus tard le {0}.", [frappe.datetime.str_to_user(frm.doc.finaliser_avant)]),
				depasse ? "red" : "orange"
			);
		}
		if (["Accepté", "Liste d'attente"].includes(statut)) {
			frm.add_custom_button(__("Enregistrer un désistement"), () => {
				frappe.prompt(
					{ fieldtype: "Small Text", fieldname: "motif", label: __("Motif du désistement"), reqd: 1 },
					(v) => {
						frappe.call({
							method: "udshed.api.concours_finalisation.desister_candidature",
							args: { candidature: frm.doc.name, motif: v.motif },
							freeze: true,
						}).then((r) => {
							const promus = (r.message && r.message.promus) || [];
							let msg = __("Désistement enregistré.");
							if (promus.length) {
								msg += "<br>" + __("Place(s) reproposée(s) à :") + "<br>• "
									+ promus.map((p) => `${p.candidat} (${p.filiere})`).join("<br>• ");
							}
							frappe.msgprint(msg);
							frm.reload_doc();
						});
					},
					__("Le candidat ne vient pas"),
					__("Enregistrer")
				);
			});
		}
	},
});

function change_status(listview) {
	const items = listview.get_checked_items(true);
	if (!items || !items.length) {
		frappe.msgprint(__("Veuillez sélectionner au moins un dossier candidat."));
		return;
	}

	const STATUSES = [
		"En attente",
		"Dossier en cours d'examen",
		"Autorisé à concourir",
		"Accepté",
		"Refusé",
		"Désisté",
	];

	const dialog = new frappe.ui.Dialog({
		title: __("Changer le statut ({0} dossier(s))", [items.length]),
		fields: [
			{ fieldtype: "Select", fieldname: "new_status", label: __("Nouveau statut"), options: STATUSES.join("\n"), reqd: 1 },
			{ fieldtype: "Small Text", fieldname: "comment", label: __("Observation / Motif"), description: __("Obligatoire si le statut est « Refusé » ou « Désisté ». « Inscrit » n'est pas proposé : il est attribué quand le candidat finalise son inscription.") },
		],
		primary_action_label: __("Enregistrer"),
	});

	// The primary action is set below via buttons to iterate reliably.
	dialog.get_primary_btn().off("click").on("click", function () {
		dialog.get_primary_btn().prop("disabled", true).text(__("Enregistrement..."));
		const values = dialog.get_values();
		if (!values || !values.new_status) {
			dialog.get_primary_btn().prop("disabled", false).text(__("Enregistrer"));
			return;
		}
		apply_status_change(items, values, dialog);
	});
	dialog.set_value("new_status", "En attente");
	// Require a comment if the new status is "Refusé"
	dialog.get_field("new_status").$input.on("change", function () {
		const v = $(this).val();
		dialog.fields_dict.comment.toggle_reqd(v === "Refusé" || v === "Désisté");
	});

	dialog.show();
}

function apply_status_change(items, values, dialog) {
	const new_status = values.new_status;
	const comment = values.comment;

	const done = [];
	const fail = [];

	function next(i) {
		if (i >= items.length) {
			finish(done, fail, dialog, new_status);
			return;
		}
		const name = items[i].name || items[i];
		frappe
			.call({
				method: "udshed.udshed.doctype.session_inscription_candidate.session_inscription_candidate.update_candidate_status",
				args: { name: name, new_status: new_status, comment: comment },
			})
			.then(function (r) {
				done.push(name);
				next(i + 1);
			})
			.catch(function () {
				fail.push(name);
				next(i + 1);
			});
	}
	next(0);
}

function finish(done, fail, dialog, new_status) {
	if (dialog) {
		dialog.get_primary_btn().prop("disabled", false).text(__("Enregistrer"));
		dialog.hide();
	}
	let msg = __("Statut mis à jour vers « {0} » pour {1} dossier(s).", [new_status, done.length]);
	if (fail.length) {
		msg += "<br>" + __("Échec sur {0} dossier(s) : {1}", [fail.length, fail.join(", ")]);
	}
	frappe.msgprint(msg);
	cur_list.refresh();
}
