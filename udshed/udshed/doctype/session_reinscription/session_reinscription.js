// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

const ROLES_PROGRESSION = ["System Manager", "Coordonateur", "Agent de scolarité", "Registration Manager"];

frappe.ui.form.on("Session Reinscription", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.academic_year) return;
		if (!ROLES_PROGRESSION.some((r) => frappe.user.has_role(r))) return;

		// Progressions des résultats de l'année précédant la session
		frm.add_custom_button(__("Calculer les progressions"), () => {
			frappe.call({
				method: "udshed.api.reregistration.annee_precedente",
				args: { academic_year: frm.doc.academic_year },
			}).then((r) => {
				const annee = r.message;
				if (!annee) {
					frappe.msgprint(__("Année académique précédente introuvable."));
					return;
				}
				frappe.confirm(
					__("Calculer la progression des étudiants à partir des résultats {0} officiellement publiés ?", [annee]),
					() => {
						frappe.call({
							method: "udshed.api.progression.recalculer_progressions",
							args: { academic_year: annee },
							freeze: true,
						}).then((res) => {
							const b = res.message || {};
							const lignes = Object.entries(b.par_statut || {})
								.map(([statut, n]) => `<li>${frappe.utils.escape_html(statut)} : ${n}</li>`)
								.join("");
							frappe.msgprint({
								title: __("Progressions {0}", [annee]),
								message: `<ul>${lignes || "<li>Aucun étudiant</li>"}</ul>` +
									((b.echecs || []).length ? `<p>${b.echecs.length} échec(s) : voir le journal des erreurs.</p>` : ""),
							});
						});
					}
				);
			});
		});

		frm.add_custom_button(__("Voir les progressions"), () => {
			frappe.call({
				method: "udshed.api.reregistration.annee_precedente",
				args: { academic_year: frm.doc.academic_year },
			}).then((r) => frappe.set_route("List", "Progression Academique", { annee_source: r.message }));
		});
	},

	validate(frm) {
		if (frm.doc.date_ouverture && frm.doc.date_cloture) {
			if (frm.doc.date_ouverture >= frm.doc.date_cloture) {
				frappe.msgprint("La date d'ouverture doit être antérieure à la date de clôture");
				frappe.validated = false;
			}
		}
	}
});
