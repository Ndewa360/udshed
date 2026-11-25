// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.ui.form.on("Progression Academique", {
	refresh(frm) {
		const couleurs = {
			"Admis au niveau supérieur": "green",
			"Redoublement": "orange",
			"Fin de parcours": "blue",
			"Décision administrative requise": "red",
			"En attente de publication": "gray",
		};
		if (frm.doc.statut) {
			frm.set_intro(frm.doc.motif || frm.doc.statut, couleurs[frm.doc.statut] || "gray");
		}
		if (frm.doc.reinscription) {
			frm.disable_form();
			frm.set_intro(__("Progression utilisée par la réinscription {0} : elle n'est plus modifiable.", [frm.doc.reinscription]), "blue");
		}
		if (frm.doc.filiere_cible) {
			charger_niveaux(frm);
		}
	},

	filiere_cible(frm) {
		charger_niveaux(frm);
	},
});

// Rappel des niveaux réellement configurés dans la filière
function charger_niveaux(frm) {
	frappe.call({
		method: "udshed.api.reregistration.get_ordered_levels",
		args: { filiere: frm.doc.filiere_cible },
		callback(r) {
			const niveaux = (r.message || []).map((l) => l.level).join(", ");
			frm.set_df_property("niveau_cible", "description",
				__("Niveaux de la filière : {0}", [niveaux || "aucun"]));
		},
	});
}
