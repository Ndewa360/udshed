// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

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
		frm.add_custom_button(__("Candidats au concours"), () => {
			frappe.set_route("List", "Candidat Concours", { concours: frm.doc.name });
		});
		frm.add_custom_button(__("Liste d'émargement"), () => choisir_centre_emargement(frm));
		boutons_phase3(frm);
	},
});

// ---------------------------------------------------------------- phase 3
const API3 = "udshed.api.concours_resultats.";
const GROUPE3 = __("Notes et classement");

function boutons_phase3(frm) {
	if (!["Épreuves", "Délibération", "Résultats publiés", "Clôturé"].includes(frm.doc.statut)) return;

	if (["Épreuves", "Délibération"].includes(frm.doc.statut)) {
		frm.add_custom_button(__("Saisie des notes"), () =>
			frappe.set_route("saisie-notes-concours", { concours: frm.doc.name })
		, GROUPE3);
	}
	if (frm.doc.statut === "Épreuves" && !frm.doc.anonymat_leve) {
		frm.add_custom_button(__("Lever l'anonymat"), () => {
			frappe.confirm(
				__("Lever l'anonymat ? Les notes deviennent nominatives, ne sont plus modifiables, et le concours passe en « Délibération »."),
				() => frappe.call({ method: API3 + "lever_anonymat", args: { concours: frm.doc.name }, freeze: true })
					.then(() => frm.reload_doc())
			);
		}, GROUPE3);
	}
	if (frm.doc.statut === "Délibération") {
		frm.add_custom_button(__("Calculer le classement"), () => {
			frappe.call({ method: API3 + "calculer_classement", args: { concours: frm.doc.name }, freeze: true,
				freeze_message: __("Calcul des moyennes et du classement…") })
				.then((r) => { afficher_resume_classement(r.message || []); frm.reload_doc(); });
		}, GROUPE3);
	}
	if (frm.doc.classement_calcule_le) {
		frm.add_custom_button(__("PV de classement provisoire"), () => {
			window.open("/api/method/" + API3 + "telecharger_pv_classement?" +
				new URLSearchParams({ concours: frm.doc.name }).toString());
		}, GROUPE3);
	}

	// Avancement de la saisie, en tête du formulaire.
	if (frm.doc.statut === "Épreuves") {
		frappe.call({ method: API3 + "etat_saisie", args: { concours: frm.doc.name } }).then((r) => {
			const etat = r.message || [];
			if (!etat.length) return;
			const lignes = etat.map((m) => {
				const icone = m.validee ? "✔" : m.saisies === m.total && m.total ? "●" : "○";
				return `${icone} ${frappe.utils.escape_html(m.matiere)} : ${m.saisies}/${m.total}${m.validee ? " — " + __("validée") : ""}`;
			});
			frm.set_intro(__("Saisie des notes") + " — " + lignes.join(" &nbsp;|&nbsp; "),
				etat.every((m) => m.validee) ? "green" : "blue");
		});
	}
}

function afficher_resume_classement(resume) {
	const lignes = resume.map((s) => `
		<tr><td>${frappe.utils.escape_html(s.filiere)}</td><td class="text-right">${s.places}</td>
		<td class="text-right">${s.candidats}</td><td class="text-right text-success"><b>${s.admis}</b></td>
		<td class="text-right">${s.attente}</td><td class="text-right">${s.non_admis}</td>
		<td class="text-right ${s.ex_aequo ? "text-danger" : ""}">${s.ex_aequo}</td></tr>`).join("");
	frappe.msgprint({
		title: __("Classement calculé"),
		message: `<table class="table table-bordered table-condensed">
			<thead><tr><th>${__("Filière")}</th><th>${__("Places")}</th><th>${__("Candidats")}</th>
			<th>${__("Admis")}</th><th>${__("Attente")}</th><th>${__("Non admis")}</th><th>${__("Ex æquo")}</th></tr></thead>
			<tbody>${lignes}</tbody></table>
			<p class="text-muted small">${__("Propositions provisoires : la décision finale appartient au jury (délibération).")}</p>`,
		wide: true,
	});
}

function choisir_centre_emargement(frm) {
	frappe.call({
		method: "udshed.api.concours.centres_du_concours",
		args: { concours: frm.doc.name },
	}).then((r) => {
		const centres = r.message || [];
		if (!centres.length) {
			frappe.msgprint(__("Aucun candidat n'est encore autorisé à concourir."));
			return;
		}
		const total = centres.reduce((s, c) => s + c.effectif, 0);
		const options = [__("Tous les centres ({0} candidats)", [total])].concat(
			centres.map((c) => `${c.centre || __("Sans centre")} (${c.effectif})`)
		);
		const d = new frappe.ui.Dialog({
			title: __("Liste d'émargement"),
			fields: [
				{
					fieldtype: "Select",
					fieldname: "choix",
					label: __("Centre"),
					options: options.join("\n"),
					default: options[0],
					reqd: 1,
				},
			],
			primary_action_label: __("Télécharger le PDF"),
			primary_action(values) {
				const idx = options.indexOf(values.choix);
				const params = new URLSearchParams({ concours: frm.doc.name });
				if (idx > 0 && centres[idx - 1].centre) params.set("centre", centres[idx - 1].centre);
				window.open("/api/method/udshed.api.concours.telecharger_liste_emargement?" + params.toString());
				d.hide();
			},
		});
		d.show();
	});
}
