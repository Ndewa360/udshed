frappe.ready(function() {

	// ---- CSS : visibilité de tous les champs (haut du formulaire + table enfant) ----
	$('<style>').text(`

		/* === Sélecteurs : texte et fond noirs sur blanc === */
		.web-form-container select.form-control,
		.web-form-container .grid-row select.form-control,
		.web-form-container .form-in-grid select.form-control,
		.web-form-container [data-fieldtype="Table"] select.form-control {
			color: #000 !important;
			background-color: #fff !important;
			color-scheme: light !important;
			opacity: 1 !important;
		}

		/* Options déroulantes (liste ouverte) */
		.web-form-container select.form-control option,
		.web-form-container .grid-row select.form-control option,
		.web-form-container .form-in-grid select.form-control option {
			color: #000 !important;
			background-color: #fff !important;
		}

		/* === Champs Link (autocomplete) : input + dropdown awesomplete === */
		.web-form-container input.form-control,
		.web-form-container .grid-row input.form-control,
		.web-form-container .form-in-grid input.form-control {
			color: #000 !important;
			background-color: #fff !important;
			opacity: 1 !important;
		}

		/* Liste déroulante awesomplete (suggestions Link) */
		.web-form-container .awesomplete > ul,
		.web-form-container .grid-row .awesomplete > ul,
		.web-form-container .form-in-grid .awesomplete > ul {
			background-color: #fff !important;
			color: #000 !important;
			border: 1px solid #ccc !important;
			z-index: 10000 !important;
		}

		.web-form-container .awesomplete > ul > li,
		.web-form-container .grid-row .awesomplete > ul > li,
		.web-form-container .form-in-grid .awesomplete > ul > li {
			color: #000 !important;
			padding: 8px 12px !important;
		}

		.web-form-container .awesomplete > ul > li:hover,
		.web-form-container .grid-row .awesomplete > ul > li:hover,
		.web-form-container .form-in-grid .awesomplete > ul > li:hover,
		.web-form-container .awesomplete > ul > li[aria-selected="true"] {
			background-color: #e8e8e8 !important;
			color: #000 !important;
		}

		/* Texte surligné dans les suggestions */
		.web-form-container .awesomplete mark,
		.web-form-container .grid-row .awesomplete mark {
			background-color: #ffe066 !important;
			color: #000 !important;
		}

		/* === Table enfant (grid) : texte statique + lignes === */
		.web-form-container .grid-row .static-area {
			color: #000 !important;
			background-color: #fff !important;
		}

		.web-form-container .grid-row .editable-row .form-control {
			color: #000 !important;
			background-color: #fff !important;
		}

		/* Label et header du grid */
		.web-form-container .grid-field label,
		.web-form-container .grid-heading-row {
			color: #333 !important;
		}
	`).appendTo('head');

	// ---- Délégation dynamique : couvre les champs ajoutés après chargement ----

	// Sélects (présent + futur)
	$(document).on('focus change', '.web-form-container select.form-control', function() {
		$(this).css({ color: '#000', 'background-color': '#fff', 'color-scheme': 'light', opacity: 1 });
	});

	// Champs Link / autocomplete (input + sélection)
	$(document).on('focus change input', '.web-form-container input.form-control', function() {
		$(this).css({ color: '#000', 'background-color': '#fff', opacity: 1 });
	});

	// Quand une suggestion awesomplete est sélectionnée
	$(document).on('click', '.web-form-container .awesomplete > ul > li', function() {
		var $input = $(this).closest('.awesomplete').find('input');
		$input.css({ color: '#000', 'background-color': '#fff' });
	});

	// ---- Redirection après soumission ----
	frappe.web_form.after_save = function() {
		window.location.href = '/candidature-success';
	};
})