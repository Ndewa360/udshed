frappe.pages["report-reinscription"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Rapports de réinscription",
		single_column: true,
	});

	let filters = { reinscription_session: null, filiere: null, statut: null };
	let report_data = null;

	const STATUTS = ["Validée"];
	const STATUT_COLORS = {
		"Validée": "green"
	};

	function esc(s) {
		return s == null ? "" : String(s).replace(/[&<>"']/g, c => ({
			"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
		}[c]));
	}

	function setup_filters() {
		page.add_field({
			fieldtype: "Link",
			label: "Session de réinscription",
			fieldname: "reinscription_session",
			options: "Session Reinscription",
			change() {
				filters.reinscription_session = this.get_value();
				load_report();
			}
		});

		page.add_field({
			fieldtype: "Link",
			label: "Filière",
			fieldname: "filiere",
			options: "Field of study",
			change() {
				filters.filiere = this.get_value();
				load_report();
			}
		});

		page.add_field({
			fieldtype: "Select",
			label: "Statut",
			fieldname: "statut",
			options: ["", ...STATUTS].join("\n"),
			change() {
				filters.statut = this.get_value() || null;
				load_report();
			}
		});

		page.set_primary_action(__("Exporter CSV"), export_csv, "download");
	}

	function load_report() {
		frappe.call({
			method: "udshed.api.reregistration.get_reregistration_report",
			args: filters,
			callback(r) {
				if (!r.message) return;
				report_data = r.message;
				render();
			}
		});
	}

	function render() {
		page.main.empty();
		if (!report_data) return;
		render_cards();
		render_breakdowns();
		render_table();
	}

	function statut_badge(s) {
		s = s || "Validée";
		return `<span class="indicator green">${esc(s)}</span>`;
	}

	function card(label, value, color) {
		return `<div class="col-sm-6 col-md-2">
			<div class="card mb-3">
				<div class="card-body text-center">
					<div class="h3 mb-1 ${color ? "text-" + color : ""}">${value}</div>
					<div class="text-muted small">${esc(label)}</div>
				</div>
			</div>
		</div>`;
	}

	function render_cards() {
		let d = report_data;
		let html = `<div class="row">
			${card("Total réinscriptions", d.total, "primary")}
			${card("Validées", d.par_statut["Validée"] || 0, "green")}
		</div>`;
		page.main.append(html);
	}

	function breakdown_table(title, data) {
		let entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1]);
		let rows = entries.map(([k, v]) =>
			`<tr><td>${esc(k)}</td><td class="text-right">${v}</td></tr>`
		).join("");
		let body = entries.length
			? rows
			: `<tr><td colspan="2" class="text-muted">Aucune donnée</td></tr>`;
		return `<div class="col-sm-12 col-md-6">
			<h6 class="text-muted mt-2">${esc(title)}</h6>
			<table class="table table-sm table-bordered">
				<thead><tr><th>Libellé</th><th class="text-right">Nombre</th></tr></thead>
				<tbody>${body}</tbody>
			</table>
		</div>`;
	}

	function render_breakdowns() {
		let html = `<div class="row">
			${breakdown_table("Répartition par filière", report_data.par_filiere)}
			${breakdown_table("Répartition par niveau", report_data.par_niveau)}
		</div>`;
		page.main.append(html);
	}

	function render_table() {
		let rows = report_data.rows.map(r => `<tr>
			<td>${esc(r.matricule)}</td>
			<td>${esc(r.nom_etudiant)}</td>
			<td>${esc(r.filiere_label)}</td>
			<td>${esc(r.niveau)}</td>
			<td>${esc(r.semestre)}</td>
			<td>${esc(r.academic_year)}</td>
			<td>${statut_badge(r.statut)}</td>
		</tr>`).join("");
		let body = rows
			|| `<tr><td colspan="7" class="text-center text-muted">Aucune réinscription</td></tr>`;
		page.main.append(`<div class="mt-3">
			<h6 class="text-muted">Détail des réinscriptions</h6>
			<div class="table-responsive">
				<table class="table table-sm table-bordered table-hover">
					<thead><tr>
						<th>Matricule</th>
						<th>Étudiant</th>
						<th>Filière</th>
						<th>Niveau</th>
						<th>Semestre</th>
						<th>Année</th>
						<th>Statut</th>
					</tr></thead>
					<tbody>${body}</tbody>
				</table>
			</div>
		</div>`);
	}

	function export_csv() {
		if (!report_data || !report_data.rows.length) {
			frappe.msgprint(__("Aucune donnée à exporter."));
			return;
		}
		let cols = ["matricule", "nom_etudiant", "filiere_label", "niveau", "semestre", "academic_year", "statut"];
		let lines = report_data.rows.map(r =>
			cols.map(c => `"${String(r[c] || "").replace(/"/g, '""')}"`).join(",")
		);
		let csv = cols.map(c => c.toUpperCase()).join(",") + "\n" + lines.join("\n");
		let blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
		let link = document.createElement("a");
		link.href = URL.createObjectURL(blob);
		link.download = `rapport_reinscriptions_${filters.reinscription_session || "toutes"}.csv`;
		link.click();
	}

	setup_filters();
	load_report();
};
