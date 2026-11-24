// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

// La fiche sert au paramétrage (formations, places, épreuves, délai).
// Le déroulé du concours (candidats, notes, délibération, admissions) se pilote
// depuis la page « Gestion des concours ».
frappe.ui.form.on("Concours", {
	setup(frm) {
		// La campagne doit appartenir à l'année du concours.
		frm.set_query("session_inscription", () => ({
			filters: frm.doc.academic_year ? { academic_year: frm.doc.academic_year } : {},
		}));
		// Une épreuve propre ne peut viser qu'une filière déjà inscrite au concours.
		frm.set_query("filiere", "epreuves", () => ({
			filters: {
				name: ["in", (frm.doc.filieres || []).map((r) => r.filiere).filter(Boolean)],
			},
		}));
	},

	refresh(frm) {
		if (frm.is_new()) return;
		const ouvrir = () => {
			frappe.route_options = { concours: frm.doc.name };
			frappe.set_route("gestion-concours");
		};
		frm.add_custom_button(__("Gérer le concours"), ouvrir).addClass("btn-primary");
		frm.set_intro(__("Cette fiche sert au paramétrage. Candidats, notes, délibération et admissions se gèrent depuis la page « Gestion des concours »."), "blue");
	},
});
