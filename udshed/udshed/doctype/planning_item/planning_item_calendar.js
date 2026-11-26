// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

// Vue calendrier des séances (le planning de travail reste la page « Planning »).
frappe.views.calendar["Planning Item"] = {
	field_map: { start: "date", end: "date", id: "name", title: "cours", allDay: "allDay" },
	filters: [{ fieldtype: "Link", fieldname: "academic_year", options: "Academic Year", label: __("Année académique") }],
};
