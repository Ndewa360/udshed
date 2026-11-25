// Acte académique : délivrance (signature électronique ou manuscrite), refus, remise, téléchargement.
frappe.ui.form.on("Acte Academique", {
	refresh(frm) {
		if (frm.is_new()) return;
		const api = "udshed.api.actes.";
		const recharger = () => frm.reload_doc();
		if (frm.doc.statut === "Demandé") {
			frm.add_custom_button(__("Délivrer"), () =>
				frappe.confirm(__("Délivrer ce document ? Il sera signé (électroniquement ou à retirer selon le modèle)."), () =>
					frappe.call(api + "delivrer", { acte: frm.doc.name }).then(recharger))).addClass("btn-primary");
			frm.add_custom_button(__("Refuser"), () =>
				frappe.prompt({ fieldname: "motif", fieldtype: "Small Text", label: __("Motif du refus"), reqd: 1 },
					(v) => frappe.call(api + "refuser", { acte: frm.doc.name, motif: v.motif }).then(recharger),
					__("Refuser la demande")));
		}
		if (frm.doc.statut === "Prêt à retirer") {
			frm.add_custom_button(__("Marquer comme remis"), () =>
				frappe.call(api + "marquer_retire", { acte: frm.doc.name }).then(recharger));
		}
		if (["Disponible", "Prêt à retirer", "Retiré", "Demandé"].includes(frm.doc.statut)) {
			frm.add_custom_button(frm.doc.statut === "Prêt à retirer" ? __("Imprimer pour signature") : __("Télécharger"), () =>
				open_url_post("/api/method/" + api + "telecharger", { acte: frm.doc.name }, true));
		}
	},
});
