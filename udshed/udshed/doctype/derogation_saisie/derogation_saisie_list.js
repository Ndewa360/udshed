frappe.listview_settings["Derogation Saisie"] = {
	add_fields: ["statut"],
	get_indicator(doc) {
		const couleurs = { "Demandée": "orange", "Accordée": "green", "Refusée": "red" };
		return [__(doc.statut), couleurs[doc.statut] || "gray", "statut,=," + doc.statut];
	},
};
