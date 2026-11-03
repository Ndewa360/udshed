// L'assistant est partagé avec la page du portail /reinscription-etudiant
// (public/js/reinscription_wizard.js).
frappe.pages['reinscription_etudiant'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Réinscription Étudiant',
		single_column: true
	});

	frappe.require([
		'/assets/udshed/css/reinscription_wizard.css',
		'/assets/udshed/js/reinscription_wizard.js'
	], function() {
		window.udshed_reinscription({
			main: page.main,
			clear: function() {
				page.clear_actions();
				page.clear_fields();
			},
			desk: true
		});
	});
};
