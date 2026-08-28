frappe.pages["gestion-des-niveaux"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Gestion des Niveaux"),
		single_column: false,
	});

	let all_data = [];
	let filtered_data = [];
	let selected_filiere = null;
	let selected_level = null;
	let search_term = "";
	let active_cycle_filters = [];
	let expanded_cycle = null;
	let selected_cycle_level = null;
	let collapsed_main_cycles = {};
	let cycle_levels_map = {};
	let cycle_options = [];

	page.body.html(`
		<div class="gn-layout">
			<div class="gn-topbar" id="gn-topbar"></div>
			<div class="gn-content">
				<div class="gn-sidebar" id="gn-sidebar"></div>
				<div class="gn-main" id="gn-main"></div>
				<div class="gn-actions-panel" id="gn-actions-panel"></div>
			</div>
		</div>
	`);

	setup_top_bar();
	load_data();

	// ── Top bar ──
	function setup_top_bar() {
		let $bar = $(`
			<div class="gn-topbar-inner">
				<div class="gn-search-wrapper">
					<svg class="gn-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
					</svg>
					<input type="text" class="gn-search-input" placeholder="${__("Rechercher une faculté, filière ou niveau…")}" />
				</div>
				<div class="gn-cycle-filters" id="gn-cycle-filters"></div>
			</div>
		`);
		$("#gn-topbar").html($bar);

		$bar.find(".gn-search-input").on("input", function () {
			search_term = $(this).val().toLowerCase().trim();
			selected_cycle_level = null;
			apply_filters();
		});

		let $cf = $bar.find("#gn-cycle-filters");
		cycle_options.forEach((c) => {
			let levels = cycle_levels_map[c] || [];
			let levels_html = levels.map(l =>
				`<div class="gn-cycle-level-item" data-level="${esc(l)}">${__(short_label(l))}</div>`
			).join("");
			$cf.append(`
				<div class="gn-cycle-dropdown" data-cycle="${c}">
					<div class="gn-cycle-tag" data-cycle="${c}">
						${__(c)}
						<svg class="gn-cycle-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>
					</div>
					<div class="gn-cycle-levels">${levels_html}</div>
				</div>
			`);
		});

		$cf.on("click", ".gn-cycle-tag", function (e) {
			e.stopPropagation();
			let c = $(this).data("cycle");
			let $dd = $(this).closest(".gn-cycle-dropdown");
			if (expanded_cycle === c) {
				$dd.removeClass("gn-cycle-open");
				expanded_cycle = null;
			} else {
				$(".gn-cycle-dropdown").removeClass("gn-cycle-open");
				$dd.addClass("gn-cycle-open");
				expanded_cycle = c;
			}
		});

		$cf.on("click", ".gn-cycle-level-item", function (e) {
			e.stopPropagation();
			let level = $(this).data("level");
			let cycle = $(this).closest(".gn-cycle-dropdown").data("cycle");
			$(".gn-cycle-level-item").removeClass("gn-level-active");
			$(this).addClass("gn-level-active");
			selected_cycle_level = level;
			active_cycle_filters = [cycle];
			$(".gn-cycle-tag").removeClass("active");
			$(".gn-cycle-tag[data-cycle='" + cycle + "']").addClass("active");
			apply_filters();
		});

		$(document).click(function () {
			$(".gn-cycle-dropdown").removeClass("gn-cycle-open");
			expanded_cycle = null;
		});
	}

	// ── Load ──
	function load_data() {
		frappe.call({
			method: "udshed.api.reregistration.get_all_levels",
			args: { faculty: null, filiere: null },
			callback(r) {
				if (!r.message) {
					frappe.show_alert({ message: __("Erreur lors du chargement des données"), indicator: "red" });
					return;
				}
				all_data = r.message || [];
				build_cycle_maps(all_data);
				apply_filters();
			},
			error(err) {
				console.error("Erreur get_all_levels:", err);
				frappe.show_alert({ message: __("Erreur lors du chargement des données"), indicator: "red" });
			}
		});
	}

	function build_cycle_maps(data) {
		cycle_levels_map = {};
		let cycle_order = ["BTS", "Licence", "Master", "Doctorat"];
		let seen = new Set();

		data.forEach(fos => {
			(fos.levels || []).forEach(l => {
				let cycle = l.cycle || "Autre";
				if (!cycle_levels_map[cycle]) {
					cycle_levels_map[cycle] = [];
				}
				if (!seen.has(l.level)) {
					cycle_levels_map[cycle].push(l.level);
					seen.add(l.level);
				}
			});
		});

		// Trier les cycles selon l'ordre prédéfini, puis alphabétique pour le reste
		cycle_options = Object.keys(cycle_levels_map).sort((a, b) => {
			let ia = cycle_order.indexOf(a);
			let ib = cycle_order.indexOf(b);
			if (ia !== -1 && ib !== -1) return ia - ib;
			if (ia !== -1) return -1;
			if (ib !== -1) return 1;
			return a.localeCompare(b);
		});
	}

	// ── Filters ──
	function apply_filters() {
		filtered_data = all_data.map((fos) => {
			if (!fos.filiere_name) return { ...fos, levels: [] };
			let levels = (fos.levels || []).filter((l) => {
				if (selected_cycle_level && l.level !== selected_cycle_level) return false;
				if (active_cycle_filters.length && !active_cycle_filters.includes(l.cycle)) return false;
				if (search_term) {
					let hay = [fos.filiere_label, fos.filiere_name, fos.faculte, l.level, l.cycle, l.coordonateur]
						.join(" ").toLowerCase();
					if (!hay.includes(search_term)) return false;
				}
				return true;
			});
			return { ...fos, levels };
		}).filter((fos) => {
			if (!fos.filiere_name) {
				return search_term ? (fos.faculte || "").toLowerCase().includes(search_term) : true;
			}
			if (search_term) {
				let hay = [fos.filiere_label, fos.filiere_name, fos.faculte].join(" ").toLowerCase();
				return fos.levels.length > 0 || hay.includes(search_term);
			}
			return fos.levels.length > 0;
		});

		render_sidebar();
		render_main();
		render_actions_panel();
	}

	// ── Sidebar ──
	function render_sidebar() {
		let $sb = $("#gn-sidebar");
		let faculties = build_tree();
		let html = `<div class="gn-sb-header">${__("Arborescence")}</div>`;

		for (let fac of faculties) {
			let fac_active = fac.name === (selected_filiere ? get_faculty(selected_filiere) : "") ? " gn-sb-fac-active" : "";
			let total_levels = fac.filieres.reduce((s, f) => s + f.total_levels, 0);
			html += `
				<div class="gn-sb-faculty${fac_active}" data-faculty="${esc(fac.name)}">
					<div class="gn-sb-fac-row">
						<svg class="gn-sb-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
						<strong>${esc(fac.label)}</strong>
						<span class="gn-sb-count">${total_levels || "0"}</span>
					</div>
					<div class="gn-sb-filieres">`;

			if (fac.filieres.length === 0) {
				html += `<div class="gn-sb-empty">${__("Aucune filière")}</div>`;
			}

			for (let fil of fac.filieres) {
				let fil_active = fil.name === selected_filiere ? " gn-sb-fil-active" : "";
				let cycle_groups = {};
				fil.levels.forEach((l) => {
					let c = l.cycle || __("Autre");
					if (!cycle_groups[c]) cycle_groups[c] = [];
					cycle_groups[c].push(l);
				});

				html += `
					<div class="gn-sb-filiere${fil_active}" data-filiere="${esc(fil.name)}">
						<div class="gn-sb-fil-row">
							<svg class="gn-sb-chevron-sm" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
							<span>${esc(fil.label)}</span>
							<span class="gn-sb-count-sm">${fil.total_levels}</span>
						</div>
						<div class="gn-sb-cycles">`;

				for (let [cycle, lvls] of Object.entries(cycle_groups)) {
					html += `
						<div class="gn-sb-cycle">
							<div class="gn-sb-cycle-label" data-cycle="${esc(cycle)}">${cycle_badge(cycle)} ${__(cycle)}</div>`;
					for (let l of lvls) {
						let lvl_active = l.name === selected_level ? " gn-sb-lvl-active" : "";
						html += `<div class="gn-sb-level${lvl_active}" data-level-name="${esc(l.name)}" data-filiere="${esc(fil.name)}">${esc(short_label(l.level))}</div>`;
					}
					html += `</div>`;
				}

				html += `</div></div>`;
			}
			html += `</div></div>`;
		}

		$sb.html(html);
		bind_sidebar_events();
	}

	function build_tree() {
		let map = {};
		filtered_data.forEach((fos) => {
			let fac = fos.faculte || __("Non assigné");
			if (!map[fac]) map[fac] = { name: fac, label: fac, filieres: [] };
			if (!fos.filiere_name) return;
			map[fac].filieres.push({
				name: fos.filiere_name,
				label: fos.filiere_label,
				levels: fos.levels || [],
				total_levels: (fos.levels || []).length,
			});
		});
		return Object.values(map).sort((a, b) => a.label.localeCompare(b.label));
	}

	function get_faculty(filiere_name) {
		for (let fos of all_data) {
			if (fos.filiere_name === filiere_name) return fos.faculte || "";
		}
		return "";
	}

	function bind_sidebar_events() {
		$(".gn-sb-fac-row").click(function () {
			$(this).closest(".gn-sb-faculty").toggleClass("gn-sb-open");
		});
		$(".gn-sb-fil-row").click(function () {
			$(this).closest(".gn-sb-filiere").toggleClass("gn-sb-open");
		});
		$(".gn-sb-filiere").click(function (e) {
			if ($(e.target).closest(".gn-sb-level, .gn-sb-cycle-label").length) return;
			let f = $(this).data("filiere");
			select_filiere(f);
		});
		$(".gn-sb-cycle-label").click(function (e) {
			e.stopPropagation();
			let cycle = $(this).data("cycle");
			let filiere = $(this).closest(".gn-sb-filiere").data("filiere");
			if (!filiere) return;
			select_filiere(filiere);
			selected_cycle_level = null;
			active_cycle_filters = [cycle];
			$(".gn-cycle-tag").removeClass("active");
			$(".gn-cycle-tag[data-cycle='" + cycle + "']").addClass("active");
			$(".gn-cycle-level-item").removeClass("gn-level-active");
			apply_filters();
		});
		$(".gn-sb-level").click(function (e) {
			e.stopPropagation();
			let f = $(this).data("filiere");
			let n = $(this).data("level-name");
			select_level(f, n);
		});
		$(".gn-sb-faculty").addClass("gn-sb-open");
	}

	// ── Main ──
	function render_main() {
		let $mn = $("#gn-main");

		if (!selected_filiere) {
			let total_levels = filtered_data.reduce((s, f) => s + (f.levels || []).length, 0);
			let total_filieres = filtered_data.filter(f => f.filiere_name !== null).length;
			$mn.html(`
				<div class="gn-empty-state">
					<svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.2">
						<path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
					</svg>
					<h3>${__("Gestion des Niveaux")}</h3>
					<p>${__("Sélectionnez une filière dans l'arborescence pour gérer ses niveaux.")}</p>
					<div class="gn-empty-stats">
						<div class="gn-stat-card">
							<div class="gn-stat-num">${total_filieres}</div>
							<div class="gn-stat-label">${__("Filières")}</div>
						</div>
						<div class="gn-stat-card">
							<div class="gn-stat-num">${total_levels}</div>
							<div class="gn-stat-label">${__("Niveaux")}</div>
						</div>
						<div class="gn-stat-card">
							<div class="gn-stat-num">${all_data.length ? new Set(all_data.map(f => f.faculte)).size : 0}</div>
							<div class="gn-stat-label">${__("Facultés")}</div>
						</div>
					</div>
				</div>`);
			return;
		}

		let fos = filtered_data.find((f) => f.filiere_name === selected_filiere);
		if (!fos || !fos.levels.length) {
			$mn.html(`
				<div class="gn-main-header">
					<button class="btn btn-xs btn-default gn-back-btn" id="gn-back">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg>
						${__("Retour")}
					</button>
					<h4 class="gn-main-title">${esc(fos ? fos.filiere_label : "")}</h4>
				</div>
				<div class="gn-empty-state">
					<p>${__("Aucun niveau dans cette filière. Utilisez le bouton « Ajouter un niveau ».")}</p>
				</div>`);
			bind_main_events();
			return;
		}

		let cycle_groups = {};
		fos.levels.forEach((l) => {
			let c = l.cycle || __("Autre");
			if (!cycle_groups[c]) cycle_groups[c] = [];
			cycle_groups[c].push(l);
		});

		let html = `
			<div class="gn-main-header">
				<button class="btn btn-xs btn-default gn-back-btn" id="gn-back">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg>
					${__("Retour")}
				</button>
				<h4 class="gn-main-title">${esc(fos.filiere_label)}</h4>
				<span class="text-muted ml-2">${fos.filiere_name}</span>
			</div>`;

		for (let [cycle, lvls] of Object.entries(cycle_groups)) {
			let collapsed = collapsed_main_cycles[cycle] || false;
			let chevron_style = collapsed ? "transform:rotate(-90deg);" : "";
			html += `
				<div class="gn-cycle-section" data-cycle="${esc(cycle)}">
					<div class="gn-cycle-header gn-cycle-toggle" data-cycle="${esc(cycle)}">
						<svg class="gn-cycle-toggle-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="${chevron_style}"><path d="m6 9 6 6 6-6"/></svg>
						${cycle_badge(cycle)}
						<strong>${__(cycle)}</strong>
						<span class="gn-cycle-count">${lvls.length} ${lvls.length > 1 ? __("niveaux") : __("niveau")}</span>
					</div>`;

			if (!collapsed) {
				html += `
					<table class="table table-hover gn-table">
						<thead>
							<tr>
								<th style="width:40px;" class="text-center">#</th>
								<th>${__("Niveau")}</th>
								<th>${__("Cycle")}</th>
								<th>${__("Coordonateur")}</th>
								<th>${__("Calendrier")}</th>
								<th style="width:140px;" class="text-center">${__("Actions")}</th>
							</tr>
						</thead>
						<tbody>`;

				lvls.forEach((l, idx) => {
					let sel = l.name === selected_level ? " gn-row-selected" : "";
					html += `
						<tr class="gn-level-row${sel}" data-level-name="${esc(l.name)}" data-filiere="${esc(fos.filiere_name)}" data-order="${l.order}">
							<td class="text-center gn-drag-handle" style="cursor:grab;" title="${__("Glisser pour réordonner")}">
								<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="opacity:.35">
									<circle cx="9" cy="5" r="1.5"/><circle cx="15" cy="5" r="1.5"/>
									<circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/>
									<circle cx="9" cy="19" r="1.5"/><circle cx="15" cy="19" r="1.5"/>
								</svg>
							</td>
							<td class="text-center">${idx + 1}</td>
							<td><strong>${esc(short_label(l.level))}</strong></td>
							<td>${cycle_badge(cycle)} ${esc(cycle)}</td>
							<td>${esc(l.coordonateur || "—")}</td>
							<td>${esc(l.calendrier || "—")}</td>
							<td class="text-center">
								<div class="btn-group btn-group-sm">
									<button class="btn btn-light gn-btn-edit" data-level-name="${esc(l.name)}" data-filiere="${esc(fos.filiere_name)}" title="${__("Modifier")}">
										<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
									</button>
									<button class="btn btn-light text-danger gn-btn-delete" data-level-name="${esc(l.name)}" data-level-label="${esc(short_label(l.level))}" data-filiere="${esc(fos.filiere_name)}" title="${__("Supprimer")}">
										<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14"/></svg>
									</button>
								</div>
							</td>
						</tr>`;
				});

				html += `</tbody></table>`;
			}

			html += `</div>`;
		}

		$mn.html(html);
		bind_main_events();
	}

	function bind_main_events() {
		$("#gn-back").click(function () {
			selected_filiere = null;
			selected_level = null;
			apply_filters();
		});

		$(".gn-level-row").click(function (e) {
			if ($(e.target).closest(".gn-btn-edit, .gn-btn-delete, .gn-drag-handle").length) return;
			let f = $(this).data("filiere");
			let n = $(this).data("level-name");
			select_level(f, n);
		});

		$(".gn-btn-edit").click(function (e) {
			e.stopPropagation();
			show_edit_dialog($(this).data("filiere"), $(this).data("level-name"));
		});

		$(".gn-btn-delete").click(function (e) {
			e.stopPropagation();
			let f = $(this).data("filiere");
			let n = $(this).data("level-name");
			let label = $(this).data("level-label");
			frappe.confirm(
				__("Voulez-vous vraiment supprimer le niveau « {0} » ?", [label]),
				() => delete_level(f, n)
			);
		});

		$(".gn-cycle-toggle").click(function () {
			let cycle = $(this).data("cycle");
			collapsed_main_cycles[cycle] = !collapsed_main_cycles[cycle];
			render_main();
		});

		bind_drag_drop();
	}

	// ── Actions Panel ──
	function render_actions_panel() {
		let $ap = $("#gn-actions-panel");
		let html = `<div class="gn-ap-header">${__("Actions rapides")}</div>`;

		html += `
			<div class="gn-ap-section">
				<button class="btn btn-primary btn-block gn-ap-btn" id="gn-ap-add-level">
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
					${__("Ajouter un niveau")}
				</button>
				<button class="btn btn-default btn-block gn-ap-btn" id="gn-ap-add-filiere">
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
					${__("Ajouter une filière")}
				</button>
				<button class="btn btn-default btn-block gn-ap-btn" id="gn-ap-add-faculty">
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
					${__("Ajouter une faculté")}
				</button>
			</div>`;

		html += `<div class="gn-ap-section gn-ap-info">`;

		if (selected_level) {
			let info = get_level_info(selected_level);
			if (info) {
				html += `
					<div class="gn-ap-info-title">${__("Niveau sélectionné")}</div>
					<div class="gn-ap-info-row"><span class="text-muted">${__("Niveau")}:</span> <strong>${esc(short_label(info.level))}</strong></div>
					<div class="gn-ap-info-row"><span class="text-muted">${__("Cycle")}:</span> ${cycle_badge(info.cycle)} ${esc(info.cycle || "—")}</div>
					<div class="gn-ap-info-row"><span class="text-muted">${__("Filière")}:</span> ${esc(info.filiere_label || "")}</div>
					<div class="gn-ap-info-row"><span class="text-muted">${__("Coordonateur")}:</span> ${esc(info.coordonateur || "—")}</div>
					<div class="gn-ap-info-row"><span class="text-muted">${__("Calendrier")}:</span> ${esc(info.calendrier || "—")}</div>
					<div class="gn-ap-info-row"><span class="text-muted">${__("Gest. planning")}:</span> ${esc(info.gestionnaire_de_planning || "—")}</div>`;
			}
		} else if (selected_filiere) {
			let fos = all_data.find((f) => f.filiere_name === selected_filiere);
			if (fos) {
				let cycles = {};
				(fos.levels || []).forEach((l) => {
					let c = l.cycle || __("Autre");
					if (!cycles[c]) cycles[c] = 0;
					cycles[c]++;
				});
				html += `
					<div class="gn-ap-info-title">${__("Filière sélectionnée")}</div>
					<div class="gn-ap-info-row"><span class="text-muted">${__("Nom")}:</span> <strong>${esc(fos.filiere_label)}</strong></div>
					<div class="gn-ap-info-row"><span class="text-muted">${__("Code")}:</span> ${esc(fos.filiere_name)}</div>
					<div class="gn-ap-info-row"><span class="text-muted">${__("Faculté")}:</span> ${esc(fos.faculte || "—")}</div>
					<div class="gn-ap-info-row"><span class="text-muted">${__("Total niveaux")}:</span> <strong>${(fos.levels || []).length}</strong></div>`;
				for (let [c, count] of Object.entries(cycles)) {
					html += `<div class="gn-ap-info-row"><span class="text-muted">${cycle_badge(c)} ${__(c)}:</span> ${count}</div>`;
				}
			}
		} else {
			let total_levels = all_data.reduce((s, f) => s + (f.levels || []).length, 0);
			let total_fac = new Set(all_data.map(f => f.faculte)).size;
			html += `
				<div class="gn-ap-info-title">${__("Vue d'ensemble")}</div>
				<div class="gn-ap-info-row"><span class="text-muted">${__("Facultés")}:</span> <strong>${total_fac}</strong></div>
				<div class="gn-ap-info-row"><span class="text-muted">${__("Filières")}:</span> <strong>${all_data.filter(f => f.filiere_name !== null).length}</strong></div>
				<div class="gn-ap-info-row"><span class="text-muted">${__("Niveaux")}:</span> <strong>${total_levels}</strong></div>`;
		}

		html += `</div>`;
		$ap.html(html);
		bind_actions_events();
	}

	function get_level_info(level_name) {
		for (let fos of all_data) {
			for (let l of fos.levels || []) {
				if (l.name === level_name) {
					return { ...l, filiere_label: fos.filiere_label, faculte: fos.faculte };
				}
			}
		}
		return null;
	}

	function bind_actions_events() {
		$("#gn-ap-add-level").click(function () {
			if (!selected_filiere) {
				frappe.show_alert({ message: __("Sélectionnez d'abord une filière."), indicator: "orange" });
				return;
			}
			show_add_level_dialog(selected_filiere);
		});
		$("#gn-ap-add-filiere").click(function () {
			show_add_filiere_dialog();
		});
		$("#gn-ap-add-faculty").click(function () {
			show_add_faculty_dialog();
		});
	}

	// ── Selection ──
	function select_filiere(f) { selected_filiere = f; selected_level = null; apply_filters(); }
	function select_level(f, n) { selected_filiere = f; selected_level = n; apply_filters(); }

	// ── Dialogs ──
	function show_add_faculty_dialog() {
		let d = new frappe.ui.Dialog({
			title: __("Ajouter une faculté"),
			fields: [
				{ fieldtype: "Data", fieldname: "faculty_name", label: __("Nom de la faculté"), reqd: 1 },
				{ fieldtype: "Data", fieldname: "faculty_code", label: __("Code"), reqd: 1 },
				{ fieldtype: "Small Text", fieldname: "description", label: __("Description") },
			],
			primary_action_label: __("Créer"),
			primary_action(values) {
				frappe.call({
					method: "frappe.client.insert",
					args: { doc: { doctype: "Faculty", faculty_name: values.faculty_name, faculty_code: values.faculty_code, description: values.description || "" } },
					freeze: true,
					freeze_message: __("Création de la faculté…"),
					callback(r) {
						d.hide();
						if (r.message) {
							frappe.show_alert({ message: __("Faculté « {0} » créée", [values.faculty_name]), indicator: "green" });
							load_data();
						}
					},
					error(err) {
						console.error("Erreur création faculté:", err);
						frappe.show_alert({ message: __("Erreur lors de la création"), indicator: "red" });
					}
				});
			},
		});
		d.show();
	}

	function show_add_filiere_dialog() {
		let d = new frappe.ui.Dialog({
			title: __("Ajouter une filière"),
			fields: [
				{ fieldtype: "Data", fieldname: "name_of_field", label: __("Intitulé"), reqd: 1 },
				{ fieldtype: "Data", fieldname: "field_of_study_code", label: __("Code"), reqd: 1 },
				{
					fieldtype: "Link", fieldname: "faculte", label: __("Faculté"), options: "Faculty", reqd: 1,
					default: selected_filiere ? get_faculty(selected_filiere) : "",
				},
				{ fieldtype: "Small Text", fieldname: "description", label: __("Description") },
			],
			primary_action_label: __("Créer"),
			primary_action(values) {
				frappe.call({
					method: "frappe.client.insert",
					args: { doc: { doctype: "Field of study", name_of_field: values.name_of_field, field_of_study_code: values.field_of_study_code, faculte: values.faculte, description: values.description || "" } },
					freeze: true,
					freeze_message: __("Création de la filière…"),
					callback(r) {
						d.hide();
						if (r.message) {
							frappe.show_alert({ message: __("Filière « {0} » créée", [values.name_of_field]), indicator: "green" });
							load_data();
						}
					},
					error(err) {
						console.error("Erreur création filière:", err);
						frappe.show_alert({ message: __("Erreur lors de la création"), indicator: "red" });
					}
				});
			},
		});
		d.show();
	}

	function show_add_level_dialog(filiere) {
		frappe.call({
			method: "frappe.client.get_list",
			args: { doctype: "Field of study Level", filters: { parent: filiere }, fields: ["level"] },
			callback(r) {
				if (!r.message) {
					frappe.show_alert({ message: __("Erreur lors du chargement"), indicator: "red" });
					return;
				}
				let existing = (r.message || []).map(l => l.level);
				let meta = frappe.get_meta("Field of study Level");
				let level_field = meta.fields.find(f => f.fieldname === "level");
				let all_options = (level_field && level_field.options || "").split("\n").filter(Boolean);
				let available = all_options.filter(o => !existing.includes(o));

				let d = new frappe.ui.Dialog({
					title: __("Ajouter un niveau à {0}", [filiere]),
					fields: [
						{ fieldtype: "Select", fieldname: "level", label: __("Niveau"), options: available.length ? ["", ...available] : [""], reqd: 1,
						  description: available.length ? __("Choisissez le niveau à ajouter") : __("Tous les niveaux existent déjà") },
						{ fieldtype: "Select", fieldname: "cycle", label: __("Cycle"), options: ["", ...cycle_options, "Autre"],
						  description: __("Déduit automatiquement si vide.") },
						{ fieldtype: "Link", fieldname: "coordonateur", label: __("Coordonnateur"), options: "Teacher", reqd: 1 },
						{ fieldtype: "Link", fieldname: "calendrier", label: __("Calendrier"), options: "Calendar Planing", reqd: 1 },
						{ fieldtype: "Link", fieldname: "gestionnaire_de_planning", label: __("Gestionnaire de planning"), options: "Teacher" },
					],
					primary_action_label: __("Ajouter"),
					primary_action(values) {
						if (!values.level) return;
						frappe.call({
							method: "udshed.api.reregistration.add_level",
							args: { filiere, level: values.level, cycle: values.cycle || "", coordonateur: values.coordonateur, calendrier: values.calendrier || "Defaut", gestionnaire_de_planning: values.gestionnaire_de_planning || "" },
							freeze: true, freeze_message: __("Ajout du niveau…"),
							callback(r2) {
								d.hide();
								if (r2.message && r2.message.status) {
									selected_filiere = filiere;
									frappe.show_alert({ message: r2.message.message, indicator: "green" });
									load_data();
								}
							},
							error(err) {
								console.error("Erreur ajout niveau:", err);
								frappe.show_alert({ message: __("Erreur lors de l'ajout"), indicator: "red" });
							}
						});
					},
				});
				d.show();
			},
			error(err) {
				console.error("Erreur get_list niveaux:", err);
				frappe.show_alert({ message: __("Erreur lors du chargement"), indicator: "red" });
			}
		});
	}

	function show_edit_dialog(filiere, level_row_name) {
		let info = get_level_info(level_row_name);
		if (!info) return;

		let d = new frappe.ui.Dialog({
			title: __("Modifier « {0} »", [short_label(info.level)]),
			fields: [
				{ fieldtype: "Select", fieldname: "cycle", label: __("Cycle"), options: [...cycle_options, "Autre"], default: info.cycle },
				{ fieldtype: "Link", fieldname: "coordonateur", label: __("Coordonnateur"), options: "Teacher", default: info.coordonateur },
				{ fieldtype: "Link", fieldname: "calendrier", label: __("Calendrier"), options: "Calendar Planing", default: info.calendrier },
				{ fieldtype: "Link", fieldname: "gestionnaire_de_planning", label: __("Gestionnaire de planning"), options: "Teacher", default: info.gestionnaire_de_planning },
			],
			primary_action_label: __("Enregistrer"),
			primary_action(values) {
				frappe.call({
					method: "udshed.api.reregistration.update_level",
					args: { filiere, level_row_name, cycle: values.cycle, coordonateur: values.coordonateur, calendrier: values.calendrier, gestionnaire_de_planning: values.gestionnaire_de_planning || "" },
					freeze: true, freeze_message: __("Enregistrement…"),
					callback(r2) {
						d.hide();
						if (r2.message && r2.message.status) {
							selected_filiere = filiere;
							selected_level = level_row_name;
							frappe.show_alert({ message: r2.message.message, indicator: "green" });
							load_data();
						}
					},
					error(err) {
						console.error("Erreur update niveau:", err);
						frappe.show_alert({ message: __("Erreur lors de la modification"), indicator: "red" });
					}
				});
			},
		});
		d.show();
	}

	// ── Delete ──
	function delete_level(filiere, level_name) {
		frappe.call({
			method: "udshed.api.reregistration.delete_level",
			args: { filiere, level_name },
			freeze: true, freeze_message: __("Suppression du niveau…"),
			callback(r) {
				if (r.message && r.message.status) {
					selected_level = null;
					frappe.show_alert({ message: r.message.message, indicator: "green" });
					load_data();
				}
			},
			error(err) {
				console.error("Erreur suppression niveau:", err);
				frappe.show_alert({ message: __("Erreur lors de la suppression"), indicator: "red" });
			}
		});
	}

	// ── Drag & Drop ──
	function bind_drag_drop() {
		if (typeof Sortable === "undefined") return;
		$(".gn-table tbody").each(function () {
			let tbody = this;
			if (tbody._sortable) return;
			tbody._sortable = new Sortable(tbody, {
				handle: ".gn-drag-handle",
				draggable: "tr",
				animation: 150,
				ghostClass: "gn-dnd-ghost",
				onEnd() {
					let f = $(tbody).closest(".gn-cycle-section").find(".gn-level-row:first").data("filiere");
					let row_names = [];
					$(tbody).find("tr[data-level-name]").each(function () {
						row_names.push($(this).data("level-name"));
					});
					if (f && row_names.length) save_order(f, row_names);
				},
			});
		});
	}

	function save_order(filiere, row_names) {
		frappe.call({
			method: "udshed.api.reregistration.reorder_levels",
			args: { filiere, level_names: row_names },
			callback() { load_data(); },
			error(err) {
				console.error("Erreur réordonnancement:", err);
				frappe.show_alert({ message: __("Erreur lors de la réorganisation"), indicator: "red" });
			}
		});
	}

	// ── Helpers ──
	function short_label(level) {
		if (!level) return level;
		let m = level.match(/^Doctorat\s+(\d+)$/);
		return m ? "D" + m[1] : level;
	}

	function cycle_badge(cycle) {
		let map = { Licence: "blue", Master: "green", BTS: "orange", Doctorat: "purple" };
		return `<span class="indicator-pill ${map[cycle] || "gray"}" style="font-size:11px;">${esc(cycle || "")}</span>`;
	}

	function esc(s) {
		return frappe.utils.escape_html(String(s || ""));
	}
};
