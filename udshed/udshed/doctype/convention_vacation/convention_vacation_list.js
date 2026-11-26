// Conventions de vacation : statut en couleur dans la liste.
frappe.listview_settings["Convention Vacation"] = {
	add_fields: ["statut", "convention_signee"],
	get_indicator(doc) {
		const couleurs = { "Brouillon": "gray", "Envoyée à l'enseignant": "orange", "Signée": "green", "Résiliée": "red" };
		return [__(doc.statut), couleurs[doc.statut] || "gray", "statut,=," + doc.statut];
	},
};
