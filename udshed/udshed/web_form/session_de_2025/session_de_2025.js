frappe.ready(function() {
	// Fix sélection des menus déroulants (select/autocomplete)
	setTimeout(() => {
		$('.web-form-container select.form-control').each(function() {
			$(this).on('change', function() {
				$(this).css({ color: '#000', 'background-color': '#fff' });
			});
		});
		$('.web-form-container .frappe-control[data-fieldtype="Link"] input').each(function() {
			$(this).on('change', function() {
				$(this).css('color', '#000');
			});
		});
	}, 500);

	// Rediriger vers la page de succès après soumission
	frappe.web_form.after_save = function() {
		window.location.href = '/candidature-success';
	};
})