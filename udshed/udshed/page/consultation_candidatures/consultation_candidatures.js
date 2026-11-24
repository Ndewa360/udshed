frappe.pages['consultation-candidatures'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Consultation des candidatures'),
		single_column: true
	});

	var API = 'udshed.udshed.doctype.session_inscription_candidate.session_inscription_candidate.';

	var state = {
		filters: { session: null, filiere: null, niveau: null, centre: null, statut: null },
		stats: {},
		candidates: [],
		total: 0,
		page_num: 0,
		per_page: 20,
		selected_doc: null
	};

	var STYLES = `
		.cc-page { max-width: 1100px; margin: 0 auto; padding: 8px 0 40px; }
		.cc-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 20px; }
		.cc-stat-card { background: #fff; border: 1px solid #e2e4e9; border-radius: 10px; padding: 16px 20px; text-align: center; cursor: pointer; transition: border-color 0.2s; }
		.cc-stat-card:hover { border-color: #1e2025; }
		.cc-stat-card.active { border-color: #1e2025; box-shadow: 0 0 0 1px #1e2025; }
		.cc-stat-num { font-size: 28px; font-weight: 700; color: #1e2025; }
		.cc-stat-label { font-size: 12px; color: #6b6d7a; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
		.cc-filters { background: #fff; border: 1px solid #e2e4e9; border-radius: 10px; padding: 16px 20px; margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
		.cc-filters .filter-group { flex: 1; min-width: 160px; }
		.cc-filters label { display: block; font-size: 11px; color: #6b6d7a; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }
		.cc-table-wrap { background: #fff; border: 1px solid #e2e4e9; border-radius: 10px; overflow: hidden; }
		.cc-table { width: 100%; border-collapse: collapse; }
		.cc-table th { background: #f5f6f8; font-size: 11px; color: #6b6d7a; text-transform: uppercase; letter-spacing: 0.05em; padding: 10px 16px; text-align: left; border-bottom: 1px solid #e2e4e9; }
		.cc-table td { padding: 12px 16px; font-size: 13px; color: #3c3e44; border-bottom: 1px solid #f0f1f3; }
		.cc-table tr:hover td { background: #fafbfc; }
		.cc-badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
		.cc-badge-waiting { background: #fff3cd; color: #856404; }
		.cc-badge-review { background: #cce5ff; color: #004085; }
		.cc-badge-accepted { background: #d4edda; color: #155724; }
		.cc-badge-rejected { background: #f8d7da; color: #721c24; }
		.cc-badge-enrolled { background: #d1ecf1; color: #0c5460; }
		.cc-btn-view { background: none; border: 1px solid #e2e4e9; border-radius: 6px; padding: 4px 12px; font-size: 12px; cursor: pointer; color: #1e2025; }
		.cc-btn-view:hover { background: #f5f6f8; }
		.cc-pagination { display: flex; justify-content: center; align-items: center; gap: 12px; padding: 16px; }
		.cc-pagination button { background: none; border: 1px solid #e2e4e9; border-radius: 6px; padding: 6px 16px; font-size: 13px; cursor: pointer; }
		.cc-pagination button:hover:not(:disabled) { background: #f5f6f8; }
		.cc-pagination button:disabled { opacity: 0.4; cursor: default; }
		.cc-empty { text-align: center; padding: 48px; color: #6b6d7a; }
		.cc-modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 1000; display: flex; align-items: flex-start; justify-content: center; padding-top: 40px; }
		.cc-modal { background: #fff; border-radius: 12px; width: 720px; max-width: 95vw; max-height: 85vh; overflow-y: auto; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
		.cc-modal-header { display: flex; justify-content: space-between; align-items: center; padding: 20px 24px; border-bottom: 1px solid #e2e4e9; position: sticky; top: 0; background: #fff; z-index: 1; }
		.cc-modal-header h3 { margin: 0; font-size: 16px; color: #1e2025; }
		.cc-modal-close { background: none; border: none; font-size: 20px; cursor: pointer; color: #6b6d7a; padding: 4px; }
		.cc-modal-body { padding: 24px; }
		.cc-detail-section { margin-bottom: 20px; }
		.cc-detail-section h4 { font-size: 13px; color: #6b6d7a; text-transform: uppercase; letter-spacing: 0.05em; margin: 0 0 10px 0; padding-bottom: 6px; border-bottom: 1px solid #f0f1f3; }
		.cc-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 24px; font-size: 13px; }
		.cc-detail-grid .label { color: #6b6d7a; }
		.cc-detail-grid .value { color: #1e2025; font-weight: 500; }
		.cc-modal-actions { display: flex; gap: 8px; flex-wrap: wrap; padding: 16px 24px; border-top: 1px solid #e2e4e9; }
		.cc-modal-actions button { padding: 8px 16px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; border: 1px solid #e2e4e9; }
		.cc-action-review { background: #cce5ff; color: #004085; border-color: #b8daff !important; }
		.cc-action-accept { background: #d4edda; color: #155724; border-color: #c3e6cb !important; }
		.cc-action-reject { background: #f8d7da; color: #721c24; border-color: #f5c6cb !important; }
		.cc-action-validate { background: #1e2025; color: #fff; border-color: #1e2025 !important; }
	`;

	$(page.body).append('<style>' + STYLES + '</style>');

	var $page = $('<div class="cc-page"></div>');
	$(page.body).append($page);

	$page.html(`
		<div class="cc-stats" id="cc-stats"></div>
		<div class="cc-filters" id="cc-filters"></div>
		<div class="cc-table-wrap">
			<table class="cc-table">
				<thead>
					<tr>
						<th>N° Dossier</th>
						<th>Session</th>
						<th>Nom complet</th>
						<th>Filière</th>
						<th>Niveau</th>
						<th>Centre</th>
						<th>Date</th>
						<th>Statut</th>
						<th>Action</th>
					</tr>
				</thead>
				<tbody id="cc-list"></tbody>
			</table>
			<div id="cc-empty" class="cc-empty" style="display:none;">Aucune candidature trouvée.</div>
			<div class="cc-pagination" id="cc-pagination"></div>
		</div>
		<div id="cc-modal-slot"></div>
	`);

	// ─── Filtres ────────────────────────────────────────────────
	function render_filters() {
		var $f = $page.find('#cc-filters');
		$f.html(`
			<div class="filter-group">
				<label>Session</label>
				<div id="cc-f-session"></div>
			</div>
			<div class="filter-group">
				<label>Filière</label>
				<div id="cc-f-filiere"></div>
			</div>
			<div class="filter-group">
				<label>Niveau</label>
				<div id="cc-f-niveau"></div>
			</div>
			<div class="filter-group">
				<label>Centre</label>
				<div id="cc-f-centre"></div>
			</div>
			<div class="filter-group">
				<label>Statut</label>
				<div id="cc-f-statut"></div>
			</div>
			<div class="filter-group" style="flex:0;">
				<label>&nbsp;</label>
				<button class="btn btn-primary btn-sm" id="cc-btn-search">Rechercher</button>
			</div>
		`);

		frappe.ui.form.make_control({
			df: { fieldtype: 'Link', options: 'Session Inscription', fieldname: 'session', placeholder: 'Toutes' },
			parent: $f.find('#cc-f-session')
		}).refresh();

		frappe.ui.form.make_control({
			df: { fieldtype: 'Link', options: 'Field of study', fieldname: 'filiere', placeholder: 'Toutes' },
			parent: $f.find('#cc-f-filiere')
		}).refresh();

		var $niveau = $('<select class="form-control form-control-sm" style="font-size:13px;"><option value="">Tous</option><option>BTS</option><option>LICENCE 1</option><option>LICENCE 2</option><option>LICENCE 3</option><option>MASTER 1</option><option>MASTER 2</option></select>');
		$f.find('#cc-f-niveau').append($niveau);

		var $centre = $('<select class="form-control form-control-sm" style="font-size:13px;"><option value="">Tous</option><option>Bangangté</option><option>Bafoussam</option><option>Yaoundé</option><option>Douala</option></select>');
		$f.find('#cc-f-centre').append($centre);

		var $statut = $('<select class="form-control form-control-sm" style="font-size:13px;"><option value="">Tous</option><option>En attente</option><option>Dossier en cours d\'examen</option><option>Accepté</option><option>Refusé</option><option>Inscrit</option></select>');
		$f.find('#cc-f-statut').append($statut);

		$f.find('#cc-btn-search').on('click', function () {
			state.filters.session = $f.find('[data-fieldname="session"]').val() || null;
			state.filters.filiere = $f.find('[data-fieldname="filiere"]').val() || null;
			state.filters.niveau = $niveau.val() || null;
			state.filters.centre = $centre.val() || null;
			state.filters.statut = $statut.val() || null;
			state.page_num = 0;
			load_stats();
			load_list();
		});
	}

	// ─── Stats ──────────────────────────────────────────────────
	function load_stats() {
		var args = Object.assign({}, state.filters);
		frappe.call({
			method: 'api/method/' + API + 'get_candidate_dashboard_stats',
			args: args,
			callback: function (r) {
				if (r && r.message) {
					state.stats = r.message;
					render_stats();
				}
			}
		});
	}

	function render_stats() {
		var s = state.stats;
		var items = [
			{ key: 'total', label: 'Total', color: '#1e2025' },
			{ key: 'en_attente', label: 'En attente', color: '#856404', bg: '#fff3cd', statut: 'En attente' },
			{ key: 'en_cours', label: 'En cours', color: '#004085', bg: '#cce5ff', statut: 'Dossier en cours d\'examen' },
			{ key: 'accepte', label: 'Acceptées', color: '#155724', bg: '#d4edda', statut: 'Accepté' },
			{ key: 'refuse', label: 'Refusées', color: '#721c24', bg: '#f8d7da', statut: 'Refusé' },
			{ key: 'inscrit', label: 'Inscrites', color: '#0c5460', bg: '#d1ecf1', statut: 'Inscrit' }
		];
		var html = items.map(function (it) {
			var active = (state.filters.statut === it.statut) ? ' active' : '';
			return '<div class="cc-stat-card' + active + '" data-statut="' + (it.statut || '') + '">'
				+ '<div class="cc-stat-num" style="color:' + it.color + ';">' + (s[it.key] || 0) + '</div>'
				+ '<div class="cc-stat-label">' + it.label + '</div>'
				+ '</div>';
		}).join('');
		$page.find('#cc-stats').html(html);

		$page.find('.cc-stat-card').on('click', function () {
			var st = $(this).data('statut');
			if (state.filters.statut === st) {
				state.filters.statut = null;
			} else {
				state.filters.statut = st || null;
			}
			state.page_num = 0;
			render_stats();
			load_list();
		});
	}

	// ─── Liste ──────────────────────────────────────────────────
	function load_list() {
		var args = Object.assign({}, state.filters, {
			start: state.page_num * state.per_page,
			limit: state.per_page
		});
		frappe.call({
			method: 'api/method/' + API + 'get_candidates_list',
			args: args,
			callback: function (r) {
				if (r && r.message) {
					state.candidates = r.message.candidates || [];
					state.total = r.message.total || 0;
					render_list();
				}
			}
		});
	}

	function badge_class(statut) {
		switch (statut) {
			case 'En attente': return 'cc-badge-waiting';
			case 'Dossier en cours d\'examen': return 'cc-badge-review';
			case 'Accepté': return 'cc-badge-accepted';
			case 'Refusé': return 'cc-badge-rejected';
			case 'Inscrit': return 'cc-badge-enrolled';
			default: return '';
		}
	}

	function render_list() {
		var $tbody = $page.find('#cc-list');
		var $empty = $page.find('#cc-empty');

		if (!state.candidates.length) {
			$tbody.empty();
			$empty.show();
		} else {
			$empty.hide();
			var html = '';
			var current_session = null;
			state.candidates.forEach(function (c) {
				if (c.session_inscription !== current_session) {
					current_session = c.session_inscription;
					html += '<tr style="background:#eef1f5;">'
						+ '<td colspan="9" style="padding:8px 16px;font-weight:700;color:#1e2025;font-size:12px;text-transform:uppercase;letter-spacing:0.05em;">'
						+ '📁 ' + frappe.utils.escape_html(c.session_label || c.session_inscription || 'Sans session')
						+ '</td></tr>';
				}
				html += '<tr>'
					+ '<td><strong>' + frappe.utils.escape_html(c.name) + '</strong></td>'
					+ '<td style="color:#6b6d7a;">' + frappe.utils.escape_html(c.session_label || '') + '</td>'
					+ '<td>' + frappe.utils.escape_html(c.last_name + ' ' + c.first_name) + '</td>'
					+ '<td>' + frappe.utils.escape_html(c.filiere_label || '') + '</td>'
					+ '<td>' + frappe.utils.escape_html(c.niveau || '') + '</td>'
					+ '<td>' + frappe.utils.escape_html(c.examination_centre || '') + '</td>'
					+ '<td>' + frappe.utils.escape_html(c.submitted_on || '') + '</td>'
					+ '<td><span class="cc-badge ' + badge_class(c.candidature_status) + '">'
					+ frappe.utils.escape_html(c.candidature_status || '') + '</span></td>'
					+ '<td><button class="cc-btn-view" data-name="' + frappe.utils.escape_html(c.name) + '">Voir</button></td>'
					+ '</tr>';
			});
			$tbody.html(html);
		}

		// Pagination
		var total_pages = Math.ceil(state.total / state.per_page);
		var $pag = $page.find('#cc-pagination');
		if (total_pages <= 1) { $pag.empty(); return; }
		$pag.html(
			'<button class="cc-prev" ' + (state.page_num === 0 ? 'disabled' : '') + '>&larr; Précédent</button>'
			+ '<span>Page ' + (state.page_num + 1) + ' / ' + total_pages + '</span>'
			+ '<button class="cc-next" ' + (state.page_num >= total_pages - 1 ? 'disabled' : '') + '>Suivant &rarr;</button>'
		);
		$pag.find('.cc-prev').on('click', function () { state.page_num--; load_list(); });
		$pag.find('.cc-next').on('click', function () { state.page_num++; load_list(); });

		// Clic Voir
		$tbody.find('.cc-btn-view').on('click', function () {
			open_detail($(this).data('name'));
		});
	}

	// ─── Détail (modal) ─────────────────────────────────────────
	function open_detail(name) {
		frappe.call({
			method: 'api/method/' + API + 'get_candidate_detail',
			args: { name: name },
			callback: function (r) {
				if (r && r.message) {
					state.selected_doc = r.message;
					render_modal(r.message);
				}
			}
		});
	}

	function render_modal(d) {
		var choix_html = (d.choix_de_formation || []).map(function (c) {
			return '<div style="padding:4px 0;">' + frappe.utils.escape_html(c.choix) + ' — <strong>'
				+ frappe.utils.escape_html(c.filiere) + '</strong> (' + frappe.utils.escape_html(c.niveau) + ')</div>';
		}).join('') || '<span style="color:#6b6d7a;">Aucun choix</span>';

		var diplomes_html = (d.diplome_formation || []).map(function (dp) {
			return '<div style="padding:4px 0;">' + frappe.utils.escape_html(dp.diplome) + ' — '
				+ frappe.utils.escape_html(dp.year || '') + ' — '
				+ frappe.utils.escape_html(dp.serie || '') + ' — '
				+ frappe.utils.escape_html(dp.mention || '') + '</div>';
		}).join('') || '<span style="color:#6b6d7a;">Aucun diplôme renseigné</span>';

		var docs_html = '';
		if (d.birth_certificate) docs_html += '<a href="' + d.birth_certificate + '" target="_blank" class="btn btn-sm btn-outline-secondary">Acte de naissance</a> ';
		if (d.access_diploma_copy) docs_html += '<a href="' + d.access_diploma_copy + '" target="_blank" class="btn btn-sm btn-outline-secondary">Diplôme</a> ';
		if (d.id_photo) docs_html += '<a href="' + d.id_photo + '" target="_blank" class="btn btn-sm btn-outline-secondary">Photo</a> ';
		if (d.remittance_receipt) docs_html += '<a href="' + d.remittance_receipt + '" target="_blank" class="btn btn-sm btn-outline-secondary">Reçu</a> ';
		if (!docs_html) docs_html = '<span style="color:#6b6d7a;">Aucun document</span>';

		var modal_html = `
			<div class="cc-modal-overlay" id="cc-modal">
				<div class="cc-modal">
					<div class="cc-modal-header">
						<h3>Dossier ${frappe.utils.escape_html(d.name)}</h3>
						<button class="cc-modal-close">&times;</button>
					</div>
					<div class="cc-modal-body">

						<div class="cc-detail-section">
							<h4>Choix de formation</h4>
							${choix_html}
						</div>

						<div class="cc-detail-section">
							<h4>Informations personnelles</h4>
							<div class="cc-detail-grid">
								<div><span class="label">Nom complet</span></div>
								<div><span class="value">${frappe.utils.escape_html(d.last_name + ' ' + d.first_name)}</span></div>
								<div><span class="label">Date de naissance</span></div>
								<div><span class="value">${frappe.utils.escape_html(d.birthdate)}</span></div>
								<div><span class="label">Lieu de naissance</span></div>
								<div><span class="value">${frappe.utils.escape_html(d.birth_place)}</span></div>
								<div><span class="label">Sexe</span></div>
								<div><span class="value">${frappe.utils.escape_html(d.sexe)}</span></div>
								<div><span class="label">Téléphone</span></div>
								<div><span class="value">${frappe.utils.escape_html(d.phone)}</span></div>
								<div><span class="label">Email</span></div>
								<div><span class="value">${frappe.utils.escape_html(d.email)}</span></div>
								<div><span class="label">Contact parent</span></div>
								<div><span class="value">${frappe.utils.escape_html(d.parent_phone)}</span></div>
								<div><span class="label">Filière</span></div>
								<div><span class="value">${frappe.utils.escape_html(d.filiere_label || d.filiere)}</span></div>
								<div><span class="label">Niveau</span></div>
								<div><span class="value">${frappe.utils.escape_html(d.niveau)}</span></div>
								<div><span class="label">Centre d'examen</span></div>
								<div><span class="value">${frappe.utils.escape_html(d.examination_centre)}</span></div>
								<div><span class="label">Date de soumission</span></div>
								<div><span class="value">${frappe.utils.escape_html(d.submitted_on)}</span></div>
							</div>
						</div>

						<div class="cc-detail-section">
							<h4>Diplômes</h4>
							${diplomes_html}
						</div>

						<div class="cc-detail-section">
							<h4>Documents</h4>
							<div style="display:flex;gap:8px;flex-wrap:wrap;">${docs_html}</div>
						</div>

						<div class="cc-detail-section">
							<h4>Statut</h4>
							<div><span class="cc-badge ${badge_class(d.candidature_status)}">${frappe.utils.escape_html(d.candidature_status)}</span></div>
							${d.status_comment ? '<div style="margin-top:8px;font-size:13px;color:#3c3e44;"><strong>Observation :</strong> ' + frappe.utils.escape_html(d.status_comment) + '</div>' : ''}
							${d.status_updated_on ? '<div style="margin-top:4px;font-size:12px;color:#6b6d7a;">Dernière mise à jour : ' + frappe.utils.escape_html(d.status_updated_on) + '</div>' : ''}
						</div>
					</div>

					<div class="cc-modal-actions">
						<button class="cc-action-review" data-status="Dossier en cours d'examen">Mettre en cours</button>
						<button class="cc-action-accept" data-status="Accepté">Accepter</button>
						<button class="cc-action-reject" data-status="Refusé">Rejeter</button>
						<button class="cc-action-validate" data-status="Inscrit">Valider l'inscription</button>
					</div>
				</div>
			</div>
		`;

		$page.find('#cc-modal-slot').html(modal_html);

		// Close
		$page.find('#cc-modal').on('click', function (e) {
			if ($(e.target).is('.cc-modal-overlay') || $(e.target).is('.cc-modal-close')) {
				$page.find('#cc-modal-slot').empty();
			}
		});

		// Actions
		$page.find('.cc-modal-actions button').on('click', function () {
			var new_status = $(this).data('status');
			if (new_status === 'Refusé') {
				prompt_reject(d.name);
			} else if (new_status === 'Inscrit') {
				frappe.confirm(
					'Valider l\'inscription de <strong>' + frappe.utils.escape_html(d.last_name + ' ' + d.first_name) + '</strong> ?',
					function () {
						call_update_status(d.name, new_status, null);
					}
				);
			} else {
				frappe.confirm(
					'Mettre le statut à <strong>' + new_status + '</strong> ?',
					function () {
						call_update_status(d.name, new_status, null);
					}
				);
			}
		});
	}

	function prompt_reject(doc_name) {
		var d = new frappe.ui.Dialog({
			title: 'Motif du rejet',
			fields: [
				{
					fieldname: 'reason',
					fieldtype: 'Small Text',
					label: 'Motif du rejet',
					reqd: 1
				}
			],
			primary_action_label: 'Rejeter',
			primary_action: function (values) {
				d.hide();
				call_update_status(doc_name, 'Refusé', values.reason);
			}
		});
		d.show();
	}

	function call_update_status(doc_name, new_status, comment) {
		frappe.call({
			method: 'api/method/' + API + 'update_candidate_status',
			args: { name: doc_name, new_status: new_status, comment: comment },
			callback: function (r) {
				if (r && r.message && r.message.ok) {
					frappe.show_alert({ message: 'Statut mis à jour : ' + new_status, indicator: 'green' });
					$page.find('#cc-modal-slot').empty();
					load_stats();
					load_list();
				}
			}
		});
	}

	// ─── Init ───────────────────────────────────────────────────
	render_filters();
	load_stats();
	load_list();
};
