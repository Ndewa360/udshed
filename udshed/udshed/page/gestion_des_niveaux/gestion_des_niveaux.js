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
			method: "frappe.client.get",
			args: { doctype: "Field of study", name: filiere },
			callback(r) {
				let doc = r.message;
				let existing_levels = (doc.field_of_study_level || []).map(l => l.level);
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
						let new_row = doc.append("field_of_study_level", {
							level: values.level,
							order: (doc.field_of_study_level.length || 0) + 1,
							coordonateur: values.coordonateur,
							calendrier: values.calendrier || "Defaut",
							gestionnaire_de_planning: values.gestionnaire_de_planning,
						});
						frappe.call({
							method: "frappe.client.save",
							args: { doc: doc },
							freeze: true,
							freeze_message: __("Ajout du niveau..."),
							callback(r2) {
								d.hide();
								frappe.show_alert({
									message: __("Niveau {0} ajouté à {1}", [values.level, filiere]),
									indicator: "green",
								});
								load_levels();
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
		let html = build_table_html();
		let container = page.body;
		container.innerHTML =
			'<div class="levels-management-container" style="padding: 15px;">' +
			html +
			"</div>";
		bind_events();
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
		all_data.forEach((fos) => {
			let levels = fos.levels || [];
			html += `
				<div class="card mb-4">
					<div class="card-header d-flex justify-content-between align-items-center">
						<div>
							<strong>${frappe.utils.escape_html(fos.filiere_label)}</strong>
							<span class="text-muted ml-2">(${frappe.utils.escape_html(fos.filiere_name)})</span>
							<span class="badge badge-info ml-2">${levels.length} niveau${levels.length > 1 ? "x" : ""}</span>
						</div>
						<div>
							<button class="btn btn-sm btn-outline-primary add-level-btn mr-2"
								data-filiere="${frappe.utils.escape_html(fos.filiere_name)}">
								${__("+ Ajouter")}
							</button>
							<button class="btn btn-sm btn-outline-secondary open-filiere-btn"
								data-filiere="${frappe.utils.escape_html(fos.filiere_name)}">
								${__("Modifier la filière")}
							</button>
						</div>
					</div>
					<div class="card-body p-0">
						<table class="table table-hover mb-0">
							<thead class="thead-light">
								<tr>
									<th style="width: 60px;">${__("Ordre")}</th>
									<th>${__("Niveau")}</th>
									<th>${__("Coordonateur")}</th>
									<th>${__("Calendrier")}</th>
									<th style="width: 120px;">${__("Actions")}</th>
								</tr>
							</thead>
							<tbody>
								${levels.length ? levels.map((l, idx) => build_level_row(fos.filiere_name, l, idx, levels.length)).join("") : `
									<tr>
										<td colspan="5" class="text-center text-muted" style="padding: 30px;">
											${__("Aucun niveau. Cliquez sur « + Ajouter » pour en créer un.")}
										</td>
									</tr>`}
							</tbody>
						</table>
					</div>
				</div>`;
		});
		return html;
	}

	function build_level_row(filiere, level, idx, total) {
		let up_disabled = idx === 0;
		let down_disabled = idx === total - 1;
		return `
			<tr data-filiere="${frappe.utils.escape_html(filiere)}" data-level-name="${frappe.utils.escape_html(level.name)}">
				<td class="text-center">
					<span class="badge badge-secondary badge-order">${level.order}</span>
				</td>
				<td>
					<strong>${frappe.utils.escape_html(level.level)}</strong>
				</td>
				<td>${frappe.utils.escape_html(level.coordonateur || "")}</td>
				<td>${frappe.utils.escape_html(level.calendrier || "")}</td>
				<td class="text-center">
					<button class="btn btn-sm btn-outline-secondary move-up-btn" ${up_disabled ? "disabled" : ""}
						data-filiere="${frappe.utils.escape_html(filiere)}"
						data-level-name="${frappe.utils.escape_html(level.name)}"
						title="${__("Monter")}">
						<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M8 3l-5 5h10l-5-5z"/></svg>
					</button>
					<button class="btn btn-sm btn-outline-secondary move-down-btn" ${down_disabled ? "disabled" : ""}
						data-filiere="${frappe.utils.escape_html(filiere)}"
						data-level-name="${frappe.utils.escape_html(level.name)}"
						title="${__("Descendre")}">
						<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M8 13l5-5H3l5 5z"/></svg>
					</button>
				</td>
			</tr>`;
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
