frappe.pages["liste-des-inscriptions"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Liste des inscriptions",
		single_column: true,
	});

	let filter_filiere = null;
	let report_data = null;

	function esc(s) {
		return s == null ? "" : String(s).replace(/[&<>"']/g, c => ({
			"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
		}[c]));
	}

	function setup_filters() {
		page.add_field({
			fieldtype: "Link",
			label: "Filière",
			fieldname: "filiere",
			options: "Field of study",
			change() {
				filter_filiere = this.get_value();
				load_data();
			}
		});
	}

	function load_data() {
		frappe.call({
			method: "udshed.api.inscription.get_liste_inscriptions",
			args: { filiere: filter_filiere },
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
		render_section();
	}

	function section_header(title, count) {
		return `<div class="bureau-section-header">
			<span class="bureau-section-dot"></span>
			<h5>${esc(title)}</h5>
			<span class="bureau-count-badge">${count}</span>
		</div>`;
	}

	function stat_card(label, value, icon) {
		return `<div class="bureau-stat-card">
			<div class="bureau-stat-icon">${frappe.utils.icon(icon || "list", "md")}</div>
			<div>
				<div class="bureau-stat-value">${value}</div>
				<div class="bureau-stat-label">${esc(label)}</div>
			</div>
		</div>`;
	}

	function matches_search(row, q, keys) {
		if (!q) return true;
		q = q.toLowerCase();
		return keys.some(k => String(row[k] || "").toLowerCase().includes(q));
	}

	function search_box(placeholder) {
		return `<div class="bureau-search-wrap">
			<svg class="bureau-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<circle cx="11" cy="11" r="7"></circle>
				<line x1="21" y1="21" x2="16.65" y2="16.65"></line>
			</svg>
			<input type="text" class="bureau-search-input form-control" placeholder="${esc(placeholder)}">
			<div class="bureau-search-results"></div>
		</div>`;
	}

	function render_section() {
		let rows = report_data.rows || [];
		let container = $(`<div class="bureau-section" data-section="inscriptions"></div>`);
		container.append(section_header("Inscrits", rows.length));
		page.main.append(container);
		refresh_stats(container, rows);
		container.append(search_box("Rechercher un inscrit (matricule, nom, email, filière, niveau)…"));
		let $input = container.find(".bureau-search-input");
		$input.on("input", function () {
			update_results(container, rows, this.value);
		});
		$input.on("focus", function () {
			update_results(container, rows, this.value);
		});
	}

	function refresh_stats($sec, filtered) {
		let par_filiere = {};
		let par_niveau = {};
		filtered.forEach(r => {
			par_filiere[r.filiere_label] = (par_filiere[r.filiere_label] || 0) + 1;
			par_niveau[r.niveau] = (par_niveau[r.niveau] || 0) + 1;
		});
		let cards = `<div class="bureau-stats-row">
			${stat_card("Total inscrits", filtered.length, "users")}
			${Object.entries(par_filiere).map(([k, v]) => stat_card(`${k}`, v, "layers")).join("")}
		</div>
		<div class="bureau-stats-row">
			${Object.entries(par_niveau).map(([k, v]) => stat_card(`Niveau ${k}`, v, "graduation-cap")).join("")}
		</div>`;
		$sec.find(".bureau-stats-widget").remove();
		$sec.find(".bureau-search-wrap").before(`<div class="bureau-stats-widget">${cards}</div>`);
	}

	function update_results($sec, allRows, q) {
		let filtered = allRows.filter(r => matches_search(r, q, [
			"matricule", "nom_complet", "email", "phone",
			"filiere_label", "niveau"
		]));
		refresh_stats($sec, filtered);
		let $results = $sec.find(".bureau-search-results");
		$results.empty();
		let items = filtered.slice(0, 50).map((r, i) => `
			<div class="bureau-search-result" data-idx="${i}">
				<span class="bureau-result-name">${esc(r.matricule) || esc(r.nom_complet)} — ${esc(r.nom_complet)}</span>
				<span class="bureau-result-meta">${esc(r.filiere_label)} · ${esc(r.niveau)}</span>
			</div>`).join("");
		if (!q) {
			$results.hide();
		} else if (!filtered.length) {
			$results.html(`<div class="bureau-search-empty">Aucun inscrit trouvé</div>`).show();
		} else {
			$results.html(items).show();
		}
		$results.find(".bureau-search-result").on("click", function () {
			show_detail(filtered[parseInt($(this).attr("data-idx"), 10)]);
			$results.empty().hide();
		});
	}

	function detail_item(label, value) {
		return `<div class="bureau-detail-item">
			<div class="bureau-detail-label">${esc(label)}</div>
			<div class="bureau-detail-value">${value == null || value === "" ? "—" : esc(value)}</div>
		</div>`;
	}

	function show_detail(r) {
		if (!r) return;
		let dialog = new frappe.ui.Dialog({
			title: r.nom_complet || r.matricule,
			size: "large",
		});
		dialog.$body.append(`
			<div class="bureau-detail-section">
				<h6>Inscription</h6>
				<div class="bureau-detail-grid">
					${detail_item("Matricule", r.matricule)}
					${detail_item("Année académique", r.annee_academique)}
					${detail_item("Nom complet", r.nom_complet)}
					${detail_item("Email", r.email)}
					${detail_item("Téléphone", r.phone)}
					${detail_item("Filière", r.filiere_label)}
					${detail_item("Niveau", r.niveau)}
					${detail_item("Centre d'examen", r.examination_centre)}
					${detail_item("Numéro de dossier", r.name)}
				</div>
			</div>
			<div class="bureau-detail-actions">
				<button class="btn btn-primary btn-sm bureau-open-dossier">Ouvrir le dossier candidat</button>
			</div>`);
		dialog.$body.find(".bureau-open-dossier").on("click", function () {
			frappe.set_route("Form", "Session Inscription Candidate", r.name);
		});
		dialog.show();
	}

	$(document).on("click.listeInscriptions", function (e) {
		if (!$(e.target).closest(".bureau-search-wrap").length) {
			$(".bureau-search-results").empty().hide();
		}
	});

	setup_filters();
	load_data();
};
