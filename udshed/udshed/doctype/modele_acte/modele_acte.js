// Modèle d'acte : ouverture de l'éditeur visuel et aperçu PDF.
frappe.ui.form.on("Modele Acte", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Ouvrir l'éditeur"), () => {
			frappe.route_options = { modele: frm.doc.name };
			frappe.set_route("editeur-modele-acte");
		}).addClass("btn-primary");
		frm.add_custom_button(__("Aperçu PDF"), () =>
			open_url_post("/api/method/udshed.api.actes.apercu_modele", { modele: frm.doc.name }, true));
	},
});
