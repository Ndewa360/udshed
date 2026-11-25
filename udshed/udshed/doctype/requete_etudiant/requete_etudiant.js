// Requête étudiante : prise en charge, réponse, rejet, clôture, accès à la note (réclamation).
frappe.ui.form.on("Requete Etudiant", {
	refresh(frm) {
		if (frm.is_new() || ["Répondue", "Rejetée", "Clôturée"].includes(frm.doc.statut)) return;
		const api = "udshed.api.requetes.";
		if (frm.doc.statut === "Soumise") {
			frm.add_custom_button(__("Prendre en charge"), () =>
				frappe.call(api + "prendre_en_charge", { requete: frm.doc.name }).then(() => frm.reload_doc()));
		}
		const repondre = (statut) => frappe.prompt(
			{ fieldname: "reponse", fieldtype: "Small Text", label: __("Réponse à l'étudiant"), reqd: 1, default: frm.doc.reponse },
			(v) => frappe.call(api + "repondre", { requete: frm.doc.name, reponse: v.reponse, statut }).then(() => frm.reload_doc()),
			statut === "Rejetée" ? __("Rejeter la requête") : __("Répondre"));
		frm.add_custom_button(__("Répondre"), () => repondre("Répondue")).addClass("btn-primary");
		frm.add_custom_button(__("Rejeter"), () => repondre("Rejetée"));
		frm.add_custom_button(__("Clôturer"), () => repondre("Clôturée"));
		if (frm.doc.type_requete === "Réclamation de note") {
			frm.add_custom_button(__("Ouvrir la note pour correction"), () =>
				frappe.call(api + "note_concernee", { requete: frm.doc.name }).then((r) =>
					frappe.set_route("Form", "Session Examen Note", r.message)));
		}
	},
});
