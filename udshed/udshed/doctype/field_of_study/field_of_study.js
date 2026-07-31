frappe.ui.form.on("Field of study", {
	before_save: function (frm) {
		if (frm.doc.field_of_study_level.length == 0) {
			frappe.show_alert({ message:__('Niveaux d\'études manquants.'), indicator:'red' });
			frappe.throw(null);
		}
	},
});

frappe.ui.form.on("Field of study Level", {
	field_of_study_level_add: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		let max_order = 0;
		$.each(frm.doc.field_of_study_level, function (_i, r) {
			if (r.name !== row.name && (r.order || 0) > max_order) {
				max_order = r.order || 0;
			}
		});
		row.order = max_order + 1;
		frm.refresh_field("field_of_study_level");
	},

	order: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (!row.order || row.order < 1) {
			row.order = 1;
			frm.refresh_field("field_of_study_level");
		}
	},
});
