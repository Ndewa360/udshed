frappe.pages["note-udshed"].on_page_load = function (wrapper) {
	const API = "udshed.api.saisie_notes.";
	const TYPE_EXAMEN = "Examen";
	const TYPE_RATTRAPAGE = "Rattrapage";

	// Colonnes d'évaluations de la saisie unifiée (ordre d'affichage).
	const EVALUATIONS = [
		{ field: "cc", label: "CC" },
		{ field: "cctp", label: "CCTP" },
		{ field: "examtp", label: "EXAMTP" },
		{ field: "examen", label: "EXAM" },
	];

	const COMPOSANTE_COURT = {
		"Controle Continu(CC)": "CC",
		"Controle Continu Travaux Pratiques(CCTP)": "CCTP",
		"Examen": "EXAM",
		"Examen Travaux Pratiques(EXAMTP)": "EXAMTP",
		"Travaux Pratique (TP)": "TP",
		"Rapport": "Rapport",
		"Competence": "Compétence",
	};

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
		cur: {},
		snap: {},
		rt_cur: {},
		rt_snap: {},
		busy: false,
		preview: {},
		ues_seq: 0,
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

	function is_rattrapage_view() {
		return state.filters.session === "Rattrapage";
	}

	function active_type() {
		return is_rattrapage_view() ? TYPE_RATTRAPAGE : TYPE_EXAMEN;
	}

	// ------------------------------------------------------------------
	// aperçu automatique des calculs (moteur backend, debouncé)
	// ------------------------------------------------------------------
	let preview_timer = null;
	let preview_dirty = {};

	function preview_val(student, key, fallback) {
		const pv = state.preview[student];
		if (pv && pv[key] !== undefined && pv[key] !== null && pv[key] !== "") return pv[key];
		return fallback;
	}

	function schedule_preview(student) {
		preview_dirty[student] = true;
		clearTimeout(preview_timer);
		preview_timer = setTimeout(() => {
			const dirty = Object.keys(preview_dirty);
			preview_dirty = {};
			dirty.forEach((s) => fire_preview(s));
		}, 450);
	}

	function fire_preview(student) {
		if (!state.data || !state.filters.cours || state.busy) return;
		let args = { student, teaching_unit: state.filters.cours };
		if (is_rattrapage_view()) {
			const rt = to_num(state.rt_cur[student]);
			if (rt == null) {
				delete state.preview[student];
				update_preview_cells(student);
				return;
			}
			// On transmet CC (moyenne) et note initiale pour que l'aperçu
			// reproduise exactement le calcul de la note de rattrapage enregistrée.
			const cc = (state.data.notes.CC[student] || {}).note_cc_moyenne;
			const initiale = (state.data.notes.Rattrapage[student] || {}).note_examen;
			if (cc != null) args.notes_cc = JSON.stringify([{ cc_label: "CC", cc_weight: 1, note_cc: cc }]);
			if (initiale != null) args.note_examen = initiale;
			args.note_examen_rattrapage = rt;
		} else {
			const row = state.cur[student] || {};
			const cc = to_num(row.cc);
			const cctp = to_num(row.cctp);
			const examtp = to_num(row.examtp);
			const examen = to_num(row.examen);
			if (cc == null && cctp == null && examtp == null && examen == null) {
				delete state.preview[student];
				update_preview_cells(student);
				return;
			}
			args.notes_cc = cc == null ? "[]" : JSON.stringify([{ cc_label: "CC", cc_weight: 1, note_cc: cc }]);
			args.note_cctp = cctp;
			args.note_examtp = examtp;
			args.note_examen = examen;
		}
		frappe.call({
			method: API + "calculer_apercu",
			args,
			callback: (r) => {
				state.preview[student] = r.message || {};
				update_preview_cells(student);
				if (r.message && r.message.formule && !is_rattrapage_view()) {
					update_formule_banner(r.message.formule);
				}
			},
			error: () => {
				/* l'aperçu est facultatif : on garde les valeurs enregistrées */
			},
		});
	}

	function update_preview_cells(student) {
		tableWrap.find('[data-pv-student="' + student + '"]').each(function () {
			const key = $(this).data("pv");
			const saved = $(this).attr("data-pv-saved");
			const pv = state.preview[student];
			if (pv && pv[key] !== undefined && pv[key] !== null && pv[key] !== "") {
				const val = pv[key];
				if (key === "note_pct") $(this).text(fmt_pct(val));
				else if (key === "grade" || key === "mention" || key === "type_resultat") $(this).text(val);
				else $(this).text(fmt_num(val));
			} else if (saved !== undefined && saved !== "") {
				$(this).text(saved);
			}
		});
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
	const banner = $('<div class="sn-banner"></div>').css("display", "none").appendTo(content);
	const infoBar = $('<div class="sn-info"></div>').css("display", "none").appendTo(content);
	const formuleBar = $('<div class="sn-ue-formule sn-formule-bar"></div>').css("display", "none").appendTo(content);
	const toolbar = $('<div class="sn-toolbar"></div>').css("display", "none").appendTo(content);
	const tableWrap = $('<div class="sn-table-wrap"></div>').css("display", "none").appendTo(content);
	const emptyEl = $('<div class="sn-empty"></div>').css("display", "none").appendTo(content);
	const fileInput = $('<input type="file" accept=".xlsx,.xls" style="display:none">').appendTo(content);

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
		change: () => {
			reset_downstream("faculty");
			update_filiere_query();
		},
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
			if (state.filters.cours) render();
		},
	});

	fld.semestre.set_input("Semestre 1");
	fld.session.set_input("Examen normal");

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

	const FIELD_ORDER = ["academic_year", "faculty", "filiere", "niveau", "semestre", "cours"];

	function update_filiere_query() {
		read_filters();
		const ctx = state.ctx;
		let filters = {};
		if (state.filters.faculty) filters.faculte = state.filters.faculty;
		if (ctx && !ctx.is_admin && ctx.filieres.length) filters.name = ["in", ctx.filieres];
		fld.filiere.df.get_query = () => ({ filters });
		fld.filiere.refresh();
	}

	function reset_downstream(field) {
		read_filters();
		const idx = FIELD_ORDER.indexOf(field);
		const downstream = idx >= 0 ? FIELD_ORDER.slice(idx + 1) : ["cours"];
		downstream.forEach((f) => {
			if (f === "filiere") {
				fld.filiere.set_input("");
				state.filters.filiere = null;
			} else if (f === "niveau") {
				fld.niveau.set_input("");
				fld.niveau.df.options = [""];
				fld.niveau.refresh();
				state.filters.niveau = null;
			} else if (f === "semestre") {
				fld.semestre.set_input("Semestre 1");
				state.filters.semestre = "Semestre 1";
			} else if (f === "cours") {
				fld.cours.set_input("");
				fld.cours.df.options = [""];
				fld.cours.refresh();
				state.filters.cours = null;
			}
		});
		clear_data();
	}

	function clear_data() {
		state.data = null;
		state.cur = {};
		state.snap = {};
		state.rt_cur = {};
		state.rt_snap = {};
		state.preview = {};
		preview_dirty = {};
		clearTimeout(preview_timer);
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
			if (ctx.filieres.length === 1) fld.filiere.set_input(ctx.filieres[0]);
		}
		if (ctx.default_academic_year) {
			fld.academic_year.set_input(ctx.default_academic_year);
		}
		update_filiere_query();
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
				if (state.ctx) apply_context();
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
					maybe_load_cours();
				}
			},
		});
	}

	function maybe_load_cours() {
		read_filters();
		const previous = state.filters.cours;
		if (!previous) {
			fld.cours.df.options = [""];
			fld.cours.refresh();
		}
		if (!state.filters.academic_year || !state.filters.filiere || !state.filters.niveau) return;
		const ctx = state.ctx;
		let teacher = null;
		if (ctx && ctx.is_teacher && !ctx.is_admin && !ctx.is_coordinator) {
			teacher = state.enseignant ? state.enseignant.name : null;
		}
		const seq = ++state.ues_seq;
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
				if (seq !== state.ues_seq) return;
				const ues = r.message || [];
				const opts = ues.map((u) => ({
					value: u.name,
					label: u.intitule + (u.code ? " (" + u.code + ")" : "") + (u.credits ? " — " + u.credits + " cr" : ""),
				}));
				const keep = previous && ues.some((u) => u.name === previous);
				fld.cours.df.options = [""].concat(opts);
				fld.cours.refresh();
				if (previous && !keep) {
					fld.cours.set_input("");
					fld.cours.refresh();
					read_filters();
					clear_data();
				}
				if (!ues.length) {
					show_banner(__("Aucun cours trouvé pour ces filtres."));
				} else {
					hide_banner();
					if (ues.length === 1 && !state.filters.cours) {
						fld.cours.set_input(ues[0].name);
						read_filters();
						load_data();
					}
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
		show_banner(__("Chargement des notes..."));
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
				load_state();
				state.preview = {};
				preview_dirty = {};
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

	function load_state() {
		state.cur = {};
		state.snap = {};
		state.rt_cur = {};
		state.rt_snap = {};
		const notes_rt = (state.data && state.data.notes && state.data.notes.Rattrapage) || {};
		(state.data.lignes || []).forEach((ligne) => {
			const map = {};
			EVALUATIONS.forEach((e) => {
				const v = ligne[e.field];
				map[e.field] = v == null ? "" : String(v);
			});
			state.cur[ligne.student] = map;
			state.snap[ligne.student] = EVALUATIONS.reduce((acc, e) => {
				acc[e.field] = to_num(ligne[e.field]);
				return acc;
			}, {});
			const rt = notes_rt[ligne.student];
			state.rt_cur[ligne.student] = rt && rt.note_examen_rattrapage != null ? String(rt.note_examen_rattrapage) : "";
			state.rt_snap[ligne.student] = rt && rt.note_examen_rattrapage != null ? to_num(rt.note_examen_rattrapage) : null;
		});
	}

	function ue_credits() {
		return state.data && state.data.ue_info && state.data.ue_info.credits != null ? state.data.ue_info.credits : "";
	}

	// ------------------------------------------------------------------
	// formule / aperçu
	// ------------------------------------------------------------------
	function formule_display(formule) {
		const f = formule || (state.data && state.data.formule);
		if (!f || !f.composantes || !f.composantes.length) {
			return (
				'<span class="sn-formule-warn">⚠ ' +
				__("Aucune formule active trouvée pour cette combinaison (vérifier Grade Formula).") +
				"</span>"
			);
		}
		const chips = f.composantes
			.map(
				(c) =>
					'<span class="sn-chip">' +
					esc(COMPOSANTE_COURT[c.composante] || c.composante) +
					" <strong>" +
					esc(c.pourcentage) +
					" %</strong></span>"
			)
			.join("");
		return '<span class="sn-formule-label">' + __("Formule appliquée :") + "</span> " + chips;
	}

	function update_formule_banner(formule) {
		formuleBar.html(formule_display(formule)).show();
	}

	function formule_complete_msg() {
		const f = state.data && state.data.formule;
		if (!f || !f.composantes || !f.composantes.length) {
			return __("Aucune formule active trouvée pour cette UE. Configurez une Grade Formula (Paramétrage des formules) pour générer le PDF.");
		}
		return null;
	}

	function row_changed(student) {
		const cur = state.cur[student] || {};
		const snap = state.snap[student] || {};
		return EVALUATIONS.some((e) => to_num(cur[e.field]) !== snap[e.field]);
	}

	// ------------------------------------------------------------------
	// rendering
	// ------------------------------------------------------------------
	function render() {
		read_filters();
		const has_data = !!state.data;
		toolbar.toggle(has_data);
		tableWrap.toggle(has_data);
		infoBar.toggle(has_data);
		formuleBar.toggle(has_data);
		if (!has_data) {
			emptyEl.show().html(
				'<div class="sn-empty-icon">' +
					"&#128221;" +
					"</div>" +
					'<div class="sn-empty-title">' +
					__("Sélectionnez un cours") +
					"</div>" +
					'<div class="sn-empty-sub">' +
					__("Sélectionnez une faculté, une filière, un niveau, un semestre et un cours pour afficher les étudiants inscrits.") +
					"</div>"
			);
			return;
		}
		emptyEl.hide();
		render_info();
		render_toolbar();
		if (is_rattrapage_view()) render_rattrapage();
		else render_unifie();
	}

	function render_info() {
		const ue = state.data.ue_info || {};
		const sessions = state.data.sessions || {};
		const enseignant_names = (ue.enseignants || []).map((e) => e.full_name || e.name).filter(Boolean);
		const combinaison_labels = ((state.data.formule || {}).combinaison || "")
			.split(" + ")
			.map((c) => COMPOSANTE_COURT[c.trim()] || c.trim())
			.filter(Boolean);
		const session_dot = (name) => {
			const s = sessions[name];
			const statut = s ? s.statut : "";
			const cls = statut === "Publiée" ? "blue" : statut === "Saisi" ? "orange" : statut === "Validé" ? "green" : "gray";
			return '<span class="sn-dot ' + cls + '"></span>' + esc(statut || "Brouillon");
		};
		const initials = (name) =>
			name
				.trim()
				.split(/\s+/)
				.slice(0, 2)
				.map((w) => w.charAt(0).toUpperCase())
				.join("");
		const teacher_label = enseignant_names.length > 1 ? __("Enseignants") : __("Enseignant");
		const teacher_chips = enseignant_names
			.map(
				(n) =>
					'<span class="sn-teacher-chip">' +
					'<span class="sn-teacher-avatar">' +
					esc(initials(n)) +
					"</span>" +
					'<span class="sn-teacher-info">' +
					'<span class="sn-teacher-name">' +
					esc(n) +
					"</span>" +
					'<span class="sn-teacher-role">' +
					esc(teacher_label) +
					"</span>" +
					"</span>" +
					"</span>"
			)
			.join("");
		infoBar.html(
			'<div class="sn-info-left">' +
				'<div class="sn-ue-title">' +
				esc(ue.intitule || ue.name || "") +
				(ue.code ? ' <span class="sn-ue-code">' + esc(ue.code) + "</span>" : "") +
				'</div>' +
				'<div class="sn-ue-sub">' +
				(ue.semestre ? "Semestre " + esc(ue.semestre.replace("Semestre ", "")) + " · " : "") +
				(ue.credits ? '<span class="sn-credits">' + esc(ue.credits) + " crédits LMD</span> · " : "") +
				(combinaison_labels.length
					? '<span class="sn-chip">' +
						esc("Évaluations : " + combinaison_labels.join(" + ")) +
						"</span>"
					: "") +
				'</div>' +
				(enseignant_names.length
					? '<div class="sn-teachers"><span class="sn-teachers-label">' +
						esc(teacher_label) +
						"</span>" +
						teacher_chips +
						"</div>"
					: "") +
				'<div class="sn-ue-students">' +
				(state.data.students.length === 1 ? __("1 étudiant inscrit") : __("{0} étudiants inscrits", [state.data.students.length])) +
				"</div>" +
				"</div>" +
				'<div class="sn-info-right">' +
				"<div class=\"sn-session\"><span class=\"sn-session-label\">Examen</span> " + session_dot("normale") + "</div>" +
				"<div class=\"sn-session\"><span class=\"sn-session-label\">Rattrapage</span> " + session_dot("rattrapage") + "</div>" +
				"</div>"
		);
		update_formule_banner(state.data.formule);
	}

	function active_session_info() {
		if (!state.data || !state.data.sessions) return null;
		return is_rattrapage_view()
			? state.data.sessions.rattrapage || null
			: state.data.sessions.normale || null;
	}

	function render_toolbar() {
		const is_rt = is_rattrapage_view();
		const session = active_session_info();
		const pdf_msg = is_rt ? null : formule_complete_msg();
		const pdf_disabled = is_rt ? false : !!pdf_msg;
		toolbar.html(
			'<button type="button" class="btn btn-primary btn-sm sn-btn sn-btn-save">' +
				(is_rt ? __("Enregistrer le rattrapage") : __("Enregistrer les évaluations")) +
				"</button>" +
				'<button type="button" class="btn btn-default btn-sm sn-btn sn-btn-import">' +
				"&#8681; " + __("Importer") +
				"</button>" +
				'<button type="button" class="btn btn-default btn-sm sn-btn sn-btn-export">' +
				"&#8679; " + __("Exporter") +
				"</button>" +
				(is_rt
					? '<button type="button" class="btn btn-default btn-sm sn-btn sn-btn-modele">' + __("Modèle Excel") + "</button>"
					: '') +
				'<span class="sn-toolbar-hint">' +
				(is_rt
					? __("La note retenue = MAX(Session examen, Session rattrapage).")
					: __("La combinaison (CC, CCTP, EXAMTP, EXAM) est détectée automatiquement ; les poids proviennent de la Grade Formula.")) +
				"</span>" +
				'<span class="sn-toolbar-sep"></span>' +
				'<button type="button" class="btn btn-default btn-sm sn-btn sn-btn-pdf" ' + (pdf_disabled ? "disabled title=\"" + esc(pdf_msg) + "\"" : "") + ">" +
					"&#128196; " + __("Télécharger PDF") +
					"</button>" +
				'<button type="button" class="btn btn-success btn-sm sn-btn sn-btn-valider">' +
				__("Valider") +
				"</button>" +
				'<button type="button" class="btn btn-danger btn-sm sn-btn sn-btn-publier">' +
				__("Publier") +
				"</button>" +
				'<span class="sn-session-label">' +
				(session ? esc(session.statut || "Brouillon") : "") +
				"</span>" +
				(pdf_disabled && pdf_msg ? '<span class="sn-pdf-msg">' + esc(pdf_msg) + "</span>" : "")
		);
	}

	// ------------------------------------------------------------------
	// tableau unifié (Examen normal)
	// ------------------------------------------------------------------
	function render_unifie() {
		const headers =
			"<th>" + __("N°") + "</th><th>" + __("Matricule") + "</th><th>" + __("Nom et Prénoms") + "</th>" +
			EVALUATIONS.map((e) => '<th class="sn-ev-head">' + esc(e.label) + "</th>").join("") +
			"<th>" + __("MOY (%)") + "</th><th>" + __("GRD") + "</th><th>" + __("PTS") + "</th>";

		const body = (state.data.lignes || [])
			.map((ligne, idx) => {
				const row = state.cur[ligne.student] || {};
				const inputs = EVALUATIONS.map(
					(e) =>
						'<td class="sn-num"><input type="number" class="sn-note sn-ev-note" data-student="' +
						esc(ligne.student) +
						'" data-field="' +
						esc(e.field) +
						'" min="0" max="20" step="0.25" value="' +
						esc(row[e.field] || "") +
						'"></td>'
				).join("");
				return (
					"<tr>" +
					'<td class="sn-num">' + (idx + 1) + "</td>" +
					'<td class="sn-mono">' + esc(ligne.matricule) + "</td>" +
					"<td>" + esc(ligne.nom) + " " + esc(ligne.prenom) + "</td>" +
					inputs +
					'<td class="sn-num sn-strong" data-pv-student="' + esc(ligne.student) + '" data-pv="note_pct" data-pv-saved="' +
					esc(fmt_pct(ligne.note_pct)) +
					'">' +
					fmt_pct(preview_val(ligne.student, "note_pct", ligne.note_pct)) +
					"</td>" +
					'<td data-pv-student="' + esc(ligne.student) + '" data-pv="grade" data-pv-saved="' +
					esc(ligne.grade || "") +
					'">' +
					esc(preview_val(ligne.student, "grade", ligne.grade || "")) +
					"</td>" +
					'<td class="sn-num" data-pv-student="' + esc(ligne.student) + '" data-pv="point" data-pv-saved="' +
					esc(fmt_num(ligne.point)) +
					'">' +
					fmt_num(preview_val(ligne.student, "point", ligne.point)) +
					"</td>" +
					"</tr>"
				);
			})
			.join("");

		tableWrap.html(
			'<table class="sn-table"><thead><tr>' +
				headers +
				"</tr></thead><tbody>" +
				(body || '<tr><td colspan="' + (3 + EVALUATIONS.length + 3) + '" class="sn-norows">' + __("Aucun étudiant inscrit à ce cours dans ce contexte académique.") + "</td></tr>") +
				"</tbody></table>"
		);
		bind_table_events();
	}

	// ------------------------------------------------------------------
	// tableau rattrapage
	// ------------------------------------------------------------------
	function render_rattrapage() {
		const notes_cc = (state.data.notes && state.data.notes.CC) || {};
		const notes_rt = (state.data.notes && state.data.notes.Rattrapage) || {};

		const headers = [__("Matricule"), __("Étudiant"), __("Moy. CC"), __("Session examen"), __("Session rattrapage"), __("Note retenue"), __("Note finale"), __("%"), __("Grade"), __("Points")];
		const headerHtml = headers.map((h) => "<th>" + esc(h) + "</th>").join("");

		const body = (state.data.lignes || [])
			.map((ligne) => {
				const cc = notes_cc[ligne.student] || {};
				const rt = notes_rt[ligne.student] || {};
				const v = state.rt_cur[ligne.student] || "";
				const src = rt;
				return (
					"<tr>" +
					'<td class="sn-mono">' + esc(ligne.matricule) + "</td>" +
					"<td>" + esc(ligne.nom) + " " + esc(ligne.prenom) + "</td>" +
					'<td class="sn-num">' + fmt_num(cc.note_cc_moyenne) + "</td>" +
					'<td class="sn-num">' + fmt_num(rt.note_examen) + "</td>" +
					'<td class="sn-num"><input type="number" class="sn-note sn-rt-note" data-student="' + esc(ligne.student) +
					'" min="0" max="20" step="0.25" value="' + esc(v) + '"></td>' +
					'<td class="sn-num sn-strong" data-pv-student="' + esc(ligne.student) + '" data-pv="note_examen_active" data-pv-saved="' +
					esc(fmt_num(src.note_examen_active)) +
					'">' +
					fmt_num(preview_val(ligne.student, "note_examen_active", src.note_examen_active)) +
					"</td>" +
					'<td class="sn-num sn-strong" data-pv-student="' + esc(ligne.student) + '" data-pv="note_finale" data-pv-saved="' +
					esc(fmt_num(src.note_finale)) +
					'">' +
					fmt_num(preview_val(ligne.student, "note_finale", src.note_finale)) +
					"</td>" +
					'<td class="sn-num sn-strong" data-pv-student="' + esc(ligne.student) + '" data-pv="note_pct" data-pv-saved="' +
					esc(fmt_pct(src.note_pct)) +
					'">' +
					fmt_pct(preview_val(ligne.student, "note_pct", src.note_pct)) +
					"</td>" +
					'<td data-pv-student="' + esc(ligne.student) + '" data-pv="grade" data-pv-saved="' +
					esc(src.grade || "") +
					'">' +
					esc(preview_val(ligne.student, "grade", src.grade || "")) +
					"</td>" +
					'<td class="sn-num" data-pv-student="' + esc(ligne.student) + '" data-pv="point" data-pv-saved="' +
					esc(fmt_num(src.point)) +
					'">' +
					fmt_num(preview_val(ligne.student, "point", src.point)) +
					"</td>" +
					"</tr>"
				);
			})
			.join("");

		tableWrap.html(
			'<table class="sn-table"><thead><tr>' +
				headerHtml +
				"</tr></thead><tbody>" +
				(body || '<tr><td colspan="' + headers.length + '" class="sn-norows">' + __("Aucun étudiant inscrit à ce cours dans ce contexte académique.") + "</td></tr>") +
				"</tbody></table>"
		);
		bind_table_events();
	}

	function fmt_num(v) {
		if (v === null || v === undefined || v === "") return "—";
		return String(Number(v));
	}

	function fmt_pct(v) {
		if (v === null || v === undefined || v === "") return "—";
		return String(Number(v)) + " %";
	}

	function bind_table_events() {
		tableWrap.off("input", ".sn-note");
		tableWrap.on("input", ".sn-note", (e) => {
			const input = $(e.currentTarget);
			const student = input.data("student");
			const value = input.val();
			if (input.hasClass("sn-ev-note")) {
				const field = input.data("field");
				if (!state.cur[student]) state.cur[student] = {};
				state.cur[student][field] = value;
			} else if (input.hasClass("sn-rt-note")) {
				state.rt_cur[student] = value;
			}
			schedule_preview(student);
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

	function save_evaluations() {
		if (!state.data || state.busy) return;
		const problems = [];
		const rows = [];
		state.data.students.forEach((s) => {
			const row = state.cur[s.student] || {};
			EVALUATIONS.forEach((e) => {
				const v = to_num(row[e.field]);
				if (v != null && (v < 0 || v > 20)) {
					problems.push(esc(s.matricule) + " — " + esc(e.label) + " : " + v);
				}
			});
			if (row_changed(s.student)) {
				rows.push({
					student: s.student,
					cc: to_num(row.cc),
					note_cctp: to_num(row.cctp),
					note_examtp: to_num(row.examtp),
					note_examen: to_num(row.examen),
				});
			}
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
		if (!rows.length) {
			toast(__("Aucune évaluation à enregistrer."), "blue");
			return;
		}
		do_save("enregistrer_evaluations", rows, {});
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
				toast(__("{0} note(s) enregistrée(s).", [n]), "green");
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
				const is_rt = is_rattrapage_view();
				frappe.call({
					method: API + (is_rt ? "importer_notes" : "importer_evaluations"),
					args: {
						file_url: fd.file_url,
						type_dexamen: is_rt ? TYPE_RATTRAPAGE : undefined,
						academic_year: state.filters.academic_year,
						filiere: state.filters.filiere,
						niveau: state.filters.niveau,
						semestre: state.filters.semestre,
						teaching_unit: state.filters.cours,
					},
					freeze: true,
					freeze_message: __("Import des notes..."),
					callback: (r) => {
						state.busy = false;
						set_busy(false);
						const n = r.message && r.message.saved != null ? r.message.saved : 0;
						toast(__("{0} note(s) importée(s).", [n]), "green");
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
		const is_rt = is_rattrapage_view();
		api_download(API + (is_rt ? "export_notes" : "export_evaluations"), {
			academic_year: state.filters.academic_year,
			filiere: state.filters.filiere,
			niveau: state.filters.niveau,
			semestre: state.filters.semestre,
			teaching_unit: state.filters.cours,
			type_dexamen: is_rt ? TYPE_RATTRAPAGE : undefined,
		});
	}

	function export_modele() {
		api_download(API + "export_modele", { type_dexamen: TYPE_RATTRAPAGE });
	}

	// ------------------------------------------------------------------
	// toolbar events
	// ------------------------------------------------------------------
	toolbar.on("click", ".sn-btn-save", () => {
		if (is_rattrapage_view()) save_rattrapage();
		else save_evaluations();
	});
	toolbar.on("click", ".sn-btn-import", start_import);
	toolbar.on("click", ".sn-btn-export", export_current);
	toolbar.on("click", ".sn-btn-modele", export_modele);
	toolbar.on("click", ".sn-btn-pdf", () => {
		if (!state.filters.cours) return;
		const msg = formule_complete_msg();
		if (msg) {
			msg_error(msg);
			return;
		}
		const non_enregistre =
			(state.data.lignes || []).some((ligne) => row_changed(ligne.student)) ||
			(state.data.students || []).some(
				(s) => to_num(state.rt_cur[s.student]) !== state.rt_snap[s.student]
			);
		if (non_enregistre) {
			msg_error(
				__(
					"Des notes saisies ne sont pas encore enregistrées. Cliquez d'abord sur « Enregistrer les évaluations » ou « Enregistrer le rattrapage » avant de télécharger le PDF."
				)
			);
			return;
		}
		api_download(API + "generer_pdf", {
			academic_year: state.filters.academic_year,
			filiere: state.filters.filiere,
			niveau: state.filters.niveau,
			semestre: state.filters.semestre,
			teaching_unit: state.filters.cours,
		});
	});
	toolbar.on("click", ".sn-btn-valider", () => {
		const session = active_session_info();
		if (!session || !session.name) return;
		frappe.confirm(__("Valider toutes les notes de cette session ?"), () => {
			frappe.call({
				method: API + "valider_notes",
				args: { session: session.name },
				freeze: true,
				freeze_message: __("Validation des notes..."),
				callback: (r) => {
					const msg = r.message || {};
					toast(__("{0} note(s) validée(s).", [msg.validated != null ? msg.validated : 0]), "green");
					load_data();
				},
				error: (e) => msg_error(error_message(e)),
			});
		});
	});
	toolbar.on("click", ".sn-btn-publier", () => {
		const session = active_session_info();
		if (!session || !session.name) return;
		frappe.confirm(
			__("Publier les résultats de cette session ? Toutes les notes doivent être validées. Les notes resteront modifiables après publication en cas de requête ou de correction."),
			() => {
				frappe.call({
					method: API + "publier_session",
					args: { session: session.name },
					freeze: true,
					freeze_message: __("Publication des résultats..."),
					callback: (r) => {
						toast(__("Session publiée."), "green");
						load_data();
					},
					error: (e) => msg_error(error_message(e)),
				});
			}
		);
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
	".sn-ue-students{font-size:12px;font-weight:600;color:#4858b4;margin-top:6px;}" +
	".sn-info-right{display:flex;gap:14px;flex-wrap:wrap;}" +
	".sn-session{font-size:12px;color:#1d273b;background:#f7f9fc;border:1px solid #e2e6f0;border-radius:6px;padding:4px 9px;display:inline-flex;align-items:center;gap:6px;}" +
	".sn-session-label{font-weight:600;}" +
	".sn-dot{display:inline-block;width:8px;height:8px;border-radius:50%;}" +
	".sn-dot.gray{background:#a9b2c1;}.sn-dot.green{background:#4caf50;}.sn-dot.blue{background:#4858b4;}.sn-dot.orange{background:#f59e0b;}" +
	".sn-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:14px 0 10px;}" +
	".sn-btn{display:inline-flex;align-items:center;gap:5px;}" +
	".sn-toolbar-hint{font-size:12px;color:#8a93a3;margin-left:8px;}" +
	".sn-toolbar-sep{display:inline-block;width:1px;height:22px;background:#e2e6f0;margin:0 6px;}" +
	".sn-toolbar .sn-session-label{font-size:11px;color:#687178;background:#f7f9fc;border:1px solid #e2e6f0;border-radius:5px;padding:3px 8px;text-transform:capitalize;}" +
	".sn-formule-bar{margin:10px 0 0;}" +
	".sn-table-wrap{overflow-x:auto;background:#fff;border:1px solid #e2e6f0;border-radius:8px;}" +
	".sn-table{width:100%;border-collapse:collapse;font-size:13px;min-width:820px;}" +
	".sn-table th{background:#f7f9fc;color:#475069;font-weight:600;font-size:12px;padding:9px 10px;border-bottom:1px solid #e2e6f0;text-align:left;white-space:nowrap;position:sticky;top:0;}" +
	".sn-table td{padding:6px 10px;border-bottom:1px solid #eef1f7;vertical-align:middle;}" +
	".sn-table tr:nth-child(even) td{background:#fafbfd;}" +
	".sn-table tr:hover td{background:#f2f6ff;}" +
	".sn-mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;color:#687178;white-space:nowrap;}" +
	".sn-num{text-align:right;}" +
	".sn-num input{text-align:right;}" +
	".sn-credits{color:#4858b4;font-weight:600;}" +
	".sn-strong{font-weight:600;color:#1d273b;}" +
	".sn-note{width:72px;height:30px;border:1px solid #d1d6e4;border-radius:6px;padding:2px 6px;font-size:13px;color:#1d273b;}" +
	".sn-note:focus{outline:none;border-color:#4858b4;box-shadow:0 0 0 2px rgba(72,88,180,0.15);}" +
	".sn-ev-head{min-width:84px;text-align:center !important;}" +
	".sn-ue-formule{font-size:12px;color:#475069;display:flex;align-items:center;gap:6px;flex-wrap:wrap;}" +
	".sn-formule-label{font-weight:600;color:#1d273b;}" +
	".sn-chip{display:inline-flex;align-items:center;gap:4px;background:#eef1f8;border:1px solid #dfe4f2;border-radius:10px;padding:1px 9px;color:#3a478e;}" +
	".sn-teachers{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:8px;padding-top:8px;border-top:1px dashed #e2e6f0;}" +
	".sn-teachers-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#8a93a3;white-space:nowrap;}" +
	".sn-teacher-chip{display:inline-flex;align-items:center;gap:8px;background:#f7f9fc;border:1px solid #e2e6f0;border-radius:22px;padding:3px 14px 3px 4px;transition:border-color .15s ease,box-shadow .15s ease;}" +
	".sn-teacher-chip:hover{border-color:#c3cbec;box-shadow:0 1px 4px rgba(72,88,180,.12);}" +
	".sn-teacher-avatar{width:26px;height:26px;border-radius:50%;background:linear-gradient(135deg,#4858b4,#7386e8);color:#fff;font-size:10px;font-weight:700;letter-spacing:.5px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;text-transform:uppercase;}" +
	".sn-teacher-info{display:inline-flex;flex-direction:column;line-height:1.25;}" +
	".sn-teacher-name{font-size:12px;font-weight:600;color:#1d273b;white-space:nowrap;}" +
	".sn-teacher-role{font-size:10px;color:#8a93a3;}" +
	".sn-formule-warn{color:#b42318;font-weight:600;}" +
	".sn-pdf-msg{font-size:11px;color:#8a93a3;}" +
	".sn-btn-pdf[disabled]{opacity:.55;cursor:not-allowed;}" +
	".sn-norows{padding:26px !important;text-align:center;color:#8a93a3;}" +
	".sn-empty{text-align:center;padding:70px 20px;color:#8a93a3;}" +
	".sn-empty-icon{font-size:34px;margin-bottom:10px;}" +
	".sn-empty-title{font-size:16px;font-weight:600;color:#475069;margin-bottom:6px;}" +
	".sn-empty-sub{font-size:13px;max-width:520px;margin:0 auto;line-height:1.5;}" +
	"";