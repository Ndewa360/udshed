// Délibération du jury : simulation (sans effet), application, annulation.
frappe.ui.form.on("Deliberation Jury", {
	setup(frm) {
		frm.set_query("niveau", () => ({
			filters: frm.doc.filiere ? { parent: frm.doc.filiere, parenttype: "Field of study" } : {},
		}));
	},

	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Simuler"), () => simuler(frm));
		if (frm.doc.statut !== "Appliquée") {
			frm.add_custom_button(__("Appliquer la délibération"), () => {
				frappe.confirm(
					__("Appliquer la délibération ? Les unités et la progression des étudiants de la classe seront recalculées."),
					() => frm.call("appliquer").then((r) => {
						frappe.msgprint((r.message || {}).bilan || __("Délibération appliquée."));
						frm.reload_doc();
					})
				);
			}).addClass("btn-primary");
		} else {
			frm.add_custom_button(__("Annuler l'application"), () => {
				frappe.confirm(__("Annuler l'application ? Les validations accordées par le jury seront retirées."), () =>
					frm.call("annuler_application").then(() => frm.reload_doc())
				);
			});
			frm.dashboard.set_headline(__("Délibération appliquée le {0}.", [frappe.datetime.str_to_user(frm.doc.appliquee_le)]));
		}
	},
});

function simuler(frm) {
	const esc = (v) => frappe.utils.escape_html(v === null || v === undefined ? "" : String(v));
	frm.call("simuler").then((r) => {
		const res = r.message || {};
		const lignes = (res.etudiants || []).map((e) => {
			const unites = (e.unites_repechees || [])
				.map((u) => `${esc(u.intitule)} (${esc(u.note_20)}/20) — ${esc(u.motif)}`).join("<br>");
			return `<tr><td>${esc(e.nom)}</td><td>${unites || "<span class='text-muted'>—</span>"}</td>
				<td><b>${esc(e.decision)}</b><br><small class="text-muted">${esc(e.motif)}</small></td><td>${esc(e.credits)}</td></tr>`;
		}).join("");
		frappe.msgprint({
			title: __("Simulation de la délibération"),
			wide: true,
			message: `<p class="text-muted">${__("Aperçu sans effet. Passage vers : {0}", [esc(res.niveau_suivant || "—")])}</p>
				<div class="table-responsive"><table class="table table-bordered table-sm">
				<thead><tr><th>${__("Étudiant")}</th><th>${__("Unités validées par le jury")}</th>
				<th>${__("Décision de passage")}</th><th>${__("Crédits")}</th></tr></thead>
				<tbody>${lignes || `<tr><td colspan="4">${__("Aucun étudiant inscrit dans cette classe.")}</td></tr>`}</tbody></table></div>`,
		});
	});
}
