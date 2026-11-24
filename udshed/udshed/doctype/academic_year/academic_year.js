// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

// Création d'une année académique : après le premier enregistrement,
// l'assistant propose de reprendre les grilles d'enseignement de l'année
// précédente pour les classes cochées (au lieu de tout réimporter).

frappe.ui.form.on("Academic Year", {
	before_save(frm) {
		frm.__udshed_nouvelle = frm.is_new();
	},

	after_save(frm) {
		if (frm.__udshed_nouvelle) {
			frm.__udshed_nouvelle = false;
			udshed_reprise_grilles(frm);
		}
	},

	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Reprendre des grilles d'une année précédente"), () => udshed_reprise_grilles(frm));
	},
});

function udshed_reprise_grilles(frm, annee_source) {
	const esc = (v) => frappe.utils.escape_html(v === null || v === undefined ? "" : String(v));
	frappe.call({
		method: "udshed.api.annee_academique.apercu_grilles",
		args: { annee_cible: frm.doc.name, annee_source: annee_source || null },
		freeze: true,
		freeze_message: __("Recherche des grilles existantes..."),
		callback: (r) => {
			const data = r.message || { classes: [] };
			const d = new frappe.ui.Dialog({
				title: __("Reprendre les grilles d'enseignement"),
				size: "extra-large",
				fields: [
					{
						fieldtype: "HTML",
						options: `<div class="text-muted small">${__("Cochez les classes dont la grille doit être reprise dans {0}. Les classes non cochées pourront être importées ou saisies plus tard. Une classe déjà présente n'est jamais dupliquée.", [esc(frm.doc.name)])}</div>`,
					},
					{
						fieldtype: "Link", fieldname: "annee_source", label: __("Année source"), options: "Academic Year",
						default: data.annee_source,
						get_query: () => ({ filters: { name: ["!=", frm.doc.name] } }),
						change() {
							const v = this.get_value();
							if (v && v !== data.annee_source) {
								d.hide();
								udshed_reprise_grilles(frm, v);
							}
						},
					},
					{ fieldtype: "Column Break" },
					{ fieldtype: "Check", fieldname: "copier_enseignants", label: __("Reprendre les enseignants"), default: 1 },
					{ fieldtype: "Check", fieldname: "copier_liaisons", label: __("Reprendre les liaisons de cours communs"), default: 1 },
					{ fieldtype: "Section Break" },
					{ fieldtype: "HTML", fieldname: "classes" },
				],
				primary_action_label: __("Reprendre les grilles cochées"),
				primary_action(values) {
					const classes = [];
					d.$wrapper.find(".udshed-classe:checked").each(function () {
						classes.push({ filiere: $(this).data("filiere"), niveau: $(this).data("niveau") });
					});
					if (!classes.length) {
						frappe.msgprint(__("Cochez au moins une classe."));
						return;
					}
					frappe.call({
						method: "udshed.api.annee_academique.dupliquer_grilles",
						type: "POST",
						args: {
							annee_cible: frm.doc.name,
							annee_source: values.annee_source,
							classes,
							copier_enseignants: values.copier_enseignants ? 1 : 0,
							copier_liaisons: values.copier_liaisons ? 1 : 0,
						},
						freeze: true,
						freeze_message: __("Reprise des grilles en cours..."),
						callback: (res) => {
							const s = res.message || {};
							d.hide();
							frappe.msgprint({
								title: __("Grilles reprises"),
								indicator: "green",
								message: __("Cours créés : {0}<br>Cours rattachés à des classes supplémentaires : {1}<br>UE créées : {2}<br>Liaisons de cours communs : {3}<br>Classes déjà présentes (ignorées) : {4}",
									[s.cours_crees, s.cours_rattaches, s.ue_creees, s.liaisons, s.classes_deja_presentes]),
							});
						},
					});
				},
			});

			const zone = d.fields_dict.classes.$wrapper;
			if (!data.annee_source || !data.classes.length) {
				zone.html(`<div class="alert alert-warning">${__("Aucune grille trouvée dans l'année source. Choisissez une autre année source, ou importez les grilles depuis la page « Grilles d'enseignements ».")}</div>`);
			} else {
				const lignes = data.classes.map((c) => {
					const semestres = Object.entries(c.semestres).map(([s, n]) => `${esc(s)} : ${n}`).join(" · ");
					const deja = c.deja_presents
						? `<span class="indicator-pill orange">${__("{0} cours déjà présents", [c.deja_presents])}</span>`
						: "";
					return `<tr>
						<td><input type="checkbox" class="udshed-classe" data-filiere="${esc(c.filiere)}" data-niveau="${esc(c.niveau)}" ${c.deja_presents ? "" : "checked"}></td>
						<td>${esc(c.faculte)}</td><td><strong>${esc(c.filiere_label)}</strong></td><td>${esc(c.niveau_label)}</td>
						<td>${c.cours} ${__("cours")} · ${frappe.format(c.credits, { fieldtype: "Float" })} ${__("crédits")}<br><small class="text-muted">${semestres}</small></td>
						<td>${deja}</td></tr>`;
				}).join("");
				zone.html(`
					<div class="mb-2"><a href="#" class="udshed-tout">${__("Tout cocher")}</a> · <a href="#" class="udshed-rien">${__("Tout décocher")}</a></div>
					<div style="max-height:420px;overflow:auto"><table class="table table-sm table-bordered">
						<thead><tr><th></th><th>${__("Faculté")}</th><th>${__("Filière")}</th><th>${__("Niveau")}</th><th>${__("Grille")}</th><th></th></tr></thead>
						<tbody>${lignes}</tbody></table></div>`);
				zone.find(".udshed-tout").on("click", (e) => { e.preventDefault(); zone.find(".udshed-classe").prop("checked", true); });
				zone.find(".udshed-rien").on("click", (e) => { e.preventDefault(); zone.find(".udshed-classe").prop("checked", false); });
			}
			d.show();
		},
	});
}
