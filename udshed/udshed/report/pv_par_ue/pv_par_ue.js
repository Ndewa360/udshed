// Copyright (c) 2026, Udshed and contributors
// For license information, please see license.txt

frappe.query_reports["PV par UE"] = {
	filters: [
		{
			fieldname: "academic_year",
			label: __("Année Académique"),
			fieldtype: "Link",
			options: "Academic Year",
			reqd: 1,
		},
		{
			fieldname: "semestre",
			label: __("Semestre"),
			fieldtype: "Select",
			options: ["Semestre 1", "Semestre 2"],
			reqd: 1,
			default: "Semestre 1",
		},
		{
			fieldname: "filiere",
			label: __("Filière"),
			fieldtype: "Link",
			options: "Field of study",
			reqd: 1,
		},
		{
			fieldname: "niveau",
			label: __("Niveau / Classe"),
			fieldtype: "Select",
			options: [
				"Licence 1",
				"Licence 2",
				"Licence 3",
				"BTS 1",
				"BTS 2",
				"Master 1",
				"Master 2",
			],
			reqd: 1,
		},
		{
			fieldname: "teaching_unit_value",
			label: __("UE"),
			fieldtype: "Link",
			options: "Teaching Unit Value",
			reqd: 1,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data || !column.fieldname) {
			return value;
		}

		// Statut de l'UE
		if (column.fieldname === "statut") {
			const cls =
				data.statut === "Validé"
					? "green"
					: data.statut === "Non Validé"
					? "red"
					: "orange";
			return `<span class="indicator ${cls}">${value}</span>`;
		}

		// Note UE : verte au-dessus du seuil, rouge en dessous
		if (column.fieldname === "note_ue_pct") {
			if (data.note_ue_pct != null) {
				const seuil = data.seuil_validation;
				const cls = seuil && data.note_ue_pct < seuil ? "red" : "green";
				return `<span class="indicator ${cls}">${value}</span>`;
			}
			return `<span class="text-muted">—</span>`;
		}

		// Colonnes matière : rouge si la matière n'est pas validée
		if (column.fieldname.startsWith("mat_")) {
			if (value == null || value === "") {
				return `<span class="text-muted">—</span>`;
			}
			return value;
		}

		return value;
	},

	onload(report) {
		// Le filtre UE reste un `Link` simple : `QueryReport` écrase le
		// `df.onchange` de chaque filtre à la construction et n'expose pas
		// `get_field()`. Restreindre ses options dynamiquement casserait le
		// `onload` tout entier. Le périmètre est donc validé côté serveur
		// (`execute`), qui renvoie un message explicite si l'UE n'a aucune
		// matière dans la classe choisie.
		report.page.add_inner_button(__("Télécharger le PV de l'UE (PDF)"), () => {
			const f = report.get_filter_values();
			if (!f.teaching_unit_value) {
				frappe.msgprint(__("Sélectionnez une UE."));
				return;
			}
			const p = new URLSearchParams({
				academic_year: f.academic_year,
				filiere: f.filiere,
				niveau: f.niveau,
				semestre: f.semestre,
				teaching_unit_value: f.teaching_unit_value,
			});
			const a = document.createElement("a");
			a.href = "/api/method/udshed.api.proces_verbal.download_pv_ue_pdf?" + p.toString();
			a.style.display = "none";
			document.body.appendChild(a);
			a.click();
			a.remove();
		});

		report.page.add_inner_button(__("Recalculer l'UE"), () => {
			const f = report.get_filter_values();
			if (!f.teaching_unit_value) {
				frappe.msgprint(__("Sélectionnez une UE."));
				return;
			}
			frappe.call({
				method: "udshed.api.resultat_ue.recalculer_ue",
				args: {
					academic_year: f.academic_year,
					filiere: f.filiere,
					niveau: f.niveau,
					semestre: f.semestre,
					teaching_unit_value: f.teaching_unit_value,
				},
				callback(r) {
					const m = r.message || {};
					frappe.msgprint(
						__("Résultats recalculés pour {0} étudiant(s).").format(
							m.etudiants || 0
						)
					);
					report.refresh();
				},
			});
		});
	},
};
