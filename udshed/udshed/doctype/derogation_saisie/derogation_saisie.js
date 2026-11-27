// Dérogation de saisie : le doyen ou le vice-doyen de la faculté accorde (jusqu'à une date) ou refuse.
frappe.ui.form.on("Derogation Saisie", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.statut !== "Demandée") return;
		if (!(frappe.user.has_role("Doyen") || frappe.user.has_role("Vice-Doyen") || frappe.user.has_role("System Manager"))) return;
		const decider = (accorder) => {
			const champs = [{ fieldtype: "Small Text", fieldname: "commentaire", label: __("Commentaire (facultatif)") }];
			if (accorder) {
				champs.unshift({ fieldtype: "Datetime", fieldname: "valable_jusqu_au", label: __("Saisie autorisée jusqu'au"),
					reqd: 1, default: frappe.datetime.add_days(frappe.datetime.now_datetime(), 3) });
			}
			frappe.prompt(champs, (v) => frappe.xcall("udshed.api.saisie_periode.decider_derogation", {
				name: frm.doc.name, accorder: accorder ? 1 : 0, valable_jusqu_au: v.valable_jusqu_au, commentaire: v.commentaire,
			}).then(() => frm.reload_doc()), accorder ? __("Accorder la réouverture") : __("Refuser la demande"));
		};
		frm.add_custom_button(__("Accorder"), () => decider(true)).addClass("btn-primary");
		frm.add_custom_button(__("Refuser"), () => decider(false));
	},
});
