// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.query_reports["Liste Etudiants A Rattraper"] = {
	// Intitulé et explication : la liste sert à convoquer chaque étudiant au rattrapage des matières
	// qu'il n'a pas validées en session normale.
	onload(report) {
		report.page.set_title(__("Admis au rattrapage (par matière)"));
		$(`<div class="text-muted" style="margin: 4px 0 12px; font-size: 14px">${__(
			"Étudiants qui doivent passer la session de rattrapage, matière par matière (matières non validées en session normale). Choisissez la classe, le semestre et la matière."
		)}</div>`).prependTo(report.page.main);
	},
	filters: [
		{
			fieldname: "academic_year",
			label: __("Année académique"),
			fieldtype: "Link",
			options: "Academic Year",
			reqd: 1,
			// Année de la session (non modifiable).
			default: (window.Udshed && Udshed.Session && Udshed.Session.annee()) || frappe.defaults.get_user_default("academic_year"),
			read_only: (window.Udshed && Udshed.Session && Udshed.Session.annee()) ? 1 : 0,
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
