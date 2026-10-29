// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.listview_settings["Session Inscription Candidate"] = {
	get_indicator(doc) {
		const colors = {
			"En attente": "orange",
			"Dossier en cours d'examen": "blue",
			"Accepté": "green",
			"Refusé": "red",
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
		listview.page.add_action_item(
			__("Marquer inscrit"),
			() => mark_inscrit(listview),
			"check"
		);
	},
};

function change_status(listview) {
	const items = listview.get_checked_items(true);
	if (!items || !items.length) {
		frappe.msgprint(__("Veuillez sélectionner au moins un dossier candidat."));
		return;
	}

	const STATUSES = [
		"En attente",
		"Dossier en cours d'examen",
		"Accepté",
		"Refusé",
		"Inscrit",
	];

	const dialog = new frappe.ui.Dialog({
		title: __("Changer le statut ({0} dossier(s))", [items.length]),
		fields: [
			{ fieldtype: "Select", fieldname: "new_status", label: __("Nouveau statut"), options: STATUSES.join("\n"), reqd: 1 },
			{ fieldtype: "Small Text", fieldname: "comment", label: __("Observation / Motif"), description: __("Obligatoire si le statut est « Refusé »") },
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
		dialog.fields_dict.comment.toggle_reqd(v === "Refusé");
	});

	dialog.show();
}

function mark_inscrit(listview) {
	const items = listview.get_checked_items(true);
	if (!items || !items.length) {
		frappe.msgprint(__("Veuillez sélectionner au moins un dossier candidat."));
		return;
	}
	frappe.confirm(
		__("Marquer les {0} dossier(s) sélectionné(s) comme « Inscrit » ?", [items.length]),
		function () {
			apply_status_change(items, { new_status: "Inscrit", comment: "Inscrit via liste" }, null);
		}
	);
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
