frappe.pages['reinscription_etudiant'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Réinscription Étudiant',
		single_column: true
	});

	var student_matricule = null;
	var student_data = null;
	var current_step = 1;
	var selected_session = null;
	var selected_semestre = null;
	var reregistration_name = null;
	var wizard_data = {};

	// Initialize - get student and existing registrations
	frappe.call({
		method: 'udshed.api.reregistration.get_student_by_matricule',
		callback: function(r) {
			if (r.message) {
				student_data = r.message;
				student_matricule = r.message.name;
				load_existing_registrations();
			} else {
				show_no_student();
			}
		}
	});

	function show_no_student() {
		page.clear_actions();
		page.clear_fields();
		$(page.main).html('<div class="alert alert-warning" style="padding: 40px; text-align: center;">' +
			'<h4>Aucun étudiant lié</h4>' +
			'<p>Aucun étudiant n\'est lié à votre compte utilisateur.</p>' +
			'</div>');
	}

	function load_existing_registrations() {
		frappe.call({
			method: 'udshed.api.reregistration.get_student_registrations',
			args: { student: student_matricule },
			callback: function(r) {
				if (r.message) {
					render_dashboard(r.message);
				} else {
					render_dashboard([]);
				}
			}
		});
	}

	function render_dashboard(registrations) {
		page.clear_actions();
		page.clear_fields();
		$(page.main).empty();

		// Check if there's an open session for new registration
		frappe.call({
			method: 'udshed.api.reregistration.get_open_sessions',
			callback: function(r) {
				var has_open_session = r.message && r.message.length > 0;
				var latest_reg = registrations.length > 0 ? registrations[0] : null;
				var session_academic_year = has_open_session ? r.message[0].academic_year : null;
				var can_register = has_open_session && (!latest_reg || latest_reg.academic_year !== session_academic_year);

				var html = '';

				// Main action button
				if (can_register) {
					html += '<div style="margin-bottom: 24px; text-align: center;">';
					html += '<button class="btn btn-primary btn-lg" id="btn-new-reregistration" style="min-width: 280px; padding: 14px 32px; font-size: 15px;">';
					html += '<i class="fa fa-plus" style="margin-right: 8px;"></i> Nouveau : Se réinscrire';
					html += '</button>';
					html += '</div>';
				}

				// Existing registrations list
				html += '<div class="card" style="border: 1px solid var(--border-color); border-radius: var(--radius-lg); overflow: hidden;">';
				html += '<div class="card-header" style="padding: 16px 24px; border-bottom: 1px solid var(--border-color); background: var(--bg-table-header);">';
				html += '<h3 style="margin: 0; font-size: 16px; font-weight: 600;">Mes fiches de réinscription</h3>';
				html += '</div>';
				html += '<div style="padding: 0;">';

				if (registrations.length === 0) {
					html += '<div style="padding: 40px; text-align: center; color: var(--text-muted);">';
					html += '<i class="fa fa-file-text-o" style="font-size: 32px; margin-bottom: 12px; display: block; color: var(--text-light);"></i>';
					html += 'Aucune réinscription trouvée.';
					html += '</div>';
				} else {
					html += '<table style="width: 100%; border-collapse: collapse;">';
					html += '<thead><tr style="background: var(--bg-table-header);">';
					html += '<th style="padding: 12px 16px; text-align: left; font-weight: 600; font-size: 12px; color: var(--text-secondary); border-bottom: 1px solid var(--border-color); width: 40px;">#</th>';
					html += '<th style="padding: 12px 16px; text-align: left; font-weight: 600; font-size: 12px; color: var(--text-secondary); border-bottom: 1px solid var(--border-color);">Année académique</th>';
					html += '<th style="padding: 12px 16px; text-align: left; font-weight: 600; font-size: 12px; color: var(--text-secondary); border-bottom: 1px solid var(--border-color);">Niveau</th>';
					html += '<th style="padding: 12px 16px; text-align: left; font-weight: 600; font-size: 12px; color: var(--text-secondary); border-bottom: 1px solid var(--border-color);">Session</th>';
					html += '<th style="padding: 12px 16px; text-align: left; font-weight: 600; font-size: 12px; color: var(--text-secondary); border-bottom: 1px solid var(--border-color);">Statut</th>';
					html += '<th style="padding: 12px 16px; text-align: left; font-weight: 600; font-size: 12px; color: var(--text-secondary); border-bottom: 1px solid var(--border-color); width: 180px;">Actions</th>';
					html += '</tr></thead>';
					html += '<tbody>';

					registrations.forEach(function(reg, index) {
						var statut_class = reg.statut === 'Validée' ? 'badge-success' : (reg.statut === 'Soumise' ? 'badge-warning' : 'badge-soft');
						html += '<tr style="border-bottom: 1px solid var(--separator);">';
						html += '<td style="padding: 14px 16px; font-size: 14px; color: var(--text-primary);">' + (index + 1) + '</td>';
						html += '<td style="padding: 14px 16px; font-size: 14px; color: var(--text-primary); font-weight: 500;">' + (reg.academic_year || '—') + '</td>';
						html += '<td style="padding: 14px 16px; font-size: 14px; color: var(--text-primary);">' + (reg.niveau || '—') + '</td>';
						html += '<td style="padding: 14px 16px; font-size: 14px; color: var(--text-secondary);">' + (reg.reinscription_session || '—') + '</td>';
						html += '<td style="padding: 14px 16px;"><span class="badge ' + statut_class + '" style="padding: 4px 12px; font-size: 11px; font-weight: 600; border-radius: var(--radius-full);">' + (reg.statut || '—') + '</span></td>';
						html += '<td style="padding: 14px 16px;">';
						html += '<button class="btn btn-secondary btn-sm btn-view-fiche" data-name="' + reg.name + '" style="padding: 6px 14px; font-size: 12px;">';
						html += '<i class="fa fa-eye" style="margin-right: 6px;"></i> Voir la fiche';
						html += '</button> ';
						html += '<button class="btn btn-primary btn-sm btn-download-fiche" data-name="' + reg.name + '" style="padding: 6px 14px; font-size: 12px;">';
						html += '<i class="fa fa-download" style="margin-right: 6px;"></i> Télécharger';
						html += '</button>';
						html += '</td>';
						html += '</tr>';
					});

					html += '</tbody></table>';
				}

				html += '</div></div>';

				$(page.main).html(html);

				// Event handlers
				$('#btn-new-reregistration').on('click', function() {
					start_wizard(r.message);
				});

				$('.btn-view-fiche').on('click', function() {
					var name = $(this).data('name');
					view_fiche(name);
				});

				$('.btn-download-fiche').on('click', function() {
					var name = $(this).data('name');
					download_fiche(name);
				});
			}
		});
	}

	// ==================== WIZARD 3 ÉTAPES ====================

	function start_wizard(sessions) {
		current_step = 1;
		wizard_data = { _sessions: sessions || [] };
		render_step1(sessions);
	}

	function render_step1(sessions) {
		page.clear_actions();
		page.clear_fields();
		$(page.main).empty();

		var html = render_wizard_header(1, 'Vérification des informations', 'Vérifiez vos informations avant de continuer');

		html += '<div class="card" style="margin-bottom: 24px;">';
		html += '<div class="card-header"><div class="card-title"><i class="fa fa-user" style="color: var(--brand-blue);"></i> Identité</div></div>';
		html += '<div style="padding: 24px;">';
		html += render_readonly_fields([
			{label: 'Nom complet', value: student_data.nom_complet},
			{label: 'Matricule', value: student_data.matricule},
			{label: 'Email', value: student_data.email},
			{label: 'Date de naissance', value: student_data.date_naissance || '—'},
			{label: 'Lieu de naissance', value: student_data.lieu_naissance || '—'},
			{label: 'Téléphone', value: student_data.telephone || '—'},
			{label: 'Filière', value: student_data.filiere},
			{label: 'Niveau actuel', value: student_data.niveau_actuel}
		]);
		html += '</div></div>';

		if (student_data.nom_prenom_pere || student_data.nom_prenom_mere) {
			html += '<div class="card" style="margin-bottom: 24px;">';
			html += '<div class="card-header"><div class="card-title"><i class="fa fa-users" style="color: var(--brand-blue);"></i> Famille</div></div>';
			html += '<div style="padding: 24px;">';
			var family_fields = [];
			if (student_data.nom_prenom_pere) {
				family_fields.push({label: 'Père', value: student_data.nom_prenom_pere});
				family_fields.push({label: 'Tél. père', value: student_data.pere_telephone || '—'});
				family_fields.push({label: 'Profession père', value: student_data.pere_profession || '—'});
				family_fields.push({label: 'Ville père', value: student_data.pere_ville || '—'});
			}
			if (student_data.nom_prenom_mere) {
				family_fields.push({label: 'Mère', value: student_data.nom_prenom_mere});
				family_fields.push({label: 'Tél. mère', value: student_data.telephone_mere || '—'});
				family_fields.push({label: 'Profession mère', value: student_data.profession_mere || '—'});
				family_fields.push({label: 'Ville mère', value: student_data.mere_ville || '—'});
			}
			if (student_data.nom_prenom_sponsor) {
				family_fields.push({label: 'Sponsor', value: student_data.nom_prenom_sponsor});
				family_fields.push({label: 'Tél. sponsor', value: student_data.telephone_sponsor || '—'});
				family_fields.push({label: 'Profession sponsor', value: student_data.profession_sponsor || '—'});
				family_fields.push({label: 'Ville sponsor', value: student_data.sponsor_ville || '—'});
			}
			html += render_readonly_fields(family_fields);
			html += '</div></div>';
		}

		if (student_data.dernier_etablissement || student_data.diplome_entree) {
			html += '<div class="card" style="margin-bottom: 24px;">';
			html += '<div class="card-header"><div class="card-title"><i class="fa fa-graduation-cap" style="color: var(--brand-blue);"></i> Études antérieures</div></div>';
			html += '<div style="padding: 24px;">';
			var etudes_fields = [];
			if (student_data.dernier_etablissement) etudes_fields.push({label: 'Dernier établissement', value: student_data.dernier_etablissement});
			if (student_data.diplome_entree) etudes_fields.push({label: 'Diplôme d\'entrée', value: student_data.diplome_entree});
			if (student_data.matricule_diplome) etudes_fields.push({label: 'Matricule du diplôme', value: student_data.matricule_diplome});
			html += render_readonly_fields(etudes_fields);
			html += '</div></div>';
		}

		// Session & Semestre selection
		html += '<div class="card">';
		html += '<div class="card-header"><div class="card-title"><i class="fa fa-calendar" style="color: var(--brand-blue);"></i> Choix de la session</div></div>';
		html += '<div style="padding: 24px;">';
		html += '<div class="form-group" style="margin-bottom: 16px;">';
		html += '<label>Session de réinscription *</label>';
		html += '<select id="wizard-session" class="form-control" style="width: 100%;">';
		html += '<option value="">-- Sélectionner une session --</option>';
		(sessions || []).forEach(function(s) {
			html += '<option value="' + s.name + '">' + s.name + ' (' + s.academic_year + ')</option>';
		});
		html += '</select>';
		html += '</div>';
		html += '<div class="form-group">';
		html += '<label>Semestre *</label>';
		html += '<select id="wizard-semestre" class="form-control" style="width: 100%;">';
		html += '<option value="">-- Sélectionner un semestre --</option>';
		html += '<option value="Semestre 1">Semestre 1</option>';
		html += '<option value="Semestre 2">Semestre 2</option>';
		html += '<option value="Les deux">Les deux</option>';
		html += '</select>';
		html += '</div>';
		html += '</div></div>';

		html += render_wizard_footer([
			{id: 'wizard-next-1', label: 'Suivant : Confirmation', class: 'btn-primary', disabled: true}
		]);

		$(page.main).html(html);

		// Event handlers
		$('#wizard-session, #wizard-semestre').on('change', function() {
			var session = $('#wizard-session').val();
			var semestre = $('#wizard-semestre').val();
			$('#wizard-next-1').prop('disabled', !(session && semestre));
		});

		$('#wizard-next-1').on('click', function() {
			if (!$(this).prop('disabled')) {
				wizard_data.session = $('#wizard-session').val();
				wizard_data.semestre = $('#wizard-semestre').val();
				render_step2();
			}
		});
	}

	function render_step2() {
		current_step = 2;
		page.clear_actions();
		page.clear_fields();
		$(page.main).empty();

		var html = render_wizard_header(2, 'Confirmation', 'Confirmez votre réinscription avant validation finale');

		html += '<div class="alert alert-info" style="margin-bottom: 24px; background: linear-gradient(90deg, var(--bg-badge) 0%, #DBEAFE 100%); border-left: 4px solid var(--brand-blue);">';
		html += '<i class="fa fa-info-circle" style="margin-right: 10px; color: var(--brand-blue);"></i>';
		html += '<strong>Récapitulatif de votre réinscription :</strong> Veuillez vérifier toutes les informations ci-dessous avant de valider.';
		html += '</div>';

		// Session info
		html += '<div class="card" style="margin-bottom: 16px;">';
		html += '<div class="card-header"><div class="card-title">Session & Semestre</div></div>';
		html += '<div style="padding: 24px;">';
		html += render_readonly_fields([
			{label: 'Session de réinscription', value: wizard_data.session},
			{label: 'Semestre', value: wizard_data.semestre}
		]);
		html += '</div></div>';

		// Student info recap
		html += '<div class="card" style="margin-bottom: 16px;">';
		html += '<div class="card-header"><div class="card-title">Votre identité</div></div>';
		html += '<div style="padding: 24px;">';
		html += render_readonly_fields([
			{label: 'Nom complet', value: student_data.nom_complet},
			{label: 'Matricule', value: student_data.matricule},
			{label: 'Filière', value: student_data.filiere},
			{label: 'Niveau actuel', value: student_data.niveau_actuel},
			{label: 'Email', value: student_data.email}
		]);
		html += '</div></div>';

		// Legal/confirmation checkbox
		html += '<div class="checkbox-group" style="margin-bottom: 24px;">';
		html += '<input type="checkbox" id="wizard-confirm" style="width: 18px; height: 18px; margin-top: 2px;">';
		html += '<label for="wizard-confirm" style="flex: 1; cursor: pointer;">';
		html += 'Je certifie l\'exactitude des informations ci-dessus et je confirme ma demande de réinscription pour l\'année académique concernée.';
		html += '</label>';
		html += '</div>';

		html += render_wizard_footer([
			{id: 'wizard-back-2', label: '← Retour', class: 'btn-secondary'},
			{id: 'wizard-submit', label: 'Valider la réinscription', class: 'btn-primary', disabled: true}
		]);

		$(page.main).html(html);

		$('#wizard-confirm').on('change', function() {
			$('#wizard-submit').prop('disabled', !this.checked);
		});

		$('#wizard-back-2').on('click', function() {
			render_step1(wizard_data._sessions);
		});

		$('#wizard-submit').on('click', function() {
			submit_wizard();
		});
	}

	function submit_wizard() {
		// Show loading
		$('#wizard-submit').prop('disabled', true).html('<i class="fa fa-spinner fa-spin" style="margin-right: 8px;"></i> Validation...');

		frappe.call({
			method: 'udshed.api.reregistration.submit_reinscription',
			args: {
				matricule: student_matricule,
				reinscription_session: wizard_data.session,
				semestre: wizard_data.semestre
			},
			callback: function(r) {
				if (r.message && r.message.status) {
					reregistration_name = r.message.name;
					render_step3(r.message);
				} else {
					frappe.msgprint(__('Erreur: ') + (r.message ? r.message.message : 'Inconnue'));
					$('#wizard-submit').prop('disabled', false).html('Valider la réinscription');
				}
			},
			error: function(r) {
				frappe.msgprint(__('Erreur lors de la soumission: ') + (r.message || ''));
				$('#wizard-submit').prop('disabled', false).html('Valider la réinscription');
			}
		});
	}

	function render_step3(result) {
		current_step = 3;
		page.clear_actions();
		page.clear_fields();
		$(page.main).empty();

		var html = render_wizard_header(3, 'Réinscription réussie !', 'Votre demande a été validée avec succès.');

		html += '<div style="text-align: center; margin-bottom: 32px;">';
		html += '<div class="success-icon" style="margin: 0 auto 24px;">';
		html += '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--brand-emerald)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
		html += '</div>';
		html += '<h2 style="color: var(--text-primary); margin-bottom: 8px;">Réinscription validée</h2>';
		html += '<p style="color: var(--text-secondary);">Votre fiche de réinscription a été générée avec le statut <strong>Validée</strong>.</p>';
		html += '</div>';

		html += '<div class="card" style="margin-bottom: 24px;">';
		html += '<div class="card-header"><div class="card-title">Détails de la réinscription</div></div>';
		html += '<div style="padding: 24px;">';
		html += render_readonly_fields([
			{label: 'Référence', value: result.name},
			{label: 'Session', value: wizard_data.session},
			{label: 'Semestre', value: wizard_data.semestre},
			{label: 'Année académique', value: result.academic_year || '—'},
			{label: 'Niveau', value: result.niveau || student_data.niveau_actuel},
			{label: 'Filière', value: result.filiere || student_data.filiere},
			{label: 'Statut', value: '<span class="badge badge-success">Validée</span>'}
		]);
		html += '</div></div>';

		html += '<div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;">';
		html += '<button class="btn btn-primary btn-lg" id="btn-download-final" style="min-width: 220px;">';
		html += '<i class="fa fa-download" style="margin-right: 8px;"></i> Télécharger la fiche';
		html += '</button>';
		html += '<button class="btn btn-secondary btn-lg" id="btn-back-dashboard" style="min-width: 200px;">';
		html += '<i class="fa fa-arrow-left" style="margin-right: 8px;"></i> Retour au tableau de bord';
		html += '</button>';
		html += '</div>';

		$(page.main).html(html);

		$('#btn-download-final').on('click', function() {
			download_fiche(reregistration_name);
		});

		$('#btn-back-dashboard').on('click', function() {
			load_existing_registrations();
		});
	}

	function view_fiche(name) {
		// Open in new tab/window or modal
		frappe.set_route('Form', 'Academic Reregistration', name);
	}

	function download_fiche(name) {
		frappe.call({
			method: 'udshed.api.reregistration.telecharger_fiche_reinscription',
			args: { reregistration_name: name },
			callback: function(r) {
				// Download handled by frappe.local.response
			}
		});
	}

	// ==================== HELPER FUNCTIONS ====================

	function render_wizard_header(step, title, subtitle) {
		var steps = [
			{num: 1, label: 'Vérification'},
			{num: 2, label: 'Confirmation'},
			{num: 3, label: 'Succès'}
		];

		var html = '<div style="margin-bottom: 32px;">';
		html += '<div class="progress-bar" style="margin-bottom: 24px;">';
		html += '<div class="progress-labels">';
		steps.forEach(function(s, i) {
			var cls = i + 1 < step ? 'completed' : (i + 1 === step ? 'active' : '');
			html += '<div class="progress-label ' + cls + '">' + s.label + '</div>';
		});
		html += '</div>';
		html += '<div style="display: flex; gap: 4px;">';
		steps.forEach(function(s, i) {
			var cls = 'progress-step';
			if (i + 1 < step) cls += ' completed';
			else if (i + 1 === step) cls += ' active';
			html += '<div class="' + cls + '"></div>';
		});
		html += '</div></div>';
		html += '<h2 style="font-size: 24px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px;">' + title + '</h2>';
		html += '<p style="color: var(--text-secondary);">' + subtitle + '</p>';
		html += '</div>';
		return html;
	}

	function render_wizard_footer(buttons) {
		var html = '<div style="display: flex; gap: 12px; justify-content: flex-end; margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--border-color);">';
		buttons.forEach(function(btn) {
			var disabled = btn.disabled ? 'disabled' : '';
			html += '<button id="' + btn.id + '" class="btn ' + btn.class + ' ' + disabled + '" ' + disabled + '>' + btn.label + '</button>';
		});
		html += '</div>';
		return html;
	}

	function render_readonly_fields(fields) {
		var html = '<table class="info-table" style="width: 100%; border-collapse: collapse;">';
		fields.forEach(function(f) {
			html += '<tr>';
			html += '<td class="label" style="width: 220px; font-weight: 600; padding: 10px 12px; color: var(--text-secondary); font-size: 13px; vertical-align: top;">' + f.label + '</td>';
			html += '<td style="padding: 10px 12px; color: var(--text-primary); font-size: 14px;">' + f.value + '</td>';
			html += '</tr>';
		});
		html += '</table>';
		return html;
	}
};