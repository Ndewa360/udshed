// Copyright (c) 2026, Udshed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Resultat UE", {
	refresh(frm) {
		// Tous les champs du document sont dérivés de la grille d'enseignement
		// et des notes publiées : le formulaire est en lecture seule.
		frm.set_readonly();

		if (frm.doc.statut) {
			const couleur = {
				"Validé": "green",
				"Non Validé": "red",
				"En attente": "orange",
			}[frm.doc.statut];
			if (couleur) {
				frm.dashboard.clear_headline();
				frm.dashboard.set_headline_alert(
					__("Statut de l'UE : ") + frm.doc.statut,
					couleur
				);
			}
		}
	},
});
