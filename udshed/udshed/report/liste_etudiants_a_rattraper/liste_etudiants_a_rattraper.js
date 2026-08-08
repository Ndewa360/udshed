// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.query_reports["Liste Etudiants A Rattraper"] = {
	filters: [
		{
			fieldname: "academic_year",
			label: __("Année académique"),
			fieldtype: "Link",
			options: "Academic Year",
			reqd: 1,
		},
		{
			fieldname: "semestre",
			label: __("Semestre"),
			fieldtype: "Select",
			options: "Semestre 1\nSemestre 2",
			reqd: 1,
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
			label: __("Niveau"),
			fieldtype: "Link",
			options: "Field of study Level",
			reqd: 1,
		},
	],
};
