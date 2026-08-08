// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

const SEUILS_DEFAUT = { Licence: 50, BTS: 50, Master: 60 };

frappe.ui.form.on("Grade Formula", {
	refresh: function (frm) {
		frm.trigger("render_apercu");
	},
	cycle: function (frm) {
		frm.trigger("set_seuil_defaut");
		frm.trigger("render_apercu");
	},
	components_add: function (frm) {
		frm.trigger("render_apercu");
	},
	composition_add: function (frm) {
		frm.trigger("render_apercu");
	},
	set_seuil_defaut: function (frm) {
		if (!frm.doc.seuil_validation && SEUILS_DEFAUT[frm.doc.cycle] !== undefined) {
			frm.set_value("seuil_validation", SEUILS_DEFAUT[frm.doc.cycle]);
		}
	},
	render_apercu: function (frm) {
		const composants = (frm.doc.components || []).filter((c) => c.pourcentage);
		const lignes = [];

		if (composants.length) {
			const parties = composants.map(
				(c) => `${c.composante} (${c.pourcentage}%)`
			);
			lignes.push(`Note du cours = ${parties.join(" + ")}`);
		} else {
			lignes.push("Note du cours = (aucune composante configurée)");
		}

		const parParent = {};
		(frm.doc.composition || []).forEach((r) => {
			if (!parParent[r.composante_parent]) parParent[r.composante_parent] = [];
			parParent[r.composante_parent].push(r);
		});

		composants.forEach((c) => {
			const rows = parParent[c.composante] || [];
			if (!rows.length) return;
			const internes = rows.map(
				(r) => `${r.composante} (${r.pourcentage}%)`
			);
			lignes.push(`${c.composante} = ${internes.join(" + ")}`);
		});

		const total = (frm.doc.components || []).reduce(
			(acc, c) => acc + (c.pourcentage || 0),
			0
		);
		if (total !== 100) {
			lignes.push("");
			lignes.push(`Total actuel : ${total}% — doit être égal à 100%`);
		}

		frm.set_value("apercu", lignes.join("\n"));
	},
});

frappe.ui.form.on("Grade Formula Component", {
	composante: (frm) => frm.trigger("render_apercu"),
	pourcentage: (frm) => frm.trigger("render_apercu"),
	form_render: (frm) => frm.trigger("render_apercu"),
	grid_remove: (frm) => frm.trigger("render_apercu"),
});

frappe.ui.form.on("Grade Formula Composition", {
	composante_parent: (frm) => frm.trigger("render_apercu"),
	composante: (frm) => frm.trigger("render_apercu"),
	pourcentage: (frm) => frm.trigger("render_apercu"),
	form_render: (frm) => frm.trigger("render_apercu"),
	grid_remove: (frm) => frm.trigger("render_apercu"),
});
