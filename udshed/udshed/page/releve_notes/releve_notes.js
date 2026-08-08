frappe.pages['releve_notes'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Relevé de notes'),
		single_column: true
	});

	var state = { student: null };

	var body = $('<div style="max-width:920px;margin:0 auto;padding:8px 16px 40px;"></div>');
	$(page.body).append(body);

	body.append(`
		<div class="card" style="margin-top:14px;">
			<div class="card-body">
				<div class="d-flex align-items-start mb-3">
					<div class="mr-3" style="font-size:26px;color:#1a5276;"><i class="fa-solid fa-file-lines"></i></div>
					<div>
						<h5 class="mb-1">${__('Relevé de notes')}</h5>
						<p class="text-muted small mb-0">${__('Sélectionnez un étudiant puis générez son relevé de notes (PDF).')}</p>
					</div>
				</div>
				<div class="row align-items-end">
					<div class="col-md-7" id="rn-student-field"></div>
					<div class="col-md-5 d-flex justify-content-end">
						<button class="btn btn-primary btn-sm rn-print" disabled>
							<i class="fa-solid fa-print mr-1"></i>${__('Imprimer le relevé')}
						</button>
					</div>
				</div>
				<div class="rn-info mt-3"></div>
			</div>
		</div>
	`);

	var f_student = frappe.ui.form.make_control({
		df: {
			fieldname: 'student',
			fieldtype: 'Link',
			label: __('Étudiant'),
			options: 'Student',
			reqd: 1,
			placeholder: __('Rechercher par matricule, nom ou prénom'),
			get_query: function () {
				return { query: 'udshed.api.releve_notes.search_students' };
			},
			change: function () {
				state.student = this.get_value() || null;
				body.find('.rn-print').prop('disabled', !state.student);
				render_info();
			}
		},
		parent: body.find('#rn-student-field')
	});
	f_student.refresh();

	function render_info() {
		var slot = body.find('.rn-info');
		slot.empty();
		if (!state.student) return;

		frappe.db.get_value('Student', state.student, ['name', 'matricule', 'nom', 'prenom', 'filiere', 'niveau_actuel']).then(function (r) {
			var d = r.message || {};
			var filiere = d.filiere || '';

			function fill(filiere_label) {
				slot.html(`
					<div class="table-responsive">
						<table class="table table-bordered table-sm mb-0">
							<tbody>
								<tr>
									<th class="w-25">${__('Matricule')}</th>
									<td>${frappe.utils.escape_html(d.matricule || '')}</td>
									<th class="w-25">${__('Nom & prénom')}</th>
									<td>${frappe.utils.escape_html((d.nom || '') + ' ' + (d.prenom || ''))}</td>
								</tr>
								<tr>
									<th>${__('Filière')}</th>
									<td>${frappe.utils.escape_html(filiere_label)}</td>
									<th>${__('Niveau')}</th>
									<td>${frappe.utils.escape_html(d.niveau_actuel || '')}</td>
								</tr>
							</tbody>
						</table>
					</div>`);
			}

			if (filiere) {
				frappe.db.get_value('Field of study', filiere, 'name_of_field').then(function (res) {
					var label = (res.message && res.message.name_of_field) || filiere;
					fill(label);
				});
			} else {
				fill('');
			}
		});
	}

	body.on('click', '.rn-print', function () {
		if (!state.student) return;
		var url = '/printview?doctype=Student&name=' + encodeURIComponent(state.student) + '&format=' + encodeURIComponent('Releve Notes');
		window.open(frappe.urllib.get_full_url(url), '_blank');
	});
};
