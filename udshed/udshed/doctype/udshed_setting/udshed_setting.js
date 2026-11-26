// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

// Matricules : aperçu du prochain matricule avec les réglages saisis (avant enregistrement).
frappe.ui.form.on("Udshed Setting", {
	refresh: (frm) => apercu_matricule(frm),
	format_matricule: (frm) => apercu_matricule(frm),
	mode_lettre_matricule: (frm) => apercu_matricule(frm),
	lettre_matricule_fixe: (frm) => apercu_matricule(frm),
});

function apercu_matricule(frm) {
	const champ = frm.get_field("apercu_matricule");
	if (!champ) return;
	frappe.call({
		method: "udshed.utils.matricule.apercu",
		args: {
			format_matricule: frm.doc.format_matricule,
			mode_lettre_matricule: frm.doc.mode_lettre_matricule,
			lettre_matricule_fixe: frm.doc.lettre_matricule_fixe,
		},
		error_msg: " ",
		callback: (r) => {
			const m = r.message || {};
			champ.$wrapper.html(`<div class="text-muted small">${__("Prochain matricule")} (${frappe.utils.escape_html(m.annee || "")}) :</div>
				<div style="font-size:18px;font-weight:600;letter-spacing:1px">${frappe.utils.escape_html(m.exemple || "—")}</div>`);
		},
	}).fail(() => champ.$wrapper.html(`<div class="text-danger small">${__("Format invalide")}</div>`));
}
