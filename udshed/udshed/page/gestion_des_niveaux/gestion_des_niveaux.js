frappe.pages["gestion-des-niveaux"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Gestion des Niveaux",
		single_column: true,
	});

	let filters = { faculty: null, filiere: null };
	let all_data = [];
	let filiere_field = null;
	let btn_ajouter = null;
	let last_added = null;
	let recap_datatable = null;

	function setup_filters() {
		page.add_field({
			fieldtype: "Link",
			label: "Faculté",
			fieldname: "faculty",
			options: "Faculty",
			change() {
				filters.faculty = this.get_value();
				filters.filiere = null;
				if (filiere_field) filiere_field.set_value("");
				load_levels();
			},
		});

		filiere_field = page.add_field({
			fieldtype: "Link",
			label: "Filière",
			fieldname: "filiere",
			options: "Field of study",
			get_query() {
				if (!filters.faculty) return {};
				return { filters: { faculte: filters.faculty } };
			},
			change() {
				filters.filiere = this.get_value();
				toggle_ajouter_btn(!!this.get_value());
				load_levels();
			},
		});
	}

	function toggle_ajouter_btn(show) {
		if (btn_ajouter) {
			btn_ajouter.toggle(show);
		}
	}

	function setup_primary_action() {
		btn_ajouter = page.set_primary_action(__("Ajouter un niveau"), function () {
			if (!filters.filiere) {
				frappe.msgprint(__("Veuillez d'abord sélectionner une filière."));
				return;
			}
			show_add_level_dialog(filters.filiere);
		}, "plus");
		btn_ajouter.toggle(false);
	}

	function show_add_level_dialog(filiere) {
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Field of study Level",
				filters: { parent: filiere },
				fields: ["level"],
			},
			callback(r) {
				let existing_levels = (r.message || []).map(l => l.level);
				let all_options = [
					"Licence 1", "Licence 2", "Licence 3",
					"BTS 1", "BTS 2",
					"Master 1", "Master 2"
				];
				let available = all_options.filter(o => !existing_levels.includes(o));

				let d = new frappe.ui.Dialog({
					title: __("Ajouter un niveau à {0}", [filiere]),
					fields: [
						{
							fieldtype: "Select",
							fieldname: "level",
							label: __("Niveau"),
							options: available.length ? ["", ...available] : [""],
							reqd: 1,
							description: available.length
								? __("Choisissez le niveau à ajouter")
								: __("Tous les niveaux existent déjà dans cette filière"),
						},
						{
							fieldtype: "Select",
							fieldname: "cycle",
							label: __("Cycle"),
							options: ["", "Licence", "Master", "BTS", "Doctorat", "Autre"],
							description: __("Si vide, le cycle sera déduit automatiquement du niveau."),
						},
						{
							fieldtype: "Link",
							fieldname: "coordonateur",
							label: __("Coordonateur"),
							options: "Teacher",
							reqd: 1,
						},
						{
							fieldtype: "Link",
							fieldname: "calendrier",
							label: __("Calendrier"),
							options: "Calendar Planing",
							reqd: 1,
						},
						{
							fieldtype: "Link",
							fieldname: "gestionnaire_de_planning",
							label: __("Gestionnaire de planning"),
							options: "Teacher",
						},
					],
					primary_action_label: __("Ajouter"),
					primary_action(values) {
						if (!values.level) return;
						frappe.call({
							method: "udshed.api.reregistration.add_level",
							args: {
								filiere,
								level: values.level,
								cycle: values.cycle || "",
								coordonateur: values.coordonateur,
								calendrier: values.calendrier || "Defaut",
								gestionnaire_de_planning: values.gestionnaire_de_planning || "",
							},
							freeze: true,
							freeze_message: __("Ajout du niveau..."),
							callback(r2) {
								d.hide();
								if (r2.message && r2.message.status) {
									last_added = { filiere: filiere, level: values.level };
									frappe.show_alert({
										message: r2.message.message,
										indicator: "green",
									});
									load_levels();
								}
							},
						});
					},
				});
				d.show();
			},
		});
	}

	function load_levels() {
		frappe.call({
			method: "udshed.api.reregistration.get_all_levels",
			args: {
				faculty: filters.faculty || null,
				filiere: filters.filiere || null,
			},
			callback(r) {
				all_data = r.message || [];
				render_table();
			},
		});
	}

	function render_table() {
		let html = build_table_html() + recap_container_html();
		page.body.html(
			'<div class="levels-management-container" style="padding: 15px;">' +
				html +
				"</div>"
		);
		render_recap_datatable();
		bind_events();
		highlight_last_added();
	}

	function recap_container_html() {
		return `
			<div class="card mb-4">
				<div class="card-header d-flex justify-content-between align-items-center">
					<div>
						<strong>${__("Récapitulatif de tous les niveaux")}</strong>
						<span class="text-muted ml-2" id="recap-count-badge">0 niveau</span>
					</div>
				</div>
				<div class="card-body">
					<div id="recap-datatable"></div>
				</div>
			</div>`;
	}

	function recap_rows() {
		let rows = [];
		(all_data || []).forEach((fos) => {
			(fos.levels || []).forEach((l) => {
				rows.push([
					{ content: l.level || "" },
					{ content: l.cycle || "—" },
					{ content: fos.filiere_label || "" },
					{ content: fos.faculte || "" },
					{ content: l.coordonateur || "" },
					{ content: l.calendrier || "" },
				]);
			});
		});
		return rows;
	}

	function render_recap_datatable() {
		let rows = recap_rows();
		let $count = $("#recap-count-badge");
		if ($count.length) {
			$count.text(rows.length + (rows.length > 1 ? " niveaux" : " niveau"));
		}
		let $el = $("#recap-datatable");
		if (!$el.length) return;

		if (recap_datatable) {
			recap_datatable.destroy();
			recap_datatable = null;
		}

		if (!rows.length) {
			$el.html(
				'<div class="text-muted text-center" style="padding: 30px;">' +
					__("Aucun niveau créé pour l'instant.") +
					"</div>"
			);
			return;
		}

		let columns = [
			{ name: __("Niveau"), id: "niveau", editable: false },
			{ name: __("Cycle"), id: "cycle", editable: false },
			{ name: __("Filière"), id: "filiere", editable: false },
			{ name: __("Faculté"), id: "faculte", editable: false },
			{ name: __("Coordonnateur"), id: "coordonateur", editable: false },
			{ name: __("Calendrier"), id: "calendrier", editable: false },
		];

		recap_datatable = new frappe.DataTable($el[0], {
			columns: columns,
			data: rows,
			inlineFilters: true,
			language: frappe.boot.lang,
			cellHeight: 33,
			layout: "fixed",
			serialNoColumn: true,
			noDataMessage: __("Aucune donnée"),
			direction: frappe.utils.is_rtl() ? "rtl" : "ltr",
		});
	}

	function highlight_last_added() {
		if (!last_added) return;
		let { filiere, level } = last_added;
		last_added = null;
		$(".levels-table tbody").each(function () {
			if ($(this).data("filiere") !== filiere) return;
			$(this).find("tr").each(function () {
				let $tr = $(this);
				if ($tr.find("td").eq(2).text().trim() === level) {
					$tr.addClass("level-row-highlight");
					if ($tr[0].scrollIntoView) {
						$tr[0].scrollIntoView({ behavior: "smooth", block: "center" });
					}
					setTimeout(() => $tr.removeClass("level-row-highlight"), 3000);
				}
			});
		});
	}

	function build_table_html() {
		if (!all_data.length) {
			return `
				<div class="text-muted text-center" style="padding: 60px 40px;">
					<div style="font-size: 48px; margin-bottom: 15px; opacity: 0.3;">
						<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
							<path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
						</svg>
					</div>
					<h5 class="text-muted">${__("Bienvenue dans la Gestion des Niveaux")}</h5>
					<p class="text-muted" style="max-width: 400px; margin: 10px auto;">
						${__("Sélectionnez une filière pour voir ses niveaux, les réorganiser ou en ajouter de nouveaux.")}<br><br>
						${__("Les niveaux sont gérés dans chaque filière (Field of study).")}
					</p>
				</div>`;
		}

		let html = "";
		let shown = 0;
		all_data.forEach((fos) => {
			if (filters.faculty && fos.faculte !== filters.faculty) return;
			if (filters.filiere && fos.filiere_name !== filters.filiere) return;
			shown++;
			let levels = fos.levels || [];			html += `
				<div class="card mb-4">
					<div class="card-header d-flex justify-content-between align-items-center">
						<div>
							<strong>${frappe.utils.escape_html(fos.filiere_label)}</strong>
							<span class="text-muted ml-2">(${frappe.utils.escape_html(fos.filiere_name)})</span>
							<span class="text-muted ml-2">${levels.length} niveau${levels.length > 1 ? "x" : ""}</span>
						</div>
						<div>
							<button class="btn btn-sm btn-primary add-level-btn mr-2"
								data-filiere="${frappe.utils.escape_html(fos.filiere_name)}">
								${__("+ Ajouter")}
							</button>
							<button class="btn btn-sm btn-secondary open-filiere-btn"
								data-filiere="${frappe.utils.escape_html(fos.filiere_name)}">
								${__("Modifier la filière")}
							</button>
						</div>
					</div>
					<div class="card-body p-0">
						<table class="table table-hover mb-0 levels-table">
							<thead class="thead-light">
								<tr>
									<th style="width: 36px;"></th>
									<th style="width: 60px;">${__("Ordre")}</th>
									<th>${__("Niveau")}</th>
									<th>${__("Cycle")}</th>
									<th>${__("Coordonateur")}</th>
									<th>${__("Calendrier")}</th>
									<th style="width: 120px;">${__("Actions")}</th>
								</tr>
							</thead>
							<tbody data-filiere="${frappe.utils.escape_html(fos.filiere_name)}">
								${levels.length ? levels.map((l, idx) => build_level_row(fos.filiere_name, l, idx, levels.length)).join("") : `
									<tr>
										<td colspan="7" class="text-center text-muted" style="padding: 30px;">
											${__("Aucun niveau. Cliquez sur « + Ajouter » pour en créer un.")}
										</td>
									</tr>`}
							</tbody>
						</table>
					</div>
				</div>`;
		});
		if (!shown) {
			return `
				<div class="text-muted text-center" style="padding: 40px 20px;">
					${__("Aucune filière ne correspond aux filtres sélectionnés.")}
				</div>`;
		}
		return html;
	}

	function build_level_row(filiere, level, idx, total) {
		let up_disabled = idx === 0;
		let down_disabled = idx === total - 1;
		return `
			<tr data-filiere="${frappe.utils.escape_html(filiere)}" data-level-name="${frappe.utils.escape_html(level.name)}">
				<td class="text-center drag-handle" style="cursor: grab;" title="${__("Glisser pour réordonner")}">
					<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="opacity: .45;">
						<circle cx="9" cy="6" r="1.6"/><circle cx="15" cy="6" r="1.6"/>
						<circle cx="9" cy="12" r="1.6"/><circle cx="15" cy="12" r="1.6"/>
						<circle cx="9" cy="18" r="1.6"/><circle cx="15" cy="18" r="1.6"/>
					</svg>
				</td>
				<td class="text-center">
					<span class="text-muted">${level.order}</span>
				</td>
				<td>
					<strong>${frappe.utils.escape_html(level.level)}</strong>
				</td>
				<td>
					<span class="indicator-pill ${cycle_badge_class(level.cycle)}">${frappe.utils.escape_html(level.cycle || "—")}</span>
				</td>
				<td>${frappe.utils.escape_html(level.coordonateur || "")}</td>
				<td>${frappe.utils.escape_html(level.calendrier || "")}</td>
				<td class="text-center">
					<button class="btn btn-sm btn-secondary move-up-btn" ${up_disabled ? "disabled" : ""}
						data-filiere="${frappe.utils.escape_html(filiere)}"
						data-level-name="${frappe.utils.escape_html(level.name)}"
						title="${__("Monter")}">
						<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M8 3l-5 5h10l-5-5z"/></svg>
					</button>
					<button class="btn btn-sm btn-secondary move-down-btn" ${down_disabled ? "disabled" : ""}
						data-filiere="${frappe.utils.escape_html(filiere)}"
						data-level-name="${frappe.utils.escape_html(level.name)}"
						title="${__("Descendre")}">
						<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M8 13l5-5H3l5 5z"/></svg>
					</button>
				</td>
			</tr>`;
	}

	function cycle_badge_class(cycle) {
		let map = {
			"Licence": "blue",
			"Master": "green",
			"BTS": "orange",
			"Doctorat": "purple",
		};
		return map[cycle] || "gray";
	}

	function bind_events() {
		$(".move-up-btn").click(function () {
			let filiere = $(this).data("filiere");
			let level_name = $(this).data("level-name");
			move_level(filiere, level_name, "up");
		});

		$(".move-down-btn").click(function () {
			let filiere = $(this).data("filiere");
			let level_name = $(this).data("level-name");
			move_level(filiere, level_name, "down");
		});

		$(".open-filiere-btn").click(function () {
			let filiere = $(this).data("filiere");
			frappe.set_route("Form", "Field of study", filiere);
		});

		$(".add-level-btn").click(function () {
			let filiere = $(this).data("filiere");
			show_add_level_dialog(filiere);
		});

		bind_drag_drop();
	}

	function bind_drag_drop() {
		if (typeof Sortable === "undefined") return;
		$(".levels-table tbody").each(function () {
			let tbody = this;
			if (tbody._sortable) return;
			tbody._sortable = new Sortable(tbody, {
				handle: ".drag-handle",
				draggable: "tr",
				animation: 150,
				ghostClass: "dnd-ghost",
				onEnd() {
					let filiere = $(tbody).data("filiere");
					let names = [];
					$(tbody).find("tr[data-level-name]").each(function () {
						names.push($(this).data("level-name"));
					});
					if (filiere && names.length) reorder_levels(filiere, names);
				},
			});
		});
	}

	function reorder_levels(filiere, level_names) {
		frappe.call({
			method: "udshed.api.reregistration.reorder_levels",
			args: { filiere, level_names },
			freeze: true,
			freeze_message: __("Réorganisation en cours..."),
			callback(r) {
				if (r.message && r.message.status) {
					frappe.show_alert({
						message: r.message.message,
						indicator: "green",
					});
					load_levels();
				}
			},
		});
	}

	function move_level(filiere, level_name, direction) {
		frappe.call({
			method: "udshed.api.reregistration.move_level",
			args: { filiere, level_name, direction },
			freeze: true,
			freeze_message: __("Réorganisation en cours..."),
			callback(r) {
				if (r.message && r.message.status) {
					frappe.show_alert({
						message: r.message.message,
						indicator: "green",
					});
					load_levels();
				}
			},
		});
	}

	setup_filters();
	setup_primary_action();
	load_levels();
};
