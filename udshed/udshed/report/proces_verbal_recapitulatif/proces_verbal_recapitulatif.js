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

		// Mise en évidence du % de validation : vert si >= seuil (50%), sinon rouge
		if (column.fieldname === "pct_validation") {
			if (data.pct_validation != null) {
				if (data.pct_validation >= 50) {
					return `<span class="indicator green">${value}</span>`;
				}
				return `<span class="indicator red">${value}</span>`;
			}
		}

		// Grade non validé (statut "Non Validé") en rouge dans les colonnes UE
		if (column.fieldname.startsWith("ue_")) {
			if (data[column.fieldname + "_non_valide"]) {
				return `<span class="indicator red">${value}</span>`;
			}
		}

		return value;
	}
};
