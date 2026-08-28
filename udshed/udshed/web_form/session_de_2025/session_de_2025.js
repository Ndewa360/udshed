frappe.ready(function() {
	// ---- Redirection après soumission ----
	frappe.web_form.after_save = function() {
		window.location.href = '/candidature-success';
	};
})