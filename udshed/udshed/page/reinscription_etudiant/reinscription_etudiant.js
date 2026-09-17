frappe.pages['reinscription_etudiant'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Réinscription Étudiant',
		single_column: true
	});

	$(page.main).addClass('reinscription-wizard');

	var student_matricule = null;
	var student_data = null;
	var current_step = 1;
	var selected_session = null;
	var selected_semestre = null;
	var reregistration_name = null;
	var wizard_data = {};
	var parcours_notes = null;

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

		frappe.call({
			method: 'udshed.api.reregistration.get_open_sessions',
			callback: function(r) {
				var has_open_session = r.message && r.message.length > 0;
				var latest_reg = registrations.length > 0 ? registrations[0] : null;
				var session_academic_year = has_open_session ? r.message[0].academic_year : null;
				var can_register = has_open_session && (!latest_reg || latest_reg.academic_year !== session_academic_year);

				var html = '';

				if (can_register) {
					html += '<div style="margin-bottom: 24px; text-align: center;">';
					html += '<button class="btn btn-primary btn-lg" id="btn-new-reregistration" style="min-width: 280px; padding: 14px 32px; font-size: 15px;">';
					html += '<i class="fa fa-plus" style="margin-right: 8px;"></i> Nouveau : Se réinscrire';
					html += '</button>';
					html += '</div>';
				}

				html += '<div class="wz-card" style="overflow: hidden;">';
				html += '<div class="wz-card-header" style="padding: 16px 24px;">';
				html += '<h3 class="wz-card-title" style="margin: 0; font-size: 16px; font-weight: 600;">Mes fiches de réinscription</h3>';
				html += '</div>';
				html += '<div style="padding: 0;">';

				if (registrations.length === 0) {
					html += '<div class="wz-empty">';
					html += '<i class="fa fa-file-text-o"></i>';
					html += 'Aucune réinscription trouvée.';
					html += '</div>';
				} else {
					html += '<table class="wz-table" style="width: 100%; border-collapse: collapse;">';
					html += '<thead><tr>';
					html += '<th style="width: 40px;">#</th>';
					html += '<th>Année académique</th>';
					html += '<th>Niveau</th>';
					html += '<th>Session</th>';
					html += '<th>Statut</th>';
					html += '<th style="width: 180px;">Actions</th>';
					html += '</tr></thead>';
					html += '<tbody>';

					registrations.forEach(function(reg, index) {
						var statut_class = reg.statut === 'Validée' ? 'wz-badge-ok' : 'wz-badge-neutral';
						html += '<tr>';
						html += '<td>' + (index + 1) + '</td>';
						html += '<td class="wz-strong">' + (reg.academic_year || '—') + '</td>';
						html += '<td>' + (reg.niveau || '—') + '</td>';
						html += '<td>' + (reg.reinscription_session || '—') + '</td>';
						html += '<td><span class="wz-badge ' + statut_class + '">' + (reg.statut || '—') + '</span></td>';
						html += '<td>';
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

	// ==================== WIZARD 2 ÉTAPES + SUCCÈS ====================

	function start_wizard(sessions) {
		current_step = 1;
		wizard_data = { _sessions: sessions || [] };
		parcours_notes = null;
		render_step1(sessions);
	}

	function render_step1(sessions) {
		current_step = 1;
		wizard_data.preview = null;
		wizard_data.master_niveau = null;
		page.clear_actions();
		page.clear_fields();
		$(page.main).empty();

		var html = render_wizard_header(1, 'Fiche de réinscription',
			'Votre fiche est pré-remplie à partir de votre dossier existant. Vérifiez toutes les informations, puis choisissez la session et le semestre.');

		// Bilan (décision + niveau calculé automatiquement) - chargé à la sélection de la session
		html += '<div class="wz-card" id="wz-preview">';
		html += render_preview_placeholder();
		html += '</div>';

		// Parcours (notes + matières à reprendre) - chargé en asynchrone
		html += '<div class="wz-card" id="wz-parcours">';
		html += '<div class="wz-loading"><i class="fa fa-spinner fa-spin" style="margin-right: 8px;"></i> Vérification de votre parcours…</div>';
		html += '</div>';

		// Fiche complète : tous les champs du doctype, pré-remplis
		html += build_fiche_sections();

		html += render_wizard_footer([
			{id: 'wizard-next-1', label: 'Suivant : Confirmation', class: 'btn-primary', disabled: true}
		]);

		$(page.main).html(html);

		$('#wizard-semestre').on('change', function() {
			wizard_data.semestre = $('#wizard-semestre').val();
			load_grid($('#wizard-session').val(), wizard_data.semestre);
			update_grid_state();
		});

		$('#wizard-session').on('change', function() {
			load_preview($(this).val());
			$('#wizard-next-1').prop('disabled', true);
		});

		$('#wizard-master-level').on('change', function() {
			wizard_data.master_niveau = $(this).val();
			$('#wz-niveau-auto').text($(this).val());
			var session = $('#wizard-session').val();
			var semestre = $('#wizard-semestre').val();
			if (session && semestre) load_grid(session, semestre);
			update_grid_state();
		});

		$('#wizard-next-1').on('click', function() {
			if (!$(this).prop('disabled')) {
				wizard_data.session = $('#wizard-session').val();
				wizard_data.semestre = $('#wizard-semestre').val();
				render_step2();
			}
		});

		load_parcours();
	}

	// ==================== FICHE DE RÉINSCRIPTION (pré-remplie) ====================

	function build_fiche_sections() {
		var s = student_data || {};
		var html = '';

		// Identité
		html += render_fiche_section('Identité de l\'étudiant', 'fa-user', [
			{label: 'Étudiant (matricule)', value: esc(s.name)},
			{label: 'Dossier d\'origine', value: esc(s.dossier_origine)},
			{label: 'Nom et prénom', value: esc(s.nom_complet)},
			{label: 'Email', value: esc(s.email)},
			{label: 'Date de naissance', value: esc(s.date_naissance)},
			{label: 'Lieu de naissance', value: esc(s.lieu_naissance)},
			{label: 'Téléphone', value: esc(s.telephone)}
		]);

		// Inscription
		html += render_fiche_section('Inscription', 'fa-calendar-check-o', [
			{label: 'Session de réinscription *', value: session_select_html()},
			{label: 'Année académique', value: '<span id="wz-academic-year">—</span>'},
			{label: 'Statut', value: '<span class="wz-badge wz-badge-ok">Validée</span>'},
			{label: 'Filière', value: esc(s.filiere)},
			{label: 'Semestre *', value: semestre_select_html()},
			{label: 'Niveau de réinscription', value: '<span id="wz-niveau-auto">—</span>'}
		]);

		// Études antérieures
		html += render_fiche_section('Études antérieures', 'fa-graduation-cap', [
			{label: 'Dernier établissement fréquenté', value: esc(s.dernier_etablissement)},
			{label: 'Diplôme d\'entrée', value: esc(s.diplome_entree)},
			{label: 'Matricule du diplôme', value: esc(s.matricule_diplome)}
		]);

		// Informations académiques
		html += render_fiche_section('Informations académiques', 'fa-university', [
			{label: 'Dernier niveau suivi', value: '<span id="wz-dernier-classe">' + esc(s.dernier_classe) + '</span>'},
			{label: 'Niveau précédent', value: '<span id="wz-niveau-precedent">—</span>'},
			{label: 'Décision des résultats', value: '<span id="wz-decision">—</span>'}
		]);

		// Père
		html += render_fiche_section('Identification du Père', 'fa-male', [
			{label: 'Nom et prénom', value: esc(s.nom_prenom_pere)},
			{label: 'Téléphone', value: esc(s.pere_telephone)},
			{label: 'Profession', value: esc(s.pere_profession)},
			{label: 'Ville', value: esc(s.pere_ville)}
		]);

		// Mère
		html += render_fiche_section('Identification de la Mère', 'fa-female', [
			{label: 'Nom et prénom', value: esc(s.nom_prenom_mere)},
			{label: 'Téléphone', value: esc(s.telephone_mere)},
			{label: 'Profession', value: esc(s.profession_mere)},
			{label: 'Ville', value: esc(s.mere_ville)}
		]);

		// Sponsor
		html += render_fiche_section('Identification du Sponsor', 'fa-handshake-o', [
			{label: 'Nom et prénom', value: esc(s.nom_prenom_sponsor)},
			{label: 'Téléphone', value: esc(s.telephone_sponsor)},
			{label: 'Profession', value: esc(s.profession_sponsor)},
			{label: 'Ville', value: esc(s.sponsor_ville)}
		]);

		// Activités
		html += render_fiche_section('Informations complémentaires', 'fa-info-circle', [
			{label: 'Activités sportives', value: esc(s.activites_sportives)},
			{label: 'Activités associatives', value: esc(s.activites_associatives)},
			{label: 'Activités culturelles', value: esc(s.activites_culturelles)},
			{label: 'Connaissances informatiques', value: esc(s.connaissances_informatiques)}
		]);

		// Grille de matières (résultats année précédente + matières inscrites)
		html += '<div class="wz-card" id="wz-grid">';
		html += render_grid_placeholder();
		html += '</div>';

		return html;
	}

	function render_fiche_section(title, icon, rows) {
		var html = '<div class="wz-card">';
		html += '<div class="wz-card-header"><div class="wz-card-title">';
		if (icon) html += '<i class="fa ' + icon + ' wz-card-icon"></i>';
		html += title + '</div></div>';
		html += '<div class="wz-card-body">' + render_fiche_grid(rows) + '</div></div>';
		return html;
	}

	function render_fiche_grid(rows) {
		var html = '<div class="wz-fiche-grid">';
		(rows || []).forEach(function(r) {
			var v = (r.value === undefined || r.value === null || r.value === '') ? '—' : r.value;
			html += '<div class="wz-fiche-field">';
			html += '<div class="wz-fiche-label">' + r.label + '</div>';
			html += '<div class="wz-fiche-value">' + v + '</div>';
			html += '</div>';
		});
		html += '</div>';
		return html;
	}

	function session_select_html() {
		var html = '<select id="wizard-session" class="form-control" style="width: 100%;">';
		html += '<option value="">-- Sélectionner une session --</option>';
		(wizard_data._sessions || []).forEach(function(s) {
			html += '<option value="' + esc(s.name) + '">' + esc(s.name) + ' (' + esc(s.academic_year) + ')</option>';
		});
		html += '</select>';
		return html;
	}

	function semestre_select_html() {
		var html = '<select id="wizard-semestre" class="form-control" style="width: 100%;">';
		html += '<option value="">-- Sélectionner un semestre --</option>';
		['Semestre 1', 'Semestre 2', 'Les deux'].forEach(function(v) {
			html += '<option value="' + esc(v) + '">' + esc(v) + '</option>';
		});
		html += '</select>';
		return html;
	}

	function render_preview_placeholder() {
		return '<div class="wz-card-header"><div class="wz-card-title"><i class="fa fa-compass wz-card-icon"></i> Bilan de votre réinscription</div></div>' +
			'<div class="wz-card-body"><div class="wz-info"><i class="fa fa-info-circle" style="margin-right: 8px;"></i> ' +
			'Sélectionnez une session de réinscription pour afficher votre décision et le niveau calculé automatiquement.</div></div>';
	}

	function load_preview(session) {
		if (!session) {
			wizard_data.preview = null;
			$('#wz-preview').html(render_preview_placeholder());
			update_fiche_dynamic(null);
			return;
		}
		frappe.call({
			method: 'udshed.api.reregistration.get_reregistration_preview',
			args: { matricule: student_matricule, reinscription_session: session },
			callback: function(r) {
				wizard_data.preview = r.message || null;
				$('#wz-preview').html(render_preview_card(wizard_data.preview));
				update_fiche_dynamic(wizard_data.preview);
$('#wizard-master-level').off('change').on('change', function() {
				wizard_data.master_niveau = $(this).val();
				$('#wz-niveau-auto').text($(this).val());
				var session = $('#wizard-session').val();
				var semestre = $('#wizard-semestre').val();
				if (session && semestre) load_grid(session, semestre);
				update_grid_state();
			});
				var semestre = $('#wizard-semestre').val();
				$('#wizard-next-1').prop('disabled', !(semestre && wizard_data.preview));
				load_grid(session, semestre);
			},
			error: function() {
				wizard_data.preview = null;
				$('#wz-preview').html('<div class="wz-card-header"><div class="wz-card-title"><i class="fa fa-compass wz-card-icon"></i> Bilan de votre réinscription</div></div>' +
					'<div class="wz-card-body"><div class="wz-empty">Impossible de calculer votre bilan. Réessayez plus tard.</div></div>');
			}
		});
	}

	function render_preview_card(p) {
		if (!p) return render_preview_placeholder();
		var html = '<div class="wz-card-header"><div class="wz-card-title"><i class="fa fa-compass wz-card-icon"></i> Bilan de votre réinscription</div></div>';
		html += '<div class="wz-card-body">';
		html += decision_badge(p.decision);
		html += render_fiche_grid([
			{label: 'Année académique', value: esc(p.academic_year)},
			{label: 'Dernier niveau suivi', value: esc(p.dernier_classe)},
			{label: 'Niveau de réinscription', value: render_niveau_value(p)},
			{label: 'Niveau précédent', value: esc(p.niveau_precedent)}
		]);
		html += '</div>';
		return html;
	}

	function render_niveau_value(p) {
		if (!p.master) return '<span class="wz-strong">' + esc(p.niveau) + '</span>';
		var html = '<div class="wz-info" style="margin-bottom: 8px;">' +
			'<i class="fa fa-exclamation-circle" style="margin-right: 8px;"></i> Fin de cycle : l\'entrée au Master est accordée par le jury de décision.</div>';
		html += '<select id="wizard-master-level" class="form-control" style="width: 100%;">';
		(p.master_levels || []).forEach(function(l) {
			html += '<option value="' + esc(l) + '">' + esc(l) + '</option>';
		});
		html += '</select>';
		return html;
	}

	function update_fiche_dynamic(p) {
		if (!p) {
			$('#wz-academic-year').text('—');
			$('#wz-niveau-auto').text('—');
			$('#wz-niveau-precedent').text('—');
			$('#wz-decision').text('—');
			return;
		}
		$('#wz-academic-year').text(p.academic_year || '—');
		$('#wz-niveau-auto').text(p.master ? '(Master — à préciser)' : (p.niveau || '—'));
		$('#wz-niveau-precedent').text(p.niveau_precedent || '—');
		$('#wz-dernier-classe').text(p.dernier_classe || '—');
		$('#wz-decision').html(decision_badge(p.decision));
	}

	function load_parcours() {
		frappe.call({
			method: 'udshed.api.reregistration.get_niveau_precedent',
			args: { filiere: student_data.filiere, niveau: student_data.niveau_actuel },
			callback: function(r) {
				var niveau_precedent_label = r.message || '';
				frappe.call({
					method: 'udshed.api.reregistration.get_student_notes',
					args: {
						student: student_matricule,
						filiere: student_data.filiere,
						niveau_precedent_label: niveau_precedent_label
					},
					callback: function(r2) {
						parcours_notes = r2.message || [];
						render_parcours(parcours_notes, niveau_precedent_label);
					},
					error: function() {
						$('#wz-parcours').html('<div class="wz-empty">Impossible de charger vos notes. Réessayez plus tard.</div>');
					}
				});
			},
			error: function() {
				$('#wz-parcours').html('<div class="wz-empty">Impossible de vérifier votre parcours. Réessayez plus tard.</div>');
			}
		});
	}

	function render_parcours(notes, niveau_precedent_label) {
		var decision = '';
		(notes || []).forEach(function(n) {
			if (n.decision_annee) decision = n.decision_annee;
		});

		var reprendre = (notes || []).filter(function(n) {
			return n.statut && n.statut !== 'Validé';
		});

		var html = '<div class="wz-card-header"><div class="wz-card-title"><i class="fa fa-graduation-cap wz-card-icon"></i> Vérification parcours</div></div>';
		html += '<div class="wz-card-body">';

		if (niveau_precedent_label) {
			html += decision_badge(decision);
		}

		if (!notes || notes.length === 0) {
			if (niveau_precedent_label) {
				html += '<div class="wz-empty">Aucune note trouvée pour le niveau « ' + niveau_precedent_label + ' ».</div>';
			} else {
				html += '<div class="wz-info">C\'est votre première année dans cette filière : aucune note du niveau précédent n\'est disponible.</div>';
			}
		} else {
			html += '<h4 class="wz-subtitle">Résultats du niveau « ' + niveau_precedent_label + ' »</h4>';
			html += '<table class="wz-table">';
			html += '<thead><tr>';
			html += '<th>UE / Intitulé</th>';
			html += '<th>Semestre</th>';
			html += '<th>Note</th>';
			html += '<th>Statut</th>';
			html += '</tr></thead>';
			html += '<tbody>';
			notes.forEach(function(n) {
				var note = (n.note_finale !== null && n.note_finale !== undefined) ? format_note(n.note_finale) : '—';
				var valide = n.statut === 'Validé';
				html += '<tr>';
				html += '<td class="wz-strong">' + esc(n.ue_name || n.teaching_unit || '—') + '</td>';
				html += '<td>' + (n.semestre || '—') + '</td>';
				html += '<td class="' + (valide ? 'wz-note-ok' : 'wz-note-bad') + '">' + note + '</td>';
				html += '<td><span class="wz-badge ' + (valide ? 'wz-badge-ok' : 'wz-badge-bad') + '">' + (n.statut || '—') + '</span></td>';
				html += '</tr>';
			});
			html += '</tbody></table>';

			html += '<div class="wz-reprendre">';
			html += '<h4 class="wz-subtitle">Matières à reprendre (' + reprendre.length + ')</h4>';
			if (reprendre.length === 0) {
				html += '<div class="wz-success-line"><i class="fa fa-check-circle" style="margin-right: 8px;"></i> Aucune matière à reprendre. Vous pouvez poursuivre votre parcours sans rattrapage.</div>';
			} else {
				html += '<ul class="wz-list-reprendre">';
				reprendre.forEach(function(n) {
					var note = (n.note_finale !== null && n.note_finale !== undefined) ? ' (' + format_note(n.note_finale) + ') ' : ' ';
					html += '<li><i class="fa fa-exclamation-circle"></i> ' + esc(n.ue_name || n.teaching_unit || '—') + note + ' — semestre ' + (n.semestre || '—') + '</li>';
				});
				html += '</ul>';
			}
			html += '</div>';
		}

		html += '</div>';
		$('#wz-parcours').html(html);
	}

	// ==================== GRILLE DE MATIÈRES (résultats + cours inscrits) ====================

	function load_grid(session, semestre) {
		if (!session || !semestre) {
			wizard_data.grid = null;
			var el = $('#wz-grid');
			if (el.length) el.html(render_grid_placeholder());
			return;
		}
		frappe.call({
			method: 'udshed.api.reregistration.get_reregistration_grid',
			args: {
				matricule: student_matricule,
				reinscription_session: session,
				semestre: semestre,
				niveau: (wizard_data.preview && wizard_data.preview.master) ? wizard_data.master_niveau : null
			},
			callback: function(r) {
				wizard_data.grid = r.message || null;
				var el = $('#wz-grid');
				if (el.length) {
					el.html(render_grid_card(wizard_data.grid));
					bind_grid_events();
					update_grid_state();
				}
			},
			error: function() {
				wizard_data.grid = null;
				var el = $('#wz-grid');
				if (el.length) el.html('<div class="wz-card-header"><div class="wz-card-title"><i class="fa fa-th-list wz-card-icon"></i> Grille de matières & résultats de l\'année précédente</div></div>' +
					'<div class="wz-card-body"><div class="wz-empty"><i class="fa fa-exclamation-circle"></i>Impossible de charger la grille. Réessayez plus tard.</div></div>');
			}
		});
	}

	function render_grid_placeholder() {
		return '<div class="wz-card-header"><div class="wz-card-title"><i class="fa fa-th-list wz-card-icon"></i> Grille de matières & résultats de l\'année précédente</div></div>' +
			'<div class="wz-card-body"><div class="wz-info"><i class="fa fa-info-circle" style="margin-right: 8px;"></i> Sélectionnez la session puis le semestre pour afficher la grille des matières (résultats de l\'année précédente et matières à inscrire).</div></div>';
	}

	function render_grid_card(data, opts) {
		if (!data) return render_grid_placeholder();
		opts = opts || {};
		var st = data.stats || {};
		var limit = st.credit_limit_per_semester || 30;
		var rows = data.cours_inscrits || [];
		var sem = opts.readonly ? wizard_data.semestre : current_semestre();
		var view_rows = view_grid_rows(rows, sem);
		wizard_data.grid_view = view_rows;

		var html = '<div class="wz-card-header"><div class="wz-card-title"><i class="fa fa-th-list wz-card-icon"></i> Grille de matières & résultats de l\'année précédente</div></div>';
		html += '<div class="wz-card-body">';

		// Résultats de l'année précédente
		var rs = data.resultats_precedents || [];
		var validees = rs.filter(function(r) { return r.valide; }).length;
		html += '<h4 class="wz-subtitle">Résultats de l\'année précédente (' + validees + ' validée(s) / ' + rs.length + ')</h4>';
		if (rs.length === 0) {
			html += '<div class="wz-empty">Aucun résultat disponible pour le niveau précédent.</div>';
		} else {
			html += '<table class="wz-table">';
			html += '<thead><tr><th>UE / Intitulé</th><th>Semestre</th><th>Crédits</th><th>Note /20</th><th>Statut</th><th>Dette</th></tr></thead>';
			html += '<tbody>';
			rs.forEach(function(r) {
				html += '<tr>';
				html += '<td class="wz-strong">' + esc(r.intitule || r.teaching_unit || '—') + '</td>';
				html += '<td>' + esc(r.semestre || '—') + '</td>';
				html += '<td>' + (r.credits || 0) + '</td>';
				html += '<td class="' + (r.valide ? 'wz-note-ok' : 'wz-note-bad') + '">' + format_note(r.note) + '</td>';
				html += '<td><span class="wz-badge ' + (r.valide ? 'wz-badge-ok' : 'wz-badge-bad') + '">' + esc(r.statut || (r.valide ? 'Validé' : 'Non Validé')) + '</span></td>';
				html += '<td>' + (r.est_dette ? '<span style="color: var(--rw-gold);"><i class="fa fa-exclamation-circle" style="margin-right: 4px;"></i>Dette</span>' : '<span class="wz-strong wz-note-ok">Aucune</span>') + '</td>';
				html += '</tr>';
			});
			html += '</tbody></table>';
		}

		// Matières à inscrire : interactives (dettes verrouillées)
		html += '<div class="wz-reprendre">';
		html += '<h4 class="wz-subtitle">Matières à inscrire — niveau « ' + esc(data.niveau || '') + ' » (' + view_rows.length + ')</h4>';
		if (data.redoublement) {
			html += '<div class="wz-info"><i class="fa fa-info-circle" style="margin-right: 8px;"></i> Décision Ajourné : le programme complet du niveau « ' + esc(data.niveau || '') + ' » est repris. Toutes les matières sont cochées et verrouillées.</div>';
		} else {
			html += '<div class="wz-info"><i class="fa fa-info-circle" style="margin-right: 8px;"></i> Les dettes du niveau « ' + esc(data.niveau_precedent || '—') + ' » sont obligatoires et verrouillées. Cochez les autres matières de votre choix : la limite de ' + limit + ' crédits par semestre ne peut pas être dépassée.</div>';
		}

		var semesters_to_show = ['Semestre 1', 'Semestre 2'].filter(function(s) {
			return sem === 'Les deux' || sem === s;
		});
		html += '<div class="wz-credit-badges">';
		semesters_to_show.forEach(function(s) {
			html += credit_badge_html(s, semester_credits(view_rows, s), limit);
		});
		html += '</div>';

		var nb_checked = view_rows.filter(function(c) { return c.inscrire; }).length;
		html += '<div style="font-size: 13px; color: var(--rw-text-secondary); margin: 4px 0 12px;">Matières cochées : <strong id="wz-inscrits-count">' + nb_checked + '</strong> / ' + view_rows.length + '</div>';

		if (view_rows.length === 0) {
			html += '<div class="wz-empty">Aucune matière inscrite pour ce niveau ou ce semestre.</div>';
		} else {
			html += '<table class="wz-table">';
			html += '<thead><tr><th style="width: 40px;">Cocher</th><th>Matière / UE</th><th>Semestre</th><th>Crédits</th><th>Justification</th></tr></thead>';
			html += '<tbody>';
			view_rows.forEach(function(c) {
				var locked = opts.readonly || c.verrouille;
				html += '<tr class="' + (c.source === 'dette' ? 'wz-row-dette' : (c.verrouille ? 'wz-row-locked' : '')) + '">';
				html += '<td><input type="checkbox" class="wz-course-check" data-tu="' + esc(c.teaching_unit) + '"' + (c.inscrire ? ' checked' : '') + (locked ? ' disabled' : '') + '></td>';
				html += '<td class="wz-strong">' + esc(c.intitule || c.teaching_unit || '—') + (c.source === 'dette' ? ' <span class="wz-badge wz-badge-warn">Dette</span>' : '') + '</td>';
				html += '<td>' + esc(c.semestre || '—') + '</td>';
				html += '<td>' + (c.credits || 0) + '</td>';
				html += '<td style="font-size: 13px; color: var(--rw-text-muted);">' + esc(c.motif || '') + '</td>';
				html += '</tr>';
			});
			html += '</tbody></table>';
		}

		html += '<div class="wz-alert-danger" id="wz-grid-overflow" style="display:none;"><i class="fa fa-exclamation-triangle" style="margin-right: 8px;"></i> <span id="wz-grid-overflow-text"></span></div>';

		html += '</div>';
		html += '</div>';
		return html;
	}

	function current_semestre() {
		return $('#wizard-semestre').val() || wizard_data.semestre || null;
	}

	function view_grid_rows(rows, sem) {
		return (rows || []).filter(function(c) {
			if (c.source === 'dette') return true;
			if (sem && sem !== 'Les deux') return c.semestre === sem;
			return true;
		});
	}

	function semester_credits(rows, sem) {
		var total = 0;
		(rows || []).forEach(function(c) {
			if (c.inscrire && c.semestre === sem) total += (c.credits || 0);
		});
		return total;
	}

	function credit_badge_html(sem, total, limit) {
		var id = 'wz-credit-' + sem.replace(/\s+/g, '');
		return '<span class="wz-badge ' + (total > limit ? 'wz-badge-bad' : 'wz-badge-ok') + '" id="' + id + '" style="margin-right: 8px;">Crédits ' + sem + ' : <strong class="wz-badge-total">' + total + '</strong> / ' + limit + '</span>';
	}

	function bind_grid_events() {
		$('.wz-course-check').off('change').on('change', function() {
			var tu = $(this).data('tu');
			var is_checked = this.checked ? 1 : 0;
			(wizard_data.grid_view || []).forEach(function(c) {
				if (c.teaching_unit === tu) c.inscrire = is_checked;
			});
			update_grid_state();
		});
	}

	function update_grid_state() {
		var st = (wizard_data.grid && wizard_data.grid.stats) || {};
		var limit = st.credit_limit_per_semester || 30;
		var rows = wizard_data.grid_view || [];
		var sem = current_semestre();

		['Semestre 1', 'Semestre 2'].forEach(function(s) {
			if (sem !== 'Les deux' && sem !== s) return;
			var total = semester_credits(rows, s);
			var el = $('#wz-credit-' + s.replace(/\s+/g, ''));
			if (el.length) {
				el.attr('class', 'wz-badge ' + (total > limit ? 'wz-badge-bad' : 'wz-badge-ok'));
				el.find('.wz-badge-total').text(total);
			}
		});

		var nb_checked = rows.filter(function(c) { return c.inscrire; }).length;
		var count_el = $('#wz-inscrits-count');
		if (count_el.length) count_el.text(nb_checked);

		var s1 = semester_credits(rows, 'Semestre 1');
		var s2 = semester_credits(rows, 'Semestre 2');
		var over = [];
		if (sem === 'Les deux' || sem === 'Semestre 1') {
			if (s1 > limit) over.push('Semestre 1 : ' + s1 + ' crédits cochés (maximum ' + limit + ')');
		}
		if (sem === 'Les deux' || sem === 'Semestre 2') {
			if (s2 > limit) over.push('Semestre 2 : ' + s2 + ' crédits cochés (maximum ' + limit + ')');
		}
		var banner = $('#wz-grid-overflow');
		if (banner.length) {
			if (over.length) {
				$('#wz-grid-overflow-text').text('La limite de crédits est dépassée — ' + over.join(' ; ') + ' . Décochez des matières pour continuer.');
				banner.show();
			} else {
				banner.hide();
			}
		}

		update_next_button(over.length > 0);
	}

	function update_next_button(over_limit) {
		var el = $('#wizard-next-1');
		if (!el.length) return;
		var master_ok = !(wizard_data.preview && wizard_data.preview.master) || !!wizard_data.master_niveau;
		var ok = !!(current_semestre() && wizard_data.preview && wizard_data.grid) && master_ok && !over_limit;
		el.prop('disabled', !ok);
	}

	function decision_badge(decision) {
		if (!decision) {
			return '<div class="wz-decision wz-decision-attente"><i class="fa fa-hourglass-half" style="margin-right: 8px;"></i> Décision de l\'année précédente : en cours d\'évaluation.</div>';
		}
		var cls = 'wz-decision-attente';
		if (decision === 'Admis') cls = 'wz-decision-admis';
		else if (decision === 'Ajourné') cls = 'wz-decision-ajourne';
		return '<div class="wz-decision ' + cls + '"><i class="fa ' + (decision === 'Admis' ? 'fa-check-circle' : decision === 'Ajourné' ? 'fa-times-circle' : 'fa-hourglass-half') + '" style="margin-right: 8px;"></i> Décision de l\'année précédente : <strong>' + decision + '</strong></div>';
	}

	function render_step2() {
		current_step = 2;
		page.clear_actions();
		page.clear_fields();
		$(page.main).empty();

		var html = render_wizard_header(2, 'Confirmation', 'Vérifiez votre fiche complète avant la validation finale');

		html += '<div class="wz-alert-info">';
		html += '<i class="fa fa-info-circle" style="margin-right: 10px;"></i>';
		html += '<strong>Récapitulatif :</strong> toutes les informations ci-dessous ont été pré-remplies à partir de votre dossier. Vérifiez-les avant de valider.';
		html += '</div>';

		html += build_fiche_recap();

		// Grille de matières (résultats + matières inscrites) recap
		html += '<div class="wz-card">';
		html += (wizard_data.grid ? render_grid_card(wizard_data.grid, {readonly: true}) : render_grid_placeholder());
		html += '</div>';

		// Matières à reprendre recap
		var reprendre = (parcours_notes || []).filter(function(n) {
			return n.statut && n.statut !== 'Validé';
		});
		html += '<div class="wz-card">';
		html += '<div class="wz-card-header"><div class="wz-card-title"><i class="fa fa-exclamation-circle wz-card-icon"></i> Matières à reprendre</div></div>';
		html += '<div class="wz-card-body">';
		if (reprendre.length === 0) {
			html += '<div class="wz-success-line"><i class="fa fa-check-circle" style="margin-right: 8px;"></i> Aucune matière à reprendre.</div>';
		} else {
			html += '<ul class="wz-list-reprendre">';
			reprendre.forEach(function(n) {
				html += '<li><i class="fa fa-exclamation-circle"></i> ' + esc(n.ue_name || n.teaching_unit || '—') + ' — semestre ' + (n.semestre || '—') + '</li>';
			});
			html += '</ul>';
		}
		html += '</div></div>';

		// Legal/confirmation checkbox
		var confirm_year = wizard_data.preview ? wizard_data.preview.academic_year : session_academic_year(wizard_data.session);
		html += '<div class="wz-checkbox-group">';
		html += '<input type="checkbox" id="wizard-confirm" class="wz-checkbox">';
		html += '<label for="wizard-confirm">';
		html += 'Je certifie l\'exactitude des informations ci-dessus et je confirme ma demande de réinscription pour l\'année académique ' + esc(confirm_year || '') + '.';
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

	function build_fiche_recap() {
		var s = student_data || {};
		var p = wizard_data.preview || {};
		var niveau_final = p.master ? wizard_data.master_niveau : p.niveau;
		var html = '';

		html += render_fiche_section('Bilan de votre réinscription', 'fa-compass', [
			{label: 'Session de réinscription', value: esc(wizard_data.session)},
			{label: 'Année académique', value: esc(p.academic_year || session_academic_year(wizard_data.session) || '—')},
			{label: 'Semestre', value: esc(wizard_data.semestre)},
			{label: 'Filière', value: esc(s.filiere)},
			{label: 'Niveau de réinscription', value: '<span class="wz-strong">' + esc(niveau_final || '—') + '</span>'},
			{label: 'Décision des résultats', value: decision_badge(p.decision)}
		]);

		html += render_fiche_section('Identité de l\'étudiant', 'fa-user', [
			{label: 'Étudiant (matricule)', value: esc(s.name)},
			{label: 'Dossier d\'origine', value: esc(s.dossier_origine)},
			{label: 'Nom et prénom', value: esc(s.nom_complet)},
			{label: 'Email', value: esc(s.email)},
			{label: 'Date de naissance', value: esc(s.date_naissance)},
			{label: 'Lieu de naissance', value: esc(s.lieu_naissance)},
			{label: 'Téléphone', value: esc(s.telephone)}
		]);

		html += render_fiche_section('Études antérieures', 'fa-graduation-cap', [
			{label: 'Dernier établissement fréquenté', value: esc(s.dernier_etablissement)},
			{label: 'Diplôme d\'entrée', value: esc(s.diplome_entree)},
			{label: 'Matricule du diplôme', value: esc(s.matricule_diplome)}
		]);

		html += render_fiche_section('Identification du Père', 'fa-male', [
			{label: 'Nom et prénom', value: esc(s.nom_prenom_pere)},
			{label: 'Téléphone', value: esc(s.pere_telephone)},
			{label: 'Profession', value: esc(s.pere_profession)},
			{label: 'Ville', value: esc(s.pere_ville)}
		]);

		html += render_fiche_section('Identification de la Mère', 'fa-female', [
			{label: 'Nom et prénom', value: esc(s.nom_prenom_mere)},
			{label: 'Téléphone', value: esc(s.telephone_mere)},
			{label: 'Profession', value: esc(s.profession_mere)},
			{label: 'Ville', value: esc(s.mere_ville)}
		]);

		html += render_fiche_section('Identification du Sponsor', 'fa-handshake-o', [
			{label: 'Nom et prénom', value: esc(s.nom_prenom_sponsor)},
			{label: 'Téléphone', value: esc(s.telephone_sponsor)},
			{label: 'Profession', value: esc(s.profession_sponsor)},
			{label: 'Ville', value: esc(s.sponsor_ville)}
		]);

		html += render_fiche_section('Informations complémentaires', 'fa-info-circle', [
			{label: 'Activités sportives', value: esc(s.activites_sportives)},
			{label: 'Activités associatives', value: esc(s.activites_associatives)},
			{label: 'Activités culturelles', value: esc(s.activites_culturelles)},
			{label: 'Connaissances informatiques', value: esc(s.connaissances_informatiques)}
		]);

		return html;
	}

	function submit_wizard() {
		$('#wizard-submit').prop('disabled', true).html('<i class="fa fa-spinner fa-spin" style="margin-right: 8px;"></i> Validation...');

		var cours = (wizard_data.grid_view || [])
			.filter(function(c) { return !c.verrouille; })
			.map(function(c) { return {teaching_unit: c.teaching_unit, inscrire: c.inscrire || 0}; });

		frappe.call({
			method: 'udshed.api.reregistration.submit_reinscription',
			args: {
				matricule: student_matricule,
				reinscription_session: wizard_data.session,
				semestre: wizard_data.semestre,
				niveau: (wizard_data.preview && wizard_data.preview.master) ? wizard_data.master_niveau : null,
				cours: cours.length ? cours : []
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

		var html = '<div style="margin-bottom: 32px;">';
		html += '<div class="wz-progress" style="margin-bottom: 24px;">';
		html += '<div class="wz-step-count">Étape 2 / 2 — terminée</div>';
		html += '<div class="wz-progress-labels">';
		html += '<div class="wz-progress-label completed">Vérification</div>';
		html += '<div class="wz-progress-label completed">Confirmation</div>';
		html += '</div>';
		html += '<div class="wz-progress-steps">';
		html += '<div class="wz-progress-step completed"></div>';
		html += '<div class="wz-progress-step completed"></div>';
		html += '</div>';
		html += '</div>';
		html += '<h2 class="wz-title">Réinscription réussie !</h2>';
		html += '<p class="wz-subtitle-text">Votre demande a été validée avec succès.</p>';
		html += '</div>';

		html += '<div style="text-align: center; margin-bottom: 28px;">';
		html += '<div class="wz-success-icon"><svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg></div>';
		html += '<p class="wz-subtitle-text">Votre fiche de réinscription a été générée avec le statut <strong>Validée</strong>.</p>';
		html += '</div>';

		html += '<div class="wz-card">';
		html += '<div class="wz-card-header"><div class="wz-card-title">Détails de la réinscription</div></div>';
		html += '<div class="wz-card-body">';
		html += render_readonly_fields([
			{label: 'Référence', value: result.name},
			{label: 'Session', value: wizard_data.session},
			{label: 'Semestre', value: wizard_data.semestre},
			{label: 'Année académique', value: result.academic_year || '—'},
			{label: 'Niveau', value: result.niveau || student_data.niveau_actuel},
			{label: 'Filière', value: result.filiere || student_data.filiere},
			{label: 'Statut', value: '<span class="wz-badge wz-badge-ok">Validée</span>'}
		]);
		html += '</div></div>';

		html += '<div class="wz-card">';
		html += '<div class="wz-card-header"><div class="wz-card-title">Prochaines étapes</div></div>';
		html += '<div class="wz-card-body">';
		html += '<ul class="wz-next-steps">';
		html += '<li><i class="fa fa-download"></i> Téléchargez votre fiche de réinscription (PDF) depuis le bouton ci-dessous.</li>';
		html += '<li><i class="fa fa-university"></i> Présentez-vous auprès de la scolarité avec votre fiche pour faire valider votre dossier.</li>';
		html += '<li><i class="fa fa-money"></i> Règle les frais de réinscription auprès du service comptable.</li>';
		html += '<li><i class="fa fa-calendar-check-o"></i> Votre planning et votre emploi du temps seront disponibles après confirmation.</li>';
		html += '</ul>';
		html += '</div></div>';

		html += '<div class="wz-actions">';
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

	function session_academic_year(session_name) {
		var found = null;
		(wizard_data._sessions || []).forEach(function(s) {
			if (s.name === session_name) found = s;
		});
		return found ? found.academic_year : null;
	}

	function format_note(note) {
		var n = parseFloat(note);
		if (isNaN(n)) return '' + note;
		return n.toFixed(2).replace('.', ',');
	}

	function esc(value) {
		if (value === null || value === undefined) return '';
		return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
	}

	function render_wizard_header(step, title, subtitle) {
		var steps = [
			{num: 1, label: 'Vérification'},
			{num: 2, label: 'Confirmation'}
		];

		var html = '<div style="margin-bottom: 32px;">';
		html += '<div class="wz-progress" style="margin-bottom: 24px;">';
		html += '<div class="wz-step-count">Étape ' + step + ' / 2</div>';
		html += '<div class="wz-progress-labels">';
		steps.forEach(function(s, i) {
			var cls = i + 1 < step ? 'completed' : (i + 1 === step ? 'active' : '');
			html += '<div class="wz-progress-label ' + cls + '">' + s.label + '</div>';
		});
		html += '</div>';
		html += '<div class="wz-progress-steps">';
		steps.forEach(function(s, i) {
			var cls = 'wz-progress-step';
			if (i + 1 < step) cls += ' completed';
			else if (i + 1 === step) cls += ' active';
			html += '<div class="' + cls + '"></div>';
		});
		html += '</div>';
		html += '</div>';
		html += '<h2 class="wz-title">' + title + '</h2>';
		html += '<p class="wz-subtitle-text">' + subtitle + '</p>';
		html += '</div>';
		return html;
	}

	function render_wizard_footer(buttons) {
		var html = '<div class="wz-footer">';
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
			html += '<td class="label" style="width: 220px; font-weight: 600; padding: 10px 12px; font-size: 13px; vertical-align: top;">' + f.label + '</td>';
			html += '<td style="padding: 10px 12px; font-size: 14px;">' + f.value + '</td>';
			html += '</tr>';
		});
		html += '</table>';
		return html;
	}
};