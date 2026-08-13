frappe.pages["note-udshed"].on_page_load = function (wrapper) {
	const API = "udshed.api.saisie_notes.";
	const MAX_CC_COLUMNS = 5;
	const TYPE_CC = "CC";
	const TYPE_EXAMEN = "Examen";
	const TYPE_RATTRAPAGE = "Rattrapage";
	const TAB_CC = "cc";
	const TAB_EXAMEN = "examen";

	const state = {
		filters: {
			academic_year: null,
			faculty: null,
			filiere: null,
			niveau: null,
			semestre: "Semestre 1",
			cours: null,
			session: "Examen normal",
		},
		ctx: null,
		enseignant: null,
		data: null,
		cc_columns: [],
		cc_cur: {},
		cc_snap: {},
		ex_cur: {},
		ex_snap: {},
		rt_cur: {},
		rt_snap: {},
		cc_full: false,
		cc_counter: 0,
		tab: TAB_CC,
		busy: false,
	};

	// ------------------------------------------------------------------
	// helpers
	// ------------------------------------------------------------------
	function to_num(v) {
		if (v === null || v === undefined) return null;
		if (typeof v === "string") {
			v = v.trim().replace(",", ".");
			if (v === "") return null;
		}
		const n = Number(v);
		return Number.isFinite(n) ? n : null;
	}

	function esc(s) {
		return String(s === null || s === undefined ? "" : s).replace(
			/[&<>"']/g,
			(c) =>
				({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
		);
	}

	function toast(message, indicator) {
		frappe.show_alert({ message, indicator: indicator || "green" }, 4);
	}

	function msg_error(message) {
		frappe.msgprint({ title: __("Erreur"), message, indicator: "red" });
	}

	function error_message(err) {
		if (!err) return __("Une erreur est survenue.");
		if (typeof err === "string") return err;
		if (err.message) return err.message;
		if (err._server_messages) {
			try {
				const msgs = JSON.parse(err._server_messages);
				if (msgs && msgs.length) return msgs.join("<br>");
			} catch (e) {
				/* ignore */
			}
		}
		return __("Une erreur est survenue.");
	}

	function qs(params) {
		const p = new URLSearchParams();
		for (const [k, v] of Object.entries(params || {})) {
			if (v === null || v === undefined || v === "") continue;
			if (Array.isArray(v) || typeof v === "object") p.append(k, JSON.stringify(v));
			else p.append(k, v);
		}
		return p.toString();
	}

	function api_download(method, params) {
		const a = document.createElement("a");
		a.href = "/api/method/" + method + "?" + qs(params);
		a.style.display = "none";
		document.body.appendChild(a);
		a.click();
		a.remove();
	}

	function upload_file(file) {
		return new Promise((resolve, reject) => {
			const fd = new FormData();
			fd.append("file", file);
			fd.append("is_private", "0");
			const xhr = new XMLHttpRequest();
			xhr.open("POST", "/api/method/upload_file");
			xhr.setRequestHeader("X-Frappe-CSRF-Token", frappe.csrf_token);
			xhr.onload = () => {
				let resp;
				try {
					resp = JSON.parse(xhr.responseText);
				} catch (e) {
					reject(new Error(__("Réponse du serveur invalide.")));
					return;
				}
				if (resp && resp.message) {
					const doc = Array.isArray(resp.message) ? resp.message[0] : resp.message;
					resolve(doc);
				} else {
					reject(new Error(error_message(resp)));
				}
			};
			xhr.onerror = () => reject(new Error(__("Impossible d'envoyer le fichier.")));
			xhr.send(fd);
		});
	}

	function active_type() {
		if (state.tab === TAB_CC) return TYPE_CC;
		return state.filters.session === "Rattrapage" ? TYPE_RATTRAPAGE : TYPE_EXAMEN;
	}

	// ------------------------------------------------------------------
	// page shell
	// ------------------------------------------------------------------
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Saisie des notes"),
		single_column: true,
	});
	page.set_title(__("Saisie des notes"));
	page.set_indicator(__("Prêt"), "green");

	$("<style>")
		.text(STYLES)
		.appendTo("head");

	const content = $('<div class="sn-page"></div>').appendTo(page.body);
	const banner = $('<div class="sn-banner" hidden></div>').appendTo(content);
	const infoBar = $('<div class="sn-info" hidden></div>').appendTo(content);
	const tabsEl = $('<div class="sn-tabs" hidden></div>').appendTo(content);
	const toolbar = $('<div class="sn-toolbar" hidden></div>').appendTo(content);
	const tableWrap = $('<div class="sn-table-wrap" hidden></div>').appendTo(content);
	const emptyEl = $('<div class="sn-empty" hidden></div>').appendTo(content);
	const fileInput = $('<input type="file" accept=".xlsx,.xls" class="hidden">').appendTo(content);

	tabsEl.html(
		'<button type="button" class="sn-tab sn-tab-active" data-tab="' +
			TAB_CC +
			'">' +
			__("Notes de contrôle continu") +
			"</button>" +
			'<button type="button" class="sn-tab" data-tab="' +
			TAB_EXAMEN +
			'">' +
			__("Notes d'examen") +
			"</button>"
	);

	// ------------------------------------------------------------------
	// filters
	// ------------------------------------------------------------------
	const fld = {};
	fld.academic_year = page.add_field({
		fieldname: "academic_year",
		label: __("Année académique"),
		fieldtype: "Link",
		options: "Academic Year",
		reqd: 1,
		change: () => reset_downstream("academic_year"),
	});
	fld.faculty = page.add_field({
		fieldname: "faculty",
		label: __("Faculté"),
		fieldtype: "Link",
		options: "Faculty",
		change: () => reset_downstream("faculty"),
	});
	fld.filiere = page.add_field({
		fieldname: "filiere",
		label: __("Filière"),
		fieldtype: "Link",
		options: "Field of study",
		reqd: 1,
		change: () => {
			reset_downstream("filiere");
			load_levels();
		},
	});
	fld.niveau = page.add_field({
		fieldname: "niveau",
		label: __("Niveau"),
		fieldtype: "Select",
		options: [""],
		reqd: 1,
		change: () => {
			reset_downstream("niveau");
			maybe_load_cours();
		},
	});
	fld.semestre = page.add_field({
		fieldname: "semestre",
		label: __("Semestre"),
		fieldtype: "Select",
		options: ["Semestre 1", "Semestre 2"],
		reqd: 1,
		change: () => {
			reset_downstream("semestre");
			maybe_load_cours();
		},
	});
	fld.cours = page.add_field({
		fieldname: "cours",
		label: __("Cours"),
		fieldtype: "Select",
		options: [""],
		reqd: 1,
		change: () => {
			read_filters();
			if (state.filters.cours) {
				load_data();
			} else {
				clear_data();
			}
		},
	});
	fld.session = page.add_field({
		fieldname: "session",
		label: __("Session"),
		fieldtype: "Select",
		options: ["Examen normal", "Rattrapage"],
		change: () => {
			read_filters();
			if (state.tab === TAB_EXAMEN) render();
		},
	});

	function read_filters() {
		const vals = page.get_form_values();
		state.filters.academic_year = vals.academic_year || null;
		state.filters.faculty = vals.faculty || null;
		state.filters.filiere = vals.filiere || null;
		state.filters.niveau = vals.niveau || null;
		state.filters.semestre = vals.semestre || null;
		state.filters.cours = vals.cours || null;
		state.filters.session = vals.session || "Examen normal";
	}

	function reset_downstream(field) {
		read_filters();
		if (field !== "cours") {
			fld.cours.set_input("");
			state.filters.cours = null;
		}
		clear_data();
	}

	function clear_data() {
		state.data = null;
		state.cc_columns = [];
		state.cc_cur = {};
		state.cc_snap = {};
		state.ex_cur = {};
		state.ex_snap = {};
		state.rt_cur = {};
		state.rt_snap = {};
		state.cc_full = false;
		render();
	}

	function show_banner(message) {
		banner.html('<span class="sn-banner-msg">' + esc(message) + "</span>").show();
	}

	function hide_banner() {
		banner.hide();
	}

	// ------------------------------------------------------------------
	// user context & teacher
	// ------------------------------------------------------------------
	function normalize_context(raw) {
		const roles = [];
		const faculties = [];
		const filieres = [];
		const niveaux = [];
		let default_academic_year = null;
		let academic_year_list = [];
		(raw || []).forEach((c) => {
			if (c.role) roles.push(c.role);
			if (c.default_academic_year) default_academic_year = c.default_academic_year;
			if (Array.isArray(c.academic_year_list)) academic_year_list = c.academic_year_list;
			(c.faculty || []).forEach((f) => {
				if (f.name) faculties.push(f.name);
			});
			(c.filiere || []).forEach((f) => {
				if (f.name) filieres.push(f.name);
			});
			(c.niveau || []).forEach((n) => {
				if (n.name) niveaux.push(n.name);
			});
		});
		return {
			roles: Array.from(new Set(roles)),
			faculties: Array.from(new Set(faculties)),
			filieres: Array.from(new Set(filieres)),
			niveaux: Array.from(new Set(niveaux)),
			default_academic_year,
			academic_year_list,
			is_admin: roles.includes("Administrator") || roles.includes("System Manager"),
			is_coordinator: roles.includes("Planning Manager") || roles.includes("Coordinateur") || roles.includes("Coordonateur"),
			is_teacher: roles.includes("Teacher"),
		};
	}

	function apply_context() {
		const ctx = state.ctx;
		if (!ctx) return;
		const is_restricted = !ctx.is_admin && (ctx.filieres.length || ctx.faculties.length || ctx.niveaux.length);

		if (ctx.academic_year_list && ctx.academic_year_list.length) {
			const names = ctx.academic_year_list.map((a) => a.name);
			fld.academic_year.df.get_query = () => ({ filters: { name: ["in", names] } });
			fld.academic_year.refresh();
		}
		if (is_restricted && ctx.faculties.length) {
			fld.faculty.df.get_query = () => ({ filters: { name: ["in", ctx.faculties] } });
			fld.faculty.refresh();
			if (ctx.faculties.length === 1) fld.faculty.set_input(ctx.faculties[0]);
		}
		if (is_restricted && ctx.filieres.length) {
			fld.filiere.df.get_query = () => ({ filters: { name: ["in", ctx.filieres] } });
			fld.filiere.refresh();
			if (ctx.filieres.length === 1) fld.filiere.set_input(ctx.filieres[0]);
		}
		if (ctx.default_academic_year) {
			fld.academic_year.set_input(ctx.default_academic_year);
		}
		read_filters();
		if (ctx.filieres.length === 1) load_levels();
	}

	function load_context() {
		frappe.call({
			method: "udshed.api.user_data.get_user_context",
			callback: (r) => {
				state.ctx = normalize_context(r.message);
				apply_context();
			},
		});
		frappe.call({
			method: API + "get_enseignant_courant",
			callback: (r) => {
				state.enseignant = r.message || null;
			},
		});
	}

	// ------------------------------------------------------------------
	// dependent selects
	// ------------------------------------------------------------------
	function load_levels() {
		read_filters();
		fld.niveau.df.options = [""];
		fld.niveau.refresh();
		if (!state.filters.filiere) return;
		frappe.call({
			method: "udshed.api.course.get_levels_for_field",
			args: { field_of_study: state.filters.filiere },
			callback: (r) => {
				const levels = r.message || [];
				const ctx = state.ctx;
				let allowed = levels;
				if (ctx && !ctx.is_admin && ctx.niveaux.length) {
					allowed = levels.filter((l) => ctx.niveaux.includes(l.name));
				}
				fld.niveau.df.options = [""].concat(allowed.map((l) => l.level));
				fld.niveau.refresh();
				if (allowed.length === 1) {
					fld.niveau.set_input(allowed[0].level);
				}
			},
		});
	}

	function maybe_load_cours() {
		read_filters();
		fld.cours.df.options = [""];
		fld.cours.refresh();
		if (!state.filters.academic_year || !state.filters.filiere || !state.filters.niveau) return;
		const ctx = state.ctx;
		let teacher = null;
		if (ctx && ctx.is_teacher && !ctx.is_admin && !ctx.is_coordinator) {
			teacher = state.enseignant ? state.enseignant.name : null;
		}
		frappe.call({
			method: API + "get_ues",
			args: {
				academic_year: state.filters.academic_year,
				filiere: state.filters.filiere,
				niveau: state.filters.niveau,
				semestre: state.filters.semestre,
				teacher: teacher || null,
			},
			callback: (r) => {
				const ues = r.message || [];
				const opts = ues.map((u) => ({
					value: u.name,
					label: u.intitule + (u.code ? " (" + u.code + ")" : "") + (u.credits ? " — " + u.credits + " cr" : ""),
				}));
				fld.cours.df.options = [""].concat(opts);
				fld.cours.refresh();
				if (!ues.length) {
					show_banner(__("Aucun cours trouvé pour ces filtres."));
				} else {
					hide_banner();
				}
			},
		});
	}

	// ------------------------------------------------------------------
	// data loading
	// ------------------------------------------------------------------
	function load_data() {
		read_filters();
		if (!state.filters.cours) return;
		show_banner("");
		frappe.call({
			method: API + "charger_data",
			args: {
				academic_year: state.filters.academic_year,
				filiere: state.filters.filiere,
				niveau: state.filters.niveau,
				semestre: state.filters.semestre,
				teaching_unit: state.filters.cours,
			},
			freeze: true,
			freeze_message: __("Chargement des notes..."),
			callback: (r) => {
				state.data = r.message;
				hide_banner();
				load_cc_state();
				load_ex_rt_state();
				render();
			},
			error: (e) => {
				console.error("[note-udshed] charger_data ERROR =", e);
				state.data = null;
				render();
				show_banner(error_message(e));
			},
		});
	}

	function load_cc_state() {
		const notes_cc = (state.data && state.data.notes && state.data.notes.CC) || {};
		const columns = [];
		const seen_labels = {};
		const weights = {};
		state.data.students.forEach((s) => {
			const cc = notes_cc[s.student];
			if (!cc) return;
			(cc.notes_cc || []).forEach((item) => {
				const label = item.cc_label;
				if (label == null || label === "") return;
				if (!seen_labels[label]) {
					seen_labels[label] = state.cc_counter++;
					columns.push({ key: "c" + seen_labels[label], label, weight: item.cc_weight != null ? item.cc_weight : 1 });
					weights[label] = item.cc_weight != null ? item.cc_weight : 1;
				}
			});
		});
		if (!columns.length) {
			columns.push({ key: "c" + state.cc_counter++, label: "CC 1", weight: 1 });
		}
		state.cc_columns = columns;
		state.cc_cur = {};
		state.data.students.forEach((s) => {
			const cc = notes_cc[s.student];
			const map = {};
			if (cc) {
				(cc.notes_cc || []).forEach((item) => {
					const col = columns.find((c) => c.label === item.cc_label);
					if (col) map[col.key] = item.note_cc == null ? "" : String(item.note_cc);
				});
			}
			state.cc_cur[s.student] = map;
		});
		state.cc_full = false;
		rebuild_cc_snap();
	}

	function load_ex_rt_state() {
		const notes_ex = (state.data && state.data.notes && state.data.notes.Examen) || {};
		const notes_rt = (state.data && state.data.notes && state.data.notes.Rattrapage) || {};
		state.ex_cur = {};
		state.ex_snap = {};
		state.rt_cur = {};
		state.rt_snap = {};
		state.data.students.forEach((s) => {
			const ex = notes_ex[s.student];
			state.ex_cur[s.student] = ex && ex.note_examen != null ? String(ex.note_examen) : "";
			state.ex_snap[s.student] = ex && ex.note_examen != null ? to_num(ex.note_examen) : null;
			const rt = notes_rt[s.student];
			state.rt_cur[s.student] = rt && rt.note_examen_rattrapage != null ? String(rt.note_examen_rattrapage) : "";
			state.rt_snap[s.student] = rt && rt.note_examen_rattrapage != null ? to_num(rt.note_examen_rattrapage) : null;
		});
	}

	function cc_sig(student) {
		const vals = state.cc_columns.map((c) => {
			const v = state.cc_cur[student] ? state.cc_cur[student][c.key] : undefined;
			return [c.label, c.weight || 1, to_num(v)];
		});
		return JSON.stringify(vals);
	}

	function rebuild_cc_snap() {
		const notes_cc = (state.data && state.data.notes && state.data.notes.CC) || {};
		state.cc_snap = {};
		state.data.students.forEach((s) => {
			const cc = notes_cc[s.student];
			const by_label = {};
			if (cc) {
				(cc.notes_cc || []).forEach((item) => {
					by_label[item.cc_label] = item.note_cc;
				});
			}
			const vals = state.cc_columns.map((c) => [
				c.label,
				c.weight || 1,
				by_label[c.label] != null ? to_num(by_label[c.label]) : null,
			]);
			state.cc_snap[s.student] = JSON.stringify(vals);
		});
	}

	function add_cc_column() {
		if (state.cc_columns.length >= MAX_CC_COLUMNS) return;
		const key = "c" + state.cc_counter++;
		state.cc_columns.push({ key, label: "CC " + (state.cc_columns.length + 1), weight: 1 });
		const notes_cc = (state.data && state.data.notes && state.data.notes.CC) || {};
		state.data.students.forEach((s) => {
			const cc = notes_cc[s.student];
			let value = "";
			if (cc) {
				const item = (cc.notes_cc || []).find((i) => i.cc_label === "CC " + state.cc_columns.length);
				if (item && item.note_cc != null) value = String(item.note_cc);
			}
			if (!state.cc_cur[s.student]) state.cc_cur[s.student] = {};
			state.cc_cur[s.student][key] = value;
		});
		render_cc();
	}

	function remove_cc_column(index) {
		const col = state.cc_columns[index];
		state.cc_columns.splice(index, 1);
		state.data.students.forEach((s) => {
			delete state.cc_cur[s.student][col.key];
		});
		state.cc_full = true;
		render_cc();
	}

	// ------------------------------------------------------------------
	// rendering
	// ------------------------------------------------------------------
	function render() {
		read_filters();
		const has_data = !!state.data;
		tabsEl.toggle(has_data);
		toolbar.toggle(has_data);
		tableWrap.toggle(has_data);
		infoBar.toggle(has_data);
		if (!has_data) {
			emptyEl.show().html(
				'<div class="sn-empty-icon">' +
					"&#128221;" +
					"</div>" +
					'<div class="sn-empty-title">' +
					__("Sélectionnez un cours") +
					"</div>" +
					'<div class="sn-empty-sub">' +
					__("Choisissez une année académique, une filière, un niveau et un cours pour afficher les étudiants et saisir les notes.") +
					"</div>"
			);
			return;
		}
		emptyEl.hide();
		const cc_field = page.fields_dict.session;
		if (cc_field) {
			cc_field.df.hidden = state.tab === TAB_CC;
			cc_field.refresh();
		}
		tabsEl.find(".sn-tab").toggleClass("sn-tab-active", (i, el) => $(el).data("tab") === state.tab);
		render_info();
		render_toolbar();
		if (state.tab === TAB_CC) render_cc();
		else render_examen();
	}

	function render_info() {
		const ue = state.data.ue_info || {};
		const sessions = state.data.sessions || {};
		const enseignant_names = (ue.enseignants || []).map((e) => e.full_name || e.name).filter(Boolean);
		const session_dot = (name) => {
			const s = sessions[name];
			const statut = s ? s.statut : "";
			const cls = statut === "Publiée" ? "blue" : statut === "Saisi" ? "orange" : statut === "Validé" ? "green" : "gray";
			return '<span class="sn-dot ' + cls + '"></span>' + esc(statut || "Brouillon");
		};
		infoBar.html(
			'<div class="sn-info-left">' +
				'<div class="sn-ue-title">' +
				esc(ue.intitule || ue.name || "") +
				(ue.code ? ' <span class="sn-ue-code">' + esc(ue.code) + "</span>" : "") +
				'</div>' +
				'<div class="sn-ue-sub">' +
				(ue.semestre ? "Semestre " + esc(ue.semestre.replace("Semestre ", "")) + " · " : "") +
				(ue.credits ? esc(ue.credits) + " crédits · " : "") +
				(ue.type_ue ? esc(ue.type_ue) + " · " : "") +
				(enseignant_names.length ? "Enseignant(s) : " + esc(enseignant_names.join(", ")) : "") +
				'</div>' +
				"</div>" +
				'<div class="sn-info-right">' +
				"<div class=\"sn-session\"><span class=\"sn-session-label\">CC</span> " + session_dot("cc") + "</div>" +
				"<div class=\"sn-session\"><span class=\"sn-session-label\">Examen</span> " + session_dot("normale") + "</div>" +
				"<div class=\"sn-session\"><span class=\"sn-session-label\">Rattrapage</span> " + session_dot("rattrapage") + "</div>" +
				"</div>"
		);
	}

	function render_toolbar() {
		const is_cc = state.tab === TAB_CC;
		const type = active_type();
		const can_add = is_cc && state.cc_columns.length < MAX_CC_COLUMNS;
		toolbar.html(
			'<button type="button" class="btn btn-primary btn-sm sn-btn sn-btn-save">' +
				(is_cc ? __("Enregistrer le CC") : type === TYPE_RATTRAPAGE ? __("Enregistrer le rattrapage") : __("Enregistrer l'examen")) +
				"</button>" +
				'<button type="button" class="btn btn-default btn-sm sn-btn sn-btn-import">' +
				"&#8681; " + __("Importer") +
				"</button>" +
				'<button type="button" class="btn btn-default btn-sm sn-btn sn-btn-export">' +
				"&#8679; " + __("Exporter") +
				"</button>" +
				'<button type="button" class="btn btn-default btn-sm sn-btn sn-btn-modele">' +
				__("Modèle Excel") +
				"</button>" +
				'<button type="button" class="btn btn-default btn-sm sn-btn sn-btn-modele-pdf">' +
				__("Modèle PDF") +
				"</button>" +
				(can_add
					? '<button type="button" class="btn btn-secondary btn-sm sn-btn sn-btn-add-cc">+ ' + __("Ajouter CC") + "</button>"
					: "") +
				'<span class="sn-toolbar-hint">' +
				(is_cc
					? __("Jusqu'à " + MAX_CC_COLUMNS + " notes de CC, avec coefficient.")
					: __("Les notes finales, grades et mentions sont calculés automatiquement.")) +
				"</span>"
		);
	}

	function render_cc() {
		const headers =
			"<th>" + __("Matricule") + "</th><th>" + __("Étudiant") + "</th>" +
			state.cc_columns
				.map(
					(c, i) =>
						'<th class="sn-cc-col">' +
						'<input type="text" class="sn-cc-label" data-i="' + i + '" value="' + esc(c.label) + '" title="Libellé">' +
						'<span class="sn-cc-weight-label">coef</span>' +
						'<input type="number" class="sn-cc-weight" data-i="' + i + '" min="0" max="10" step="0.25" value="' + esc(c.weight != null ? c.weight : 1) + '" title="Coefficient">' +
						'<button type="button" class="sn-cc-del" data-i="' + i + '" title="Supprimer cette colonne">&times;</button>' +
						"</th>"
				)
				.join("") +
			"<th>" + __("Moyenne CC") + "</th>";

		const notes_cc = (state.data.notes && state.data.notes.CC) || {};
		const body = state.data.students
			.map((s) => {
				const cc = notes_cc[s.student] || {};
				const cells = state.cc_columns
					.map((c) => {
						const v = state.cc_cur[s.student] ? state.cc_cur[s.student][c.key] : "";
						return (
							'<td class="sn-num"><input type="number" class="sn-note sn-cc-note" data-student="' +
							esc(s.student) +
							'" data-key="' +
							esc(c.key) +
							'" min="0" max="20" step="0.25" value="' +
							esc(v) +
							'"></td>'
						);
					})
					.join("");
				return (
					"<tr>" +
					'<td class="sn-mono">' + esc(s.matricule) + "</td>" +
					"<td>" + esc(s.nom) + " " + esc(s.prenom) + "</td>" +
					cells +
					'<td class="sn-num sn-moy">' + fmt_num(cc.note_cc_moyenne) + "</td>" +
					"</tr>"
				);
			})
			.join("");

		tableWrap.html(
			'<table class="sn-table"><thead><tr>' +
				headers +
				"</tr></thead><tbody>" +
				(body || '<tr><td colspan="' + (2 + state.cc_columns.length + 1) + '" class="sn-norows">' + __("Aucun étudiant n'a été inscrit dans cette filière pour ce cours.") + "</td></tr>") +
				"</tbody></table>"
		);
		bind_table_events();
	}

	function render_examen() {
		const is_rt = state.filters.session === "Rattrapage";
		const notes_cc = (state.data.notes && state.data.notes.CC) || {};
		const notes_ex = (state.data.notes && state.data.notes.Examen) || {};
		const notes_rt = (state.data.notes && state.data.notes.Rattrapage) || {};

		let headers;
		let body;
		if (is_rt) {
			headers =
				"<th>" + __("Matricule") + "</th><th>" + __("Étudiant") + "</th><th>" + __("Moy. CC") + "</th>" +
				"<th>" + __("Note initiale") + "</th>" +
				"<th>" + __("Note de rattrapage") + "</th>" +
				"<th>" + __("Note retenue") + "</th>" +
				"<th>" + __("Note finale") + "</th>" +
				"<th>" + __("Grade") + "</th><th>" + __("Points") + "</th><th>" + __("Mention") + "</th>";
			body = state.data.students
				.map((s) => {
					const cc = notes_cc[s.student] || {};
					const rt = notes_rt[s.student] || {};
					const v = state.rt_cur[s.student] || "";
					return (
						"<tr>" +
						'<td class="sn-mono">' + esc(s.matricule) + "</td>" +
						"<td>" + esc(s.nom) + " " + esc(s.prenom) + "</td>" +
						'<td class="sn-num sn-moy">' + fmt_num(cc.note_cc_moyenne) + "</td>" +
						'<td class="sn-num">' + fmt_num(rt.note_examen) + "</td>" +
						'<td class="sn-num"><input type="number" class="sn-note sn-rt-note" data-student="' + esc(s.student) + '" min="0" max="20" step="0.25" value="' + esc(v) + '"></td>' +
						'<td class="sn-num sn-strong">' + fmt_num(rt.note_examen_active) + "</td>" +
						'<td class="sn-num sn-strong">' + fmt_num(rt.note_finale) + "</td>" +
						'<td>' + esc(rt.grade || "") + "</td>" +
						'<td class="sn-num">' + fmt_num(rt.point) + "</td>" +
						"<td>" + esc(rt.mention || "") + "</td>" +
						"</tr>"
					);
				})
				.join("");
		} else {
			headers =
				"<th>" + __("Matricule") + "</th><th>" + __("Étudiant") + "</th><th>" + __("Moy. CC") + "</th>" +
				"<th>" + __("Note d'examen") + "</th>" +
				"<th>" + __("Rattrapage") + "</th>" +
				"<th>" + __("Note retenue") + "</th>" +
				"<th>" + __("Note finale") + "</th>" +
				"<th>" + __("Grade") + "</th><th>" + __("Points") + "</th><th>" + __("Mention") + "</th>";
			body = state.data.students
				.map((s) => {
					const cc = notes_cc[s.student] || {};
					const ex = notes_ex[s.student] || {};
					const rt = notes_rt[s.student] || {};
					const v = state.ex_cur[s.student] || "";
					return (
						"<tr>" +
						'<td class="sn-mono">' + esc(s.matricule) + "</td>" +
						"<td>" + esc(s.nom) + " " + esc(s.prenom) + "</td>" +
						'<td class="sn-num sn-moy">' + fmt_num(cc.note_cc_moyenne) + "</td>" +
						'<td class="sn-num"><input type="number" class="sn-note sn-ex-note" data-student="' + esc(s.student) + '" min="0" max="20" step="0.25" value="' + esc(v) + '"></td>' +
						'<td class="sn-num">' + fmt_num(rt.note_examen_rattrapage) + "</td>" +
						'<td class="sn-num sn-strong">' + fmt_num(ex.note_examen_active) + "</td>" +
						'<td class="sn-num sn-strong">' + fmt_num(ex.note_finale) + "</td>" +
						'<td>' + esc(ex.grade || "") + "</td>" +
						'<td class="sn-num">' + fmt_num(ex.point) + "</td>" +
						"<td>" + esc(ex.mention || "") + "</td>" +
						"</tr>"
					);
				})
				.join("");
		}

		tableWrap.html(
			'<table class="sn-table"><thead><tr>' +
				headers +
				"</tr></thead><tbody>" +
				(body || '<tr><td colspan="10" class="sn-norows">' + __("Aucun étudiant n'a été inscrit dans cette filière pour ce cours.") + "</td></tr>") +
				"</tbody></table>"
		);
		bind_table_events();
	}

	function fmt_num(v) {
		if (v === null || v === undefined || v === "") return "—";
		return String(Number(v));
	}

	function bind_table_events() {
		tableWrap.off("input", ".sn-note");
		tableWrap.off("input", ".sn-cc-label");
		tableWrap.off("input", ".sn-cc-weight");
		tableWrap.off("click", ".sn-cc-del");
		tableWrap.on("input", ".sn-note", (e) => {
			const input = $(e.currentTarget);
			const student = input.data("student");
			const value = input.val();
			if (input.hasClass("sn-cc-note")) {
				const key = input.data("key");
				if (!state.cc_cur[student]) state.cc_cur[student] = {};
				state.cc_cur[student][key] = value;
			} else if (input.hasClass("sn-ex-note")) {
				state.ex_cur[student] = value;
			} else if (input.hasClass("sn-rt-note")) {
				state.rt_cur[student] = value;
			}
		});
		tableWrap.on("input", ".sn-cc-label", (e) => {
			const i = $(e.currentTarget).data("i");
			state.cc_columns[i].label = $(e.currentTarget).val();
		});
		tableWrap.on("input", ".sn-cc-weight", (e) => {
			const i = $(e.currentTarget).data("i");
			const w = to_num($(e.currentTarget).val());
			state.cc_columns[i].weight = w == null ? 1 : w;
		});
		tableWrap.on("click", ".sn-cc-del", (e) => {
			remove_cc_column($(e.currentTarget).data("i"));
		});
	}

	// ------------------------------------------------------------------
	// saving
	// ------------------------------------------------------------------
	function validate_notes(items) {
		const problems = [];
		items.forEach((it) => {
			if (it.value == null) return;
			if (it.value < 0 || it.value > 20) {
				problems.push(esc(it.label) + " : " + it.value);
			}
		});
		return problems;
	}

	function save_cc() {
		if (!state.data || state.busy) return;
		const problems = [];
		state.data.students.forEach((s) => {
			state.cc_columns.forEach((c) => {
				const v = state.cc_cur[s.student] ? to_num(state.cc_cur[s.student][c.key]) : null;
				if (v == null) return;
				if (v < 0 || v > 20) {
					problems.push(esc(s.matricule) + " — " + esc(c.label) + " : " + v);
				}
			});
		});
		if (problems.length) {
			msg_error(
				__("Notes invalides (doivent être entre 0 et 20) :") +
					"<ul><li>" +
					problems.slice(0, 10).join("</li><li>") +
					"</li></ul>"
			);
			return;
		}

		const rows = [];
		state.data.students.forEach((s) => {
			if (state.cc_full || cc_sig(s.student) !== state.cc_snap[s.student]) {
				rows.push({
					student: s.student,
					notes_cc: state.cc_columns.map((c) => ({
						cc_label: c.label,
						cc_weight: c.weight || 1,
						note_cc: state.cc_cur[s.student] ? to_num(state.cc_cur[s.student][c.key]) : null,
					})),
				});
			}
		});
		if (!rows.length) {
			toast(__("Aucune modification de CC à enregistrer."), "blue");
			return;
		}
		do_save("enregistrer_cc", rows, {});
	}

	function save_examen() {
		if (!state.data || state.busy) return;
		const problems = [];
		const rows = [];
		state.data.students.forEach((s) => {
			const v = to_num(state.ex_cur[s.student]);
			if (v != null && (v < 0 || v > 20)) problems.push(esc(s.matricule) + " : " + v);
			if (v !== state.ex_snap[s.student]) rows.push({ student: s.student, note_examen: v });
		});
		if (problems.length) {
			msg_error(__("Notes d'examen invalides (doivent être entre 0 et 20) : ") + problems.join(" ; "));
			return;
		}
		if (!rows.length) {
			toast(__("Aucune note d'examen à enregistrer."), "blue");
			return;
		}
		do_save("enregistrer_examen", rows, {});
	}

	function save_rattrapage() {
		if (!state.data || state.busy) return;
		const problems = [];
		const rows = [];
		state.data.students.forEach((s) => {
			const v = to_num(state.rt_cur[s.student]);
			if (v != null && (v < 0 || v > 20)) problems.push(esc(s.matricule) + " : " + v);
			if (v !== state.rt_snap[s.student]) rows.push({ student: s.student, note_examen_rattrapage: v });
		});
		if (problems.length) {
			msg_error(__("Notes de rattrapage invalides (doivent être entre 0 et 20) : ") + problems.join(" ; "));
			return;
		}
		if (!rows.length) {
			toast(__("Aucune note de rattrapage à enregistrer."), "blue");
			return;
		}
		do_save("enregistrer_rattrapage", rows, {});
	}

	function do_save(method, rows, extra) {
		state.busy = true;
		set_busy(true);
		frappe.call({
			method: API + method,
			args: Object.assign(
				{
					academic_year: state.filters.academic_year,
					filiere: state.filters.filiere,
					niveau: state.filters.niveau,
					semestre: state.filters.semestre,
					teaching_unit: state.filters.cours,
					rows: rows,
				},
				extra
			),
			freeze: true,
			freeze_message: __("Enregistrement des notes..."),
			callback: (r) => {
				state.busy = false;
				set_busy(false);
				const n = r.message && r.message.saved != null ? r.message.saved : rows.length;
				toast(__("{0} note(s) enregistrée(s).").format(n), "green");
				load_data();
			},
			error: (e) => {
				state.busy = false;
				set_busy(false);
				msg_error(error_message(e));
			},
		});
	}

	function set_busy(busy) {
		toolbar.find(".sn-btn").prop("disabled", busy);
	}

	// ------------------------------------------------------------------
	// import / export
	// ------------------------------------------------------------------
	function start_import() {
		if (!state.filters.cours || state.busy) return;
		fileInput.val("");
		fileInput.trigger("click");
	}

	fileInput.on("change", () => {
		const file = fileInput[0].files && fileInput[0].files[0];
		fileInput.val("");
		if (!file) return;
		state.busy = true;
		set_busy(true);
		upload_file(file)
			.then((fd) => {
				frappe.call({
					method: API + "importer_notes",
					args: {
						file_url: fd.file_url,
						type_dexamen: active_type(),
						academic_year: state.filters.academic_year,
						filiere: state.filters.filiere,
						niveau: state.filters.niveau,
						semestre: state.filters.semestre,
						teaching_unit: state.filters.cours,
						cc_columns:
							active_type() === TYPE_CC
								? JSON.stringify(state.cc_columns.map((c) => ({ label: c.label, weight: c.weight || 1 })))
								: undefined,
					},
					freeze: true,
					freeze_message: __("Import des notes..."),
					callback: (r) => {
						state.busy = false;
						set_busy(false);
						const n = r.message && r.message.saved != null ? r.message.saved : 0;
						toast(__("{0} note(s) importée(s).").format(n), "green");
						load_data();
					},
					error: (e) => {
						state.busy = false;
						set_busy(false);
						msg_error(error_message(e));
					},
				});
			})
			.catch((e) => {
				state.busy = false;
				set_busy(false);
				msg_error(e && e.message ? e.message : __("Impossible d'importer le fichier."));
			});
	});

	function export_current() {
		if (!state.filters.cours) return;
		api_download(API + "export_notes", {
			academic_year: state.filters.academic_year,
			filiere: state.filters.filiere,
			niveau: state.filters.niveau,
			semestre: state.filters.semestre,
			teaching_unit: state.filters.cours,
			type_dexamen: active_type(),
			cc_columns:
				active_type() === TYPE_CC
					? JSON.stringify(state.cc_columns.map((c) => ({ label: c.label, weight: c.weight || 1 })))
					: undefined,
		});
	}

	function export_modele() {
		api_download(API + "export_modele", {
			type_dexamen: active_type(),
			cc_columns:
				active_type() === TYPE_CC
					? JSON.stringify(state.cc_columns.map((c) => ({ label: c.label, weight: c.weight || 1 })))
					: undefined,
		});
	}

	function export_modele_pdf() {
		api_download(API + "export_modele_pdf", {
			type_dexamen: active_type(),
			cc_columns:
				active_type() === TYPE_CC
					? JSON.stringify(state.cc_columns.map((c) => ({ label: c.label, weight: c.weight || 1 })))
					: undefined,
			academic_year: state.filters.academic_year,
			filiere: state.filters.filiere,
			niveau: state.filters.niveau,
			semestre: state.filters.semestre,
			teaching_unit: state.filters.cours,
		});
	}

	// ------------------------------------------------------------------
	// toolbar / tab events
	// ------------------------------------------------------------------
	toolbar.on("click", ".sn-btn-save", () => {
		if (state.tab === TAB_CC) save_cc();
		else if (state.filters.session === "Rattrapage") save_rattrapage();
		else save_examen();
	});
	toolbar.on("click", ".sn-btn-import", start_import);
	toolbar.on("click", ".sn-btn-export", export_current);
	toolbar.on("click", ".sn-btn-modele", export_modele);
	toolbar.on("click", ".sn-btn-modele-pdf", export_modele_pdf);
	toolbar.on("click", ".sn-btn-add-cc", add_cc_column);

	tabsEl.on("click", ".sn-tab", (e) => {
		state.tab = $(e.currentTarget).data("tab");
		read_filters();
		render();
	});

	// ------------------------------------------------------------------
	// boot
	// ------------------------------------------------------------------
	render();
	load_context();
};

const STYLES =
	".sn-page{max-width:1200px;margin:0 auto;padding:0 4px 40px;}" +
	".sn-banner{background:#fef1ec;border:1px solid #ffc5ad;color:#b42318;border-radius:8px;padding:10px 14px;margin:12px 0;font-size:13px;}" +
	".sn-info{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;background:#fff;border:1px solid #e2e6f0;border-radius:8px;padding:12px 16px;margin:12px 0 0;}" +
	".sn-ue-title{font-size:15px;font-weight:600;color:#1d273b;}" +
	".sn-ue-code{display:inline-block;background:#e8ecf5;color:#4858b4;border-radius:4px;padding:1px 7px;font-size:11px;font-weight:600;margin-left:6px;}" +
	".sn-ue-sub{font-size:12px;color:#687178;margin-top:3px;}" +
	".sn-info-right{display:flex;gap:14px;flex-wrap:wrap;}" +
	".sn-session{font-size:12px;color:#1d273b;background:#f7f9fc;border:1px solid #e2e6f0;border-radius:6px;padding:4px 9px;display:inline-flex;align-items:center;gap:6px;}" +
	".sn-session-label{font-weight:600;}" +
	".sn-dot{display:inline-block;width:8px;height:8px;border-radius:50%;}" +
	".sn-dot.gray{background:#a9b2c1;}.sn-dot.green{background:#4caf50;}.sn-dot.blue{background:#4858b4;}.sn-dot.orange{background:#f59e0b;}" +
	".sn-tabs{display:flex;gap:6px;margin:14px 0 0;border-bottom:1px solid #e2e6f0;padding-bottom:0;}" +
	".sn-tab{border:1px solid #e2e6f0;border-bottom:none;background:#fff;color:#687178;padding:8px 16px;border-radius:8px 8px 0 0;font-size:13px;font-weight:500;cursor:pointer;margin-bottom:-1px;}" +
	".sn-tab:hover{background:#f7f9fc;color:#1d273b;}" +
	".sn-tab-active{color:#1d273b;border-color:#d1d6e4;border-bottom-color:#fff;font-weight:600;}" +
	".sn-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:14px 0 10px;}" +
	".sn-btn{display:inline-flex;align-items:center;gap:5px;}" +
	".sn-toolbar-hint{font-size:12px;color:#8a93a3;margin-left:8px;}" +
	".sn-table-wrap{overflow-x:auto;background:#fff;border:1px solid #e2e6f0;border-radius:8px;}" +
	".sn-table{width:100%;border-collapse:collapse;font-size:13px;min-width:640px;}" +
	".sn-table th{background:#f7f9fc;color:#475069;font-weight:600;font-size:12px;padding:9px 10px;border-bottom:1px solid #e2e6f0;text-align:left;white-space:nowrap;position:sticky;top:0;}" +
	".sn-table td{padding:6px 10px;border-bottom:1px solid #eef1f7;vertical-align:middle;}" +
	".sn-table tr:nth-child(even) td{background:#fafbfd;}" +
	".sn-table tr:hover td{background:#f2f6ff;}" +
	".sn-mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;color:#687178;white-space:nowrap;}" +
	".sn-num{text-align:right;}" +
	".sn-num input{text-align:right;}" +
	".sn-moy{font-weight:600;color:#1d273b;}" +
	".sn-strong{font-weight:600;color:#1d273b;}" +
	".sn-note{width:72px;height:30px;border:1px solid #d1d6e4;border-radius:6px;padding:2px 6px;font-size:13px;color:#1d273b;}" +
	".sn-note:focus{outline:none;border-color:#4858b4;box-shadow:0 0 0 2px rgba(72,88,180,0.15);}" +
	".sn-cc-col{min-width:120px;padding:6px 8px !important;}" +
	".sn-cc-label{width:74px;height:26px;border:1px solid #d1d6e4;border-radius:5px;padding:1px 5px;font-size:12px;font-weight:600;}" +
	".sn-cc-weight-label{font-size:10px;color:#8a93a3;margin-left:5px;}" +
	".sn-cc-weight{width:52px;height:26px;border:1px solid #d1d6e4;border-radius:5px;padding:1px 4px;font-size:12px;margin-left:4px;}" +
	".sn-cc-label:focus,.sn-cc-weight:focus{outline:none;border-color:#4858b4;}" +
	".sn-cc-del{border:none;background:transparent;color:#e24f3f;font-size:16px;line-height:1;cursor:pointer;padding:0 2px;margin-left:6px;vertical-align:middle;}" +
	".sn-cc-del:hover{color:#b42318;}" +
	".sn-norows{padding:26px !important;text-align:center;color:#8a93a3;}" +
	".sn-empty{text-align:center;padding:70px 20px;color:#8a93a3;}" +
	".sn-empty-icon{font-size:34px;margin-bottom:10px;}" +
	".sn-empty-title{font-size:16px;font-weight:600;color:#475069;margin-bottom:6px;}" +
	".sn-empty-sub{font-size:13px;max-width:520px;margin:0 auto;line-height:1.5;}" +
	"";
