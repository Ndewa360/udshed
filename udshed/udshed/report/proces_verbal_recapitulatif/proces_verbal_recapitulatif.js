// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.query_reports["Proces Verbal Recapitulatif"] = {
	"filters": [
		{
			"fieldname": "academic_year",
			"label": __("Année Académique"),
			"fieldtype": "Link",
			"options": "Academic Year",
			"reqd": 1
		},
		{
			"fieldname": "semestre",
			"label": __("Semestre"),
			"fieldtype": "Select",
			"options": ["Semestre 1", "Semestre 2"],
			"reqd": 1
		},
		{
			"fieldname": "filiere",
			"label": __("Filière"),
			"fieldtype": "Link",
			"options": "Field of study",
			"reqd": 1
		},
		{
			"fieldname": "niveau",
			"label": __("Niveau / Classe"),
			"fieldtype": "Select",
			"options": [
				"Licence 1",
				"Licence 2",
				"Licence 3",
				"BTS 1",
				"BTS 2",
				"Master 1",
				"Master 2"
			],
			"reqd": 1
		}
	],

	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (!data || !column.fieldname) {
			return value;
		}

		// Statut de délibération (session normale)
		if (column.fieldname === "statut") {
			const cls =
				data.statut === "Admis" ? "green"
				: data.statut === "Ajourné" ? "red"
				: "orange";
			return `<span class="indicator ${cls}">${value}</span>`;
		}

		// % de validation : vert si >= seuil (50%), sinon rouge
		if (column.fieldname === "pct_validation") {
			if (data.pct_validation != null) {
				const cls = data.pct_validation >= 50 ? "green" : "red";
				return `<span class="indicator ${cls}">${value}</span>`;
			}
		}

		// Colonnes UE : note validée en vert, non validée en rouge
		if (column.fieldname.startsWith("ue_")) {
			const base = column.fieldname
				.replace(/_note$/, "")
				.replace(/_grade$/, "")
				.replace(/_point$/, "");
			if (data[base + "_non_valide"]) {
				return `<span class="indicator red">${value}</span>`;
			}
			if (column.fieldname.endsWith("_note") && data[column.fieldname] != null) {
				return `<span class="indicator green">${value}</span>`;
			}
		}

		return value;
	},

	"onload": function (report) {
		report.page.add_inner_button(__("Télécharger le PV (PDF)"), () => {
			const filters = report.get_filter_values();
			if (!filters.academic_year || !filters.filiere || !filters.niveau) {
				frappe.msgprint(
					__("Sélectionnez l'année académique, la filière et le niveau.")
				);
				return;
			}
			const p = new URLSearchParams({
				academic_year: filters.academic_year,
				filiere: filters.filiere,
				niveau: filters.niveau,
				semestre: filters.semestre,
			});
			const a = document.createElement("a");
			a.href =
				"/api/method/udshed.api.proces_verbal.download_proces_verbal_pdf?" +
				p.toString();
			a.style.display = "none";
			document.body.appendChild(a);
			a.click();
			a.remove();
		});
	},

	"after_datatable_render": function (report) {
		const data = report.data || [];
		if (!data.length) {
			return;
		}

		let admis = 0;
		const ueStats = {};
		data.forEach((row) => {
			if (row.statut === "Admis") admis++;
			Object.keys(row).forEach((k) => {
				const m = k.match(/^ue_(.+)_note$/);
				if (!m) return;
				const base = "ue_" + m[1];
				if (row[base + "_point"] == null) return;
				if (!ueStats[base]) {
					ueStats[base] = { present: 0, valide: 0 };
				}
				ueStats[base].present++;
				if (row[base + "_non_valide"] === 0) {
					ueStats[base].valide++;
				}
			});
		});

		const total = data.length;
		let bar = `<div class="pv-stats" style="display:flex;flex-wrap:wrap;gap:6px 18px;align-items:center;background:#f7f9fc;border:1px solid #e2e6f0;border-radius:6px;padding:8px 14px;margin:10px 0;font-size:12px;">`;
		bar += `<span><strong>${total}</strong> ${__("étudiants")}</span>`;
		bar += `<span>${__("Admis")} : <strong>${admis}</strong></span>`;
		bar += `<span>${__("Taux de réussite global")} : <strong>${total ? (100 * admis / total).toFixed(1) : "0.0"}%</strong></span>`;
		Object.keys(ueStats).forEach((base) => {
			const s = ueStats[base];
			const taux = s.present ? (100 * s.valide / s.present).toFixed(0) : "0";
			bar += `<span style="color:#1a5276;"><strong>${base.replace("ue_", "")}</strong> : ${taux}% (${s.valide}/${s.present})</span>`;
		});
		bar += `</div>`;

		const wrapper =
			(report.datatable && report.datatable.wrapper) ||
			report.page.main.find(".datatable");
		if (wrapper) {
			$(wrapper).before(bar);
		}
	}
};
