// Vue calendrier du calendrier académique : un jalon s'étend de son début à sa fin.
frappe.views.calendar["Jalon Academique"] = {
	field_map: {
		start: "date_debut",
		end: "date_fin",
		id: "name",
		title: "libelle",
	},
	gantt: true,
	get_events_method: "frappe.desk.calendar.get_events",
};
