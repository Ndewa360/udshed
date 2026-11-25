// Demande de correction de note : approbation ou refus par la coordination.
frappe.ui.form.on("Correction Note", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.statut !== "En attente") return;
		const peut = frappe.user.has_role(["System Manager", "Registration Manager", "Coordonateur"]);
		if (!peut) return;
		frm.add_custom_button(__("Approuver et appliquer"), () => {
			frappe.confirm(__("Appliquer la correction ? Les résultats, la progression et la réinscription seront recalculés."), () =>
				frm.call("approuver").then((r) => {
					const bilan = ((r.message || {}).bilan || []).map((l) => frappe.utils.escape_html(l)).join("<br>");
					frappe.msgprint({ title: __("Correction appliquée"), message: bilan || __("Correction appliquée."), indicator: "green" });
					frm.reload_doc();
				})
			);
		}).addClass("btn-primary");
		frm.add_custom_button(__("Refuser"), () => {
			frappe.prompt({ fieldname: "motif", fieldtype: "Small Text", label: __("Motif du refus"), reqd: 1 },
				(v) => frm.call("refuser", { motif: v.motif }).then(() => frm.reload_doc()),
				__("Refuser la correction"));
		});
	},
});
