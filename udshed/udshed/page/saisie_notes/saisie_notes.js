frappe.pages['saisie_notes'].on_page_load = function (wrapper) {
	frappe.require('/assets/udshed/css/saisie_notes.css').then(() => {
		init_page(wrapper);
	});
};

function init_page(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Saisie des notes'),
		single_column: true
	});

	// ------------------------------------------------------------------ //
	//  État de la page
	// ------------------------------------------------------------------ //
	var state = {
		academic_year: null,
		filiere: null,
		filiere_label: '',
		niveau: null,
		semestre: 'Semestre 1',
		teaching_unit: null,
		teacher: null,
		teacher_name: '',
		role: 'Administrator',
		is_teacher: false,
		session: 'Normale',
		no_ues: false,
		data: null,
		cc_columns: [],
		active_tab: 'cc',
		edits: {},
		dirty: false,
		loading: false
	};

	// ------------------------------------------------------------------ //
	//  Définition des onglets (dépend du mode de session)
	// ------------------------------------------------------------------ //
	var TAB_DEFS = {
		cc: { key: 'cc', tab: 'CC', label: __('Notes de CC'), icon: 'fa-solid fa-list-check', session: 'cc' },
		examen: { key: 'examen', tab: 'Examen', label: __("Notes d'examen"), icon: 'fa-solid fa-file-pen', session: 'normale' },
		tp: { key: 'tp', tab: 'TP', label: __('Notes de TP'), icon: 'fa-solid fa-flask', session: 'normale' },
		rattrapage: { key: 'rattrapage', tab: 'Rattrapage', label: __('Notes de rattrapage'), icon: 'fa-solid fa-rotate-right', session: 'rattrapage' }
	};

	var TAB_META = {
		cc: {
			title: __('Notes de contrôle continu (CC)'),
			desc: __('Vous pouvez saisir plusieurs notes de contrôle continu. Les notes sont exprimées sur 20.'),
			action: 'cc'
		},
		examen: {
			title: __("Notes d'examen"),
			desc: __("Saisissez la note de l'examen de session normale sur 20. Une seule note est autorisée."),
			action: 'examen'
		},
		tp: {
			title: __('Notes de TP'),
			desc: __('Saisissez la note de travaux pratiques sur 20.'),
			action: 'tp'
		},
		rattrapage: {
			title: __('Notes de rattrapage'),
			desc: __("La note retenue est automatiquement la meilleure entre la note d'examen initiale et la note de rattrapage. Les deux notes sont conservées."),
			action: 'rattrapage'
		}
	};

	function has_tp() {
		var type_ue = state.data && state.data.ue_info && state.data.ue_info.type_ue;
		return type_ue === 'Avec TP';
	}

	function get_tabs() {
		if (state.session === 'Rattrapage') {
			return [TAB_DEFS.rattrapage];
		}
		var tabs = [TAB_DEFS.cc, TAB_DEFS.examen];
		if (has_tp()) tabs.push(TAB_DEFS.tp);
		return tabs;
	}

	function get_tab() {
		var tabs = get_tabs();
		var t = tabs.find(function (x) { return x.key === state.active_tab; });
		return t || tabs[0];
	}

	function active_session() {
		if (!state.data) return null;
		return state.data.sessions[get_tab().session] || null;
	}

	// ------------------------------------------------------------------ //
	//  Conteneur principal
	// ------------------------------------------------------------------ //
	var body = $('<div class="sn-wrapper"></div>');
	$(page.body).append(body);

	body.append(`
		<header class="sn-hero">
			<div class="sn-hero-icon"><i class="fa-solid fa-pen-to-square"></i></div>
			<div class="sn-hero-titles">
				<h2 class="sn-hero-title">${__('Saisie des notes')}</h2>
				<p class="sn-hero-subtitle">${__('Enregistrez les notes.')}</p>
			</div>
			<button class="btn btn-sm sn-btn sn-config" title="${__('Configurer la formule de calcul et la grille des grades')}">
				<i class="fa-solid fa-gear"></i><span>${__('Configuration')}</span>
			</button>
		</header>
	`);

	body.on('click.sn', '.sn-config', function () {
		frappe.set_route('Form', 'Udshed Setting');
	});

	// ------------------------------------------------------------------ //
	//  Barre de filtres
	// ------------------------------------------------------------------ //
	var filters_container = $('<div class="card sn-filters-card"><div class="sn-filters-grid"></div></div>');
	body.append(filters_container);
	var filters_grid = filters_container.find('.sn-filters-grid');

	function make_control(df) {
		var control = frappe.ui.form.make_control({ df: df, parent: filters_grid });
		control.refresh();
		return control;
	}

	var f_academic_year = make_control({
		fieldname: 'academic_year',
		fieldtype: 'Link',
		label: __('Année académique'),
		options: 'Academic Year',
		placeholder: __('Année académique'),
		change: function () {
			state.academic_year = this.get_value();
			reload_enseignants();
			reload_ues();
		}
	});

	var f_filiere = make_control({
		fieldname: 'filiere',
		fieldtype: 'Link',
		label: __('Filière'),
		options: 'Field of study',
		placeholder: __('Filière'),
		change: function () {
			state.filiere = this.get_value();
			f_niveau.set_value('');
			f_niveau.df.options = [];
			f_niveau.refresh();
			state.niveau = null;
			load_levels();
			reload_enseignants();
			reload_ues();
		}
	});

	var f_niveau = make_control({
		fieldname: 'niveau',
		fieldtype: 'Select',
		label: __('Niveau'),
		placeholder: __('Niveau'),
		change: function () {
			state.niveau = this.get_value();
			reload_enseignants();
			reload_ues();
		}
	});

	var f_semestre = make_control({
		fieldname: 'semestre',
		fieldtype: 'Select',
		label: __('Semestre'),
		options: ['Semestre 1', 'Semestre 2'],
		default: 'Semestre 1',
		change: function () {
			state.semestre = this.get_value();
			reload_enseignants();
			reload_ues();
		}
	});
	f_semestre.set_value('Semestre 1');

	var f_classe = make_control({
		fieldname: 'classe',
		fieldtype: 'Data',
		label: __('Classe'),
		placeholder: __('Automatique'),
		read_only: 1
	});

	var f_ue = make_control({
		fieldname: 'teaching_unit',
		fieldtype: 'Select',
		label: __('Unité d\'enseignement'),
		options: [],
		change: function () {
			state.teaching_unit = this.get_value();
			if (filters_ok()) {
				load_data();
			}
		}
	});

	var f_enseignant = make_control({
		fieldname: 'enseignant',
		fieldtype: 'Select',
		label: __('Enseignant'),
		options: [{ value: '', label: __('Tous les enseignants') }],
		change: function () {
			state.teacher = this.get_value() || null;
			reload_ues();
		}
	});
	$(f_enseignant.wrapper).hide();

	var f_session = make_control({
		fieldname: 'session',
		fieldtype: 'Select',
		label: __("Session d'examen"),
		options: [{ value: 'Normale', label: __('Normale') }, { value: 'Rattrapage', label: __('Rattrapage') }],
		change: function () {
			state.session = this.get_value();
			state.active_tab = get_tabs()[0].key;
			state.edits = {};
			state.dirty = false;
			render();
		}
	});
	f_session.set_value('Normale');

	// ------------------------------------------------------------------ //
	//  Gestion des filtres
	// ------------------------------------------------------------------ //
	function filters_ok() {
		return !!(state.academic_year && state.filiere && state.niveau && state.semestre && state.teaching_unit);
	}

	function update_classe() {
		var filiere = state.filiere_label || state.filiere || '';
		var niveau = state.niveau || '';
		f_classe.set_value(filiere && niveau ? filiere + ' – ' + niveau : (filiere || niveau || ''));
	}

	function load_levels() {
		if (!state.filiere) return;
		frappe.call('frappe.client.get', { doctype: 'Field of study', name: state.filiere }).then(function (r) {
			var doc = r.message;
			if (!doc) return;
			state.filiere_label = doc.name_of_field || state.filiere;
			update_classe();
			var levels = (doc.field_of_study_level || []).slice().sort(function (a, b) {
				return (a.order || 0) - (b.order || 0);
			});
			f_niveau.df.options = levels.map(function (l) { return { value: l.level, label: l.level }; });
			f_niveau.refresh();
		});
	}

	function reload_enseignants() {
		if (state.is_teacher) return;
		if (!(state.academic_year && state.filiere && state.niveau && state.semestre)) {
			f_enseignant.df.options = [{ value: '', label: __('Tous les enseignants') }];
			f_enseignant.refresh();
			return;
		}
		frappe.call('udshed.api.saisie_notes.get_enseignants', {
			academic_year: state.academic_year,
			filiere: state.filiere,
			niveau: state.niveau,
			semestre: state.semestre
		}).then(function (r) {
			var enseignants = r.message || [];
			var options = [{ value: '', label: __('Tous les enseignants') }].concat(
				enseignants.map(function (e) {
					return { value: e.name, label: (e.full_name || e.name) + ' (' + e.nb_ues + ')' };
				})
			);
			var current = state.teacher;
			f_enseignant.df.options = options;
			f_enseignant.refresh();
			if (current && enseignants.some(function (e) { return e.name === current; })) {
				f_enseignant.set_value(current);
			}
		});
	}

	function reload_ues() {
		f_ue.set_value('');
		state.teaching_unit = null;
		state.data = null;
		state.no_ues = false;
		render();
		if (!(state.academic_year && state.filiere && state.niveau && state.semestre)) {
			return;
		}
		frappe.call('udshed.api.saisie_notes.get_ues', {
			academic_year: state.academic_year,
			filiere: state.filiere,
			niveau: state.niveau,
			semestre: state.semestre,
			teacher: state.teacher || ''
		}).then(function (r) {
			var ues = r.message || [];
			f_ue.df.options = ues.map(function (u) {
				return { value: u.name, label: (u.code ? u.code + ' - ' : '') + u.intitule };
			});
			f_ue.refresh();
			if (ues.length) {
				f_ue.set_value(ues[0].name);
			} else {
				state.no_ues = true;
				render();
			}
		});
	}

	// ------------------------------------------------------------------ //
	//  Droits / contexte utilisateur
	// ------------------------------------------------------------------ //
	function apply_user_context() {
		frappe.call('udshed.api.user_data.get_user_context').then(function (r) {
			var ctx = r.message || [];
			var is_admin = ctx.some(function (c) { return c.role === 'Administrator' || c.role === 'System Manager'; });
			var is_teacher = ctx.some(function (c) { return c.role === 'Teacher'; });
			state.is_teacher = is_teacher && !is_admin;
			state.role = is_admin ? 'Administrator' : (state.is_teacher ? 'Teacher' : 'Coordonateur');

			if (state.is_teacher) {
				$(f_enseignant.wrapper).hide();
				var filieres = [];
				ctx.forEach(function (c) {
					if (c.role === 'Teacher') {
						(c.filiere || []).forEach(function (fil) { filieres.push(fil.name); });
					}
				});
				if (filieres.length) {
					f_filiere.df.get_query = function () {
						return { filters: { name: ['in', filieres] } };
					};
					f_filiere.refresh();
				}
				frappe.call('udshed.api.saisie_notes.get_enseignant_courant').then(function (res) {
					if (res.message) {
						state.teacher = res.message.name;
						state.teacher_name = res.message.full_name;
						if (state.academic_year && state.filiere && state.niveau) {
							reload_ues();
						}
					}
				});
			} else {
				$(f_enseignant.wrapper).show();
			}

			var default_ay = ctx.length && ctx[0].default_academic_year;
			if (default_ay && !state.academic_year) {
				f_academic_year.set_value(default_ay);
			}
		});
	}

	// ------------------------------------------------------------------ //
	//  Chargement des données
	// ------------------------------------------------------------------ //
	function load_data() {
		if (!filters_ok()) return Promise.resolve();
		state.loading = true;
		render();
		return frappe.call('udshed.api.saisie_notes.charger_data', {
			academic_year: state.academic_year,
			filiere: state.filiere,
			niveau: state.niveau,
			semestre: state.semestre,
			teaching_unit: state.teaching_unit
		}).then(function (r) {
			state.loading = false;
			state.data = r.message;
			state.edits = {};
			state.dirty = false;
			if (!get_tabs().some(function (t) { return t.key === state.active_tab; })) {
				state.active_tab = get_tabs()[0].key;
			}
			derive_cc_columns();
			render();
		}).catch(function () {
			state.loading = false;
			state.data = null;
			render();
		});
	}

	// ------------------------------------------------------------------ //
	//  Rendu
	// ------------------------------------------------------------------ //
	function render() {
		body.find('.sn-content').remove();
		var content = $('<div class="sn-content"></div>');
		body.append(content);

		if (state.loading) {
			content.append(`
				<div class="card sn-card">
					<div class="card-body text-center py-5">
						<i class="fa-solid fa-spinner fa-spin text-muted" style="font-size:28px;"></i>
						<div class="text-muted mt-2">${__('Chargement des étudiants…')}</div>
					</div>
				</div>`);
			return;
		}

		if (!state.data || !state.data.students) {
			render_empty(content);
			return;
		}

		render_ue_info(content);
		render_tabs(content);
		render_table_area(content);
		bind_events(content);
	}

	function render_empty(content) {
		var titre, texte;
		if (state.no_ues) {
			titre = __('Aucune unité d\'enseignement trouvée pour ces filtres.');
			texte = __('Vérifiez la filière, le niveau et le semestre sélectionnés.');
		} else if (filters_ok()) {
			titre = __('Aucun étudiant inscrit pour cette UE dans cette classe.');
			texte = __('Seuls les étudiants réinscrits (validée) et inscrits à cette unité d\'enseignement sont chargés.');
		} else {
			titre = __('Sélectionnez une année académique, une filière, un niveau, un semestre et une UE');
			texte = __('Saisie des notes de contrôle continu, d\'examen, de TP et de rattrapage.');
		}
		content.append(`
			<div class="text-center sn-empty">
				<div class="sn-empty-icon"><i class="fa-solid fa-pen-to-square"></i></div>
				<h5>${titre}</h5>
				<p class="text-muted">${texte}</p>
			</div>`);
	}

	function render_ue_info(content) {
		var ue = state.data.ue_info || {};
		var enseignants = (ue.enseignants || []).map(function (e) { return e.full_name || e.name; }).join(', ') || '-';
		var tab = get_tab();
		var session = active_session();
		var statut = session && session.statut === 'Publiée' ? __('Publiée') : __('Brouillon');
		var type_examen = state.session === 'Rattrapage' ? __('Rattrapage') : tab.label;

		content.append(`
			<div class="card sn-ue-card">
				<div class="card-body">
					<div class="sn-ue-head">
						<div class="sn-ue-titles">
							<div class="sn-ue-code">${ue.code ? frappe.utils.escape_html(ue.code) : ''}</div>
							<h4 class="sn-ue-name">${frappe.utils.escape_html(ue.intitule || ue.name || '')}</h4>
							<div class="sn-ue-type">${frappe.utils.escape_html(ue.type_ue || '')}</div>
						</div>
						<div class="sn-ue-stats">
							<div class="sn-stat"><span class="sn-stat-label">${__('Crédits')}</span><span class="sn-stat-value">${ue.credits != null ? ue.credits : '-'}</span></div>
							<div class="sn-stat"><span class="sn-stat-label">${__('Étudiants')}</span><span class="sn-stat-value">${state.data.students.length}</span></div>
							<div class="sn-stat"><span class="sn-stat-label">${__('Type d\'examen')}</span><span class="sn-stat-value">${frappe.utils.escape_html(type_examen)}</span></div>
							<div class="sn-stat"><span class="sn-stat-label">${__('Session')}</span><span class="sn-stat-value sn-stat-${session && session.statut === 'Publiée' ? 'published' : 'draft'}">${statut}</span></div>
						</div>
					</div>
					<div class="sn-ue-meta">
						<span><i class="fa-solid fa-user-tie"></i> ${__('Enseignant(s)')} : <b>${frappe.utils.escape_html(enseignants)}</b></span>
						<span><i class="fa-solid fa-layer-group"></i> ${__('Classe')} : <b>${frappe.utils.escape_html((state.filiere_label || state.filiere) + ' – ' + (state.niveau || ''))}</b></span>
					</div>
				</div>
			</div>`);
	}

	function render_tabs(content) {
		var html = '<div class="sn-tabs">';
		get_tabs().forEach(function (t) {
			var active = t.key === state.active_tab ? ' active' : '';
			html += `<button class="sn-tab${active}" data-tab="${t.key}"><i class="${t.icon}"></i>${t.label}</button>`;
		});
		html += '</div>';
		content.append(html);
	}

	function render_table_area(content) {
		var session = active_session();
		var published = session && session.statut === 'Publiée';
		var students = state.data.students || [];
		var tab = get_tab();
		var meta = TAB_META[tab.key];

		var actions = `
			<button class="btn btn-light btn-sm sn-btn sn-import" title="${__('Importer')}"><i class="fa-solid fa-file-import"></i><span>${__('Importer')}</span></button>
			<button class="btn btn-light btn-sm sn-btn sn-export" title="${__('Exporter')}"><i class="fa-solid fa-file-export"></i><span>${__('Exporter')}</span></button>
			<button class="btn btn-light btn-sm sn-btn sn-modele" title="${__('Télécharger le modèle PDF')}"><i class="fa-solid fa-file-pdf"></i><span>${__('Modèle PDF')}</span></button>`;
		if (tab.key === 'cc' && !published) {
			actions += `<button class="btn btn-light btn-sm sn-btn sn-add-cc" title="${__('Ajouter un CC')}"><i class="fa-solid fa-plus"></i><span>${__('Ajouter un CC')}</span></button>`;
		}
		actions += `<button class="btn btn-primary btn-sm sn-btn sn-save${published ? ' disabled' : ''}" ${published ? 'disabled' : ''} title="${__('Enregistrer')}"><i class="fa-solid fa-floppy-disk"></i><span>${__('Enregistrer')}</span></button>`;

		content.append(`
			<div class="card sn-toolbar-card">
				<div class="card-body sn-toolbar">
					<div class="sn-toolbar-text">
						<h5 class="sn-toolbar-title">${meta.title}</h5>
						<p class="sn-toolbar-desc">${meta.desc}</p>
					</div>
					<div class="sn-toolbar-actions">${actions}</div>
				</div>
			</div>
			<div class="sn-table-slot"></div>
			<div class="sn-footer-slot"></div>
		`);

		if (!students.length) {
			content.find('.sn-table-slot').append(`
				<div class="card sn-card"><div class="card-body text-center text-muted">${__('Aucun étudiant inscrit pour cette UE dans cette classe.')}</div></div>`);
			render_footer(content);
			return;
		}

		content.find('.sn-table-slot').append(build_table(students, tab, published));
		render_footer(content);
	}

	function build_thead(tab) {
		var cols = `<th class="sn-th-matricule">${__('Matricule')}</th>
			<th class="sn-th-nom">${__('Nom')}</th>
			<th class="sn-th-prenom">${__('Prénom')}</th>`;

		if (tab.tab === 'CC') {
			cols += `<th class="sn-th-credit">${__('Crédit')}</th>`;
			state.cc_columns.forEach(function (c) {
				var label = frappe.utils.escape_html(c.label);
				cols += `<th class="sn-cc-col">
					<div class="sn-cc-head">
						<span class="sn-cc-label" title="${label}">${label}</span>
						<input type="number" step="0.1" min="0" max="20" class="form-control sn-cc-w-input" data-label="${label}" value="${c.weight || 1}" title="${__('Coefficient')}">
						<button class="btn btn-xs sn-remove-cc" data-label="${label}" title="${__('Supprimer')}"><i class="fa-solid fa-xmark"></i></button>
					</div>
				</th>`;
			});
			cols += `<th class="sn-th-moyenne">${__('Moyenne CC')}</th>`;
		} else if (tab.tab === 'Examen') {
			cols += `<th class="sn-th-credit">${__('Crédit')}</th>`;
			cols += `<th class="sn-th-note">${__("Note d'examen")}</th>`;
		} else if (tab.tab === 'TP') {
			cols += `<th class="sn-th-credit">${__('Crédit')}</th>`;
			cols += `<th class="sn-th-note">${__('Note de TP')}</th>`;
		} else if (tab.tab === 'Rattrapage') {
			cols += `<th class="sn-th-note">${__("Note d'examen initiale")}</th>
				<th class="sn-th-note">${__('Note de rattrapage')}</th>
				<th class="sn-th-moyenne">${__('Note retenue')}</th>`;
		}
		return `<tr>${cols}</tr>`;
	}

	function build_table(students, tab, published) {
		var banner = published
			? `<div class="alert alert-warning mb-0 sn-lock-banner"><i class="fa-solid fa-lock mr-1"></i>${__('Cette session est publiée : les notes sont en lecture seule.')}</div>`
			: '';

		var notes = state.data.notes[tab.tab] || {};
		var tbody = '';
		students.forEach(function (s) {
			tbody += build_row(s, tab, published, notes);
		});

		return `
			<div class="card sn-table-card">
				${banner}
				<div class="sn-table-scroll">
					<table class="table table-bordered table-hover sn-table mb-0">
						<thead>${build_thead(tab)}</thead>
						<tbody>${tbody}</tbody>
					</table>
				</div>
			</div>`;
	}

	function value_from_saved(saved, label) {
		if (!saved || !saved.notes_cc) return '';
		var it = saved.notes_cc.find(function (i) { return i.cc_label === label; });
		return it && it.note_cc != null ? it.note_cc : '';
	}

	function valeur_colonne(c, saved, e) {
		return (e[c.label] !== undefined) ? e[c.label] : value_from_saved(saved, c.label);
	}

	function calculer_moyenne_cc(values) {
		var notes = values.filter(function (v) {
			return v.note !== null && v.note !== undefined && v.note !== '';
		});
		if (!notes.length) return null;
		var methode = (state.data.config && state.data.config.methode_calcul_cc) || 'Moyenne arithmétique';
		if (methode === 'Moyenne pondérée') {
			var total = 0, poids = 0;
			notes.forEach(function (v) {
				var w = parseFloat(v.weight) || 1;
				total += parseFloat(v.note) * w;
				poids += w;
			});
			return poids ? total / poids : null;
		}
		if (methode === 'Moyenne des N meilleures notes' || methode === 'N meilleures') {
			var n = state.data.config.nb_meilleures_notes_cc || 2;
			var top = notes.map(function (v) { return parseFloat(v.note); }).sort(function (a, b) { return b - a; }).slice(0, n);
			return top.reduce(function (s, x) { return s + x; }, 0) / top.length;
		}
		return notes.reduce(function (s, v) { return s + parseFloat(v.note); }, 0) / notes.length;
	}

	function calculer_moyenne_row(saved, e) {
		var values = state.cc_columns.map(function (c) {
			return {
				label: c.label,
				weight: c.weight,
				note: (function () {
					var v = valeur_colonne(c, saved, e);
					return (v === '' || v == null) ? null : parseFloat(v);
				})()
			};
		});
		return calculer_moyenne_cc(values);
	}

	function format_note(v) {
		return (v != null && v !== '') ? Number(v).toFixed(2) : '';
	}

	function build_row(s, tab, published, notes) {
		var disabled = published ? ' disabled' : '';
		var e = (state.edits[tab.key] || {})[s.student] || {};
		var saved = notes[s.student] || null;
		var credit = (state.data.ue_info && state.data.ue_info.credits != null) ? state.data.ue_info.credits : '';

		var cols = `<td class="sn-matricule">${frappe.utils.escape_html(s.matricule || '')}</td>
			<td class="sn-nom">${frappe.utils.escape_html(s.nom || '')}</td>
			<td class="sn-prenom">${frappe.utils.escape_html(s.prenom || '')}</td>`;

		if (tab.tab === 'CC') {
			cols += `<td class="sn-credit">${credit}</td>`;
			state.cc_columns.forEach(function (c) {
				var val = valeur_colonne(c, saved, e);
				cols += `<td class="sn-note-cell"><input type="number" step="0.01" min="0" max="20" class="form-control sn-note-input" data-label="${frappe.utils.escape_html(c.label)}" data-student="${s.student}" value="${frappe.utils.escape_html(val != null ? val : '')}"${disabled}></td>`;
			});
			cols += `<td class="sn-moyenne">${format_note(calculer_moyenne_row(saved, e))}</td>`;
		} else if (tab.tab === 'Examen') {
			cols += `<td class="sn-credit">${credit}</td>`;
			var ex = (e.note !== undefined) ? e.note : (saved && saved.note_examen != null ? saved.note_examen : '');
			cols += `<td class="sn-note-cell"><input type="number" step="0.01" min="0" max="20" class="form-control sn-note-input sn-simple-input" data-student="${s.student}" value="${frappe.utils.escape_html(ex != null ? ex : '')}"${disabled}></td>`;
		} else if (tab.tab === 'TP') {
			cols += `<td class="sn-credit">${credit}</td>`;
			var tp = (e.note !== undefined) ? e.note : (saved && saved.note_tp != null ? saved.note_tp : '');
			cols += `<td class="sn-note-cell"><input type="number" step="0.01" min="0" max="20" class="form-control sn-note-input sn-simple-input" data-student="${s.student}" value="${frappe.utils.escape_html(tp != null ? tp : '')}"${disabled}></td>`;
		} else if (tab.tab === 'Rattrapage') {
			cols += `<td class="sn-lecture">${format_note(saved && saved.note_examen)}</td>`;
			var rt = (e.note !== undefined) ? e.note : (saved && saved.note_examen_rattrapage != null ? saved.note_examen_rattrapage : '');
			cols += `<td class="sn-note-cell"><input type="number" step="0.01" min="0" max="20" class="form-control sn-note-input sn-simple-input" data-student="${s.student}" value="${frappe.utils.escape_html(rt != null ? rt : '')}"${disabled}></td>`;
			cols += `<td class="sn-retenue">${format_note(calculer_retenue(saved, e))}</td>`;
		}
		return `<tr data-student="${s.student}">${cols}</tr>`;
	}

	function calculer_retenue(saved, e) {
		var initiale = saved && saved.note_examen != null ? parseFloat(saved.note_examen) : null;
		var rt = (e.note !== undefined) ? e.note : (saved && saved.note_examen_rattrapage != null ? saved.note_examen_rattrapage : '');
		var rattrapage = (rt !== '' && rt != null) ? parseFloat(rt) : null;
		if (rattrapage == null) return initiale;
		if (initiale == null) return rattrapage;
		return Math.max(initiale, rattrapage);
	}

	function render_footer(content) {
		var session = active_session();
		var published = session && session.statut === 'Publiée';
		var total = state.data.students.length;
		var avec_valeur = count_rows_avec_valeur();
		var dirty_badge = state.dirty
			? `<span class="badge badge-warning ml-2"><i class="fa-solid fa-pen mr-1"></i>${__('Modifications non enregistrées')}</span>`
			: '';
		var publie_badge = published
			? `<span class="badge badge-secondary ml-2"><i class="fa-solid fa-lock mr-1"></i>${__('Publiée')}</span>`
			: '';

		var actions = '';
		if (!published) {
			actions += `<button class="btn btn-outline-danger btn-sm sn-publish"><i class="fa-solid fa-check-double mr-1"></i>${__('Publier la session')}</button>`;
		}

		content.find('.sn-footer-slot').empty().append(`
			<div class="card sn-footer-card">
				<div class="card-body d-flex align-items-center justify-content-between flex-wrap sn-footer-row">
					<div class="text-muted small">
						${__('Notes saisies :')} <b>${avec_valeur}</b> / ${total}
						${dirty_badge}${publie_badge}
					</div>
					<div class="sn-actions">${actions}</div>
				</div>
			</div>`);
	}

	function count_rows_avec_valeur() {
		var tab = get_tab();
		var notes = state.data.notes[tab.tab] || {};
		var n = 0;
		state.data.students.forEach(function (s) {
			var e = (state.edits[tab.key] || {})[s.student] || {};
			if (Object.keys(e).some(function (k) { return e[k] !== '' && e[k] != null; })) { n++; return; }
			var saved = notes[s.student];
			if (!saved) return;
			if (tab.key === 'cc') {
				if ((saved.notes_cc || []).some(function (i) { return i.note_cc != null && i.note_cc !== ''; })) n++;
			} else if (tab.key === 'examen' && saved.note_examen != null && saved.note_examen !== '') n++;
			else if (tab.key === 'tp' && saved.note_tp != null && saved.note_tp !== '') n++;
			else if (tab.key === 'rattrapage' && saved.note_examen_rattrapage != null && saved.note_examen_rattrapage !== '') n++;
		});
		return n;
	}

	function derive_cc_columns() {
		var cc = state.data.notes.CC || {};
		var labels = [];
		var weights = {};
		Object.keys(cc).forEach(function (st) {
			var n = cc[st];
			(n.notes_cc || []).forEach(function (it) {
				if (it.cc_label && labels.indexOf(it.cc_label) === -1) {
					labels.push(it.cc_label);
				}
				weights[it.cc_label] = it.cc_weight;
			});
		});
		(state.cc_columns || []).forEach(function (c) {
			if (labels.indexOf(c.label) === -1) {
				labels.push(c.label);
			}
		});
		state.cc_columns = labels.map(function (l) {
			var old = (state.cc_columns || []).find(function (c) { return c.label === l; });
			return { label: l, weight: old ? old.weight : (weights[l] || 1) };
		});
	}

	function next_cc_label() {
		var max = 0;
		state.cc_columns.forEach(function (c) {
			var m = /^CC\s?(\d+)$/.exec((c.label || '').trim());
			if (m) max = Math.max(max, parseInt(m[1], 10));
		});
		return 'CC' + (max + 1);
	}

	// ------------------------------------------------------------------ //
	//  Construction des lignes à enregistrer
	// ------------------------------------------------------------------ //
	function build_rows(tab) {
		var notes = state.data.notes[tab.tab] || {};
		var rows = [];
		state.data.students.forEach(function (s) {
			var e = (state.edits[tab.key] || {})[s.student] || {};
			var has_new = Object.keys(e).some(function (k) { return e[k] !== '' && e[k] != null; });
			var saved = notes[s.student] || null;
			var has_old = !!saved;
			if (!has_new && !has_old) return;

			if (tab.key === 'cc') {
				var items = state.cc_columns.map(function (c) {
					var v = valeur_colonne(c, saved, e);
					return {
						cc_label: c.label,
						cc_weight: c.weight,
						note_cc: (v !== '' && v != null) ? parseFloat(v) : null
					};
				});
				rows.push({ student: s.student, notes_cc: items });
			} else {
				var champ = { examen: 'note_examen', tp: 'note_tp', rattrapage: 'note_examen_rattrapage' }[tab.key];
				var row = { student: s.student };
				row[champ] = (e.note !== undefined && e.note !== '')
					? parseFloat(e.note)
					: (saved && saved[champ] != null ? saved[champ] : null);
				rows.push(row);
			}
		});
		return rows;
	}

	function valider_saisie(rows) {
		var erreurs = [];
		var vus = {};
		function check(valeur, contexte) {
			if (valeur === '' || valeur == null) return;
			var n = parseFloat(valeur);
			if (isNaN(n)) {
				erreurs.push(__('Note invalide dans {0}.', [contexte]));
			} else if (n < 0) {
				erreurs.push(__('Note négative ({0}) dans {1}.', [n, contexte]));
			} else if (n > 20) {
				erreurs.push(__('Note {0} supérieure à 20 dans {1}.', [n, contexte]));
			}
		}
		rows.forEach(function (row) {
			var st = row.student;
			if (vus[st]) {
				erreurs.push(__('Ligne en double pour l\'étudiant {0}.', [st]));
			}
			vus[st] = true;
			if (row.notes_cc) {
				row.notes_cc.forEach(function (it) {
					check(it.note_cc, __('CC {0}', [it.cc_label]));
				});
			}
			['note_examen', 'note_tp', 'note_examen_rattrapage'].forEach(function (k) {
				if (row[k] !== undefined) check(row[k], k.replace(/_/g, ' '));
			});
		});
		return erreurs;
	}

	// ------------------------------------------------------------------ //
	//  Actions
	// ------------------------------------------------------------------ //
	function enregistrer() {
		var tab = get_tab();
		if (active_session() && active_session().statut === 'Publiée') {
			frappe.msgprint(__('Cette session est publiée : les notes sont en lecture seule.'));
			return;
		}
		var rows = build_rows(tab);
		if (!rows.length) {
			frappe.msgprint(__('Aucune note à enregistrer.'));
			return;
		}
		var erreurs = valider_saisie(rows);
		if (erreurs.length) {
			frappe.msgprint(erreurs.map(function (e) { return '- ' + e; }).join('<br>'), __('Validation des notes'));
			return;
		}
		var method = {
			cc: 'enregistrer_cc',
			examen: 'enregistrer_examen',
			tp: 'enregistrer_tp',
			rattrapage: 'enregistrer_rattrapage'
		}[tab.key];
		frappe.call('udshed.api.saisie_notes.' + method, {
			academic_year: state.academic_year,
			filiere: state.filiere,
			niveau: state.niveau,
			semestre: state.semestre,
			teaching_unit: state.teaching_unit,
			rows: rows
		}).then(function (r) {
			frappe.show_alert({ message: __('Notes enregistrées ({0}).', [r.message.saved]), indicator: 'green' });
			return load_data();
		});
	}

	function ajouter_cc() {
		var label = next_cc_label();
		state.cc_columns.push({ label: label, weight: 1 });
		state.dirty = true;
		render();
	}

	function supprimer_cc(label) {
		var col = state.cc_columns.find(function (c) { return c.label === label; });
		if (!col) return;

		var cc = state.data.notes.CC || {};
		var a_des_valeurs = Object.keys(cc).some(function (st) {
			return (cc[st].notes_cc || []).some(function (it) {
				return it.cc_label === label && it.note_cc != null && it.note_cc !== '';
			});
		});
		var a_editions = Object.keys(state.edits.cc || {}).some(function (st) {
			return (state.edits.cc[st][label] !== undefined && state.edits.cc[st][label] !== '');
		});

		function do_remove() {
			state.cc_columns = state.cc_columns.filter(function (c) { return c.label !== label; });
			Object.keys(state.edits.cc || {}).forEach(function (st) {
				delete state.edits.cc[st][label];
			});
			state.dirty = true;
			render();
		}

		if (a_des_valeurs || a_editions) {
			frappe.confirm(
				__('La colonne « {0} » contient des notes déjà saisies. Supprimer cette colonne effacera ces notes.', [label]),
				do_remove
			);
		} else {
			do_remove();
		}
	}

	function importer() {
		var tab = get_tab();
		if (active_session() && active_session().statut === 'Publiée') {
			frappe.msgprint(__('Cette session est publiée : import impossible.'));
			return;
		}
		if (tab.key === 'cc' && !state.cc_columns.length) {
			frappe.msgprint(__('Ajoutez au moins une colonne de CC avant d\'importer.'));
			return;
		}
		var input = $('<input type="file" accept=".xlsx" style="display:none;">');
		$(document.body).append(input);
		input.on('change', function () {
			var file = input[0].files[0];
			if (!file) return;
			frappe.upload_file({
				file: file,
				is_private: false,
				do_upload: true,
				callback: function (r) {
					var message = r.message || r;
					var file_url = message.file_url || message.name;
					frappe.call('udshed.api.saisie_notes.importer_notes', {
						file_url: file_url,
						type_dexamen: tab.tab,
						academic_year: state.academic_year,
						filiere: state.filiere,
						niveau: state.niveau,
						semestre: state.semestre,
						teaching_unit: state.teaching_unit,
						cc_columns: tab.key === 'cc' ? state.cc_columns : []
					}).then(function (res) {
						frappe.show_alert({ message: __('Import terminé : {0} note(s).', [res.message.saved]), indicator: 'green' });
						return load_data();
					});
				}
			});
			$(input).remove();
		});
		input.click();
	}

	function exporter() {
		var tab = get_tab();
		frappe.call('udshed.api.saisie_notes.export_notes', {
			academic_year: state.academic_year,
			filiere: state.filiere,
			niveau: state.niveau,
			semestre: state.semestre,
			teaching_unit: state.teaching_unit,
			type_dexamen: tab.tab,
			cc_columns: tab.key === 'cc' ? state.cc_columns : []
		});
	}

	function telecharger_modele() {
		var tab = get_tab();
		frappe.call('udshed.api.saisie_notes.export_modele_pdf', {
			type_dexamen: tab.tab,
			cc_columns: tab.key === 'cc' ? state.cc_columns : [],
			academic_year: state.academic_year,
			filiere: state.filiere,
			niveau: state.niveau,
			semestre: state.semestre,
			teaching_unit: state.teaching_unit
		});
	}

	function publier() {
		var session = active_session();
		if (!session) return;
		frappe.confirm(__('Publier la session {0} ? Les notes seront verrouillées.', [session.name]), function () {
			frappe.call('udshed.api.saisie_notes.publier_session', { session: session.name })
				.then(function () {
					frappe.show_alert({ message: __('Session publiée.'), indicator: 'green' });
					return load_data();
				});
		});
	}

	// ------------------------------------------------------------------ //
	//  Événements
	// ------------------------------------------------------------------ //
	function bind_events(content) {
		content.off('.sn');

		content.on('click.sn', '.sn-tab', function () {
			state.active_tab = $(this).data('tab');
			render();
		});

		content.on('input.sn', '.sn-note-input', function () {
			var student = $(this).data('student');
			var tab = get_tab();
			state.edits[tab.key] = state.edits[tab.key] || {};
			var row = state.edits[tab.key][student] = state.edits[tab.key][student] || {};
			if (tab.key === 'cc') {
				row[$(this).data('label')] = $(this).val();
			} else {
				row.note = $(this).val();
			}
			state.dirty = true;

			var saved = (state.data.notes[tab.tab] || {})[student] || null;
			if (tab.key === 'cc') {
				var moyenne = calculer_moyenne_row(saved, row);
				$(this).closest('tr').find('.sn-moyenne').text(format_note(moyenne));
			} else if (tab.key === 'rattrapage') {
				$(this).closest('tr').find('.sn-retenue').text(format_note(calculer_retenue(saved, row)));
			}
			render_footer(content);
		});

		content.on('input.sn', '.sn-cc-w-input', function () {
			var label = $(this).data('label');
			var col = state.cc_columns.find(function (c) { return c.label === label; });
			if (col) {
				col.weight = parseFloat($(this).val()) || 1;
			}
			state.dirty = true;
			var cc_notes = state.data.notes.CC || {};
			content.find('tr[data-student]').each(function () {
				var student = $(this).data('student');
				var saved = cc_notes[student] || null;
				var e = (state.edits.cc || {})[student] || {};
				$(this).find('.sn-moyenne').text(format_note(calculer_moyenne_row(saved, e)));
			});
			render_footer(content);
		});

		content.on('click.sn', '.sn-remove-cc', function () {
			supprimer_cc($(this).data('label'));
		});

		content.on('click.sn', '.sn-add-cc', ajouter_cc);
		content.on('click.sn', '.sn-save', enregistrer);
		content.on('click.sn', '.sn-import', importer);
		content.on('click.sn', '.sn-export', exporter);
		content.on('click.sn', '.sn-modele', telecharger_modele);
		content.on('click.sn', '.sn-publish', publier);
	}

	// ------------------------------------------------------------------ //
	//  Démarrage
	// ------------------------------------------------------------------ //
	apply_user_context();
	render();
}
