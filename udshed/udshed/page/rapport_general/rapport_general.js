frappe.pages["rapport-general"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Rapport général",
		single_column: true,
	});

	let filters = {
		reinscription_session: null,
		filiere: null,
		candidature_status: null,
		statut: null,
	};
	let report_data = null;

	const CANDIDATURE_STATUTS = [
		"En attente",
		"Dossier en cours d'examen",
		"Accepté",
		"Refusé",
		"Inscrit",
	];
	const REINSCRIPTION_STATUTS = ["Validée"];

	const QUICK_LINKS = [
		{ label: "Session Inscription", icon: "calendar", route: ["List", "Session Inscription"] },
		{ label: "Dossier candidats", icon: "users", route: ["List", "Session Inscription Candidate"] },
		{ label: "Sessions de Réinscription", icon: "calendar-check", route: ["List", "Session Reinscription"] },
		{ label: "Réinscriptions", icon: "file-check", route: ["List", "Academic Reregistration"] },
		{ label: "Gestion des Niveaux", icon: "layers", route: ["gestion-des-niveaux"] },
		{ label: "Rapports de réinscription", icon: "file-text", route: ["report-reinscription"] },
	];

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
			label: "Statut candidature",
			fieldname: "candidature_status",
			options: ["", ...CANDIDATURE_STATUTS].join("\n"),
			change() {
				filters.candidature_status = this.get_value() || null;
				load_report();
			}
		});

		page.add_field({
			fieldtype: "Select",
			label: "Statut réinscription",
			fieldname: "statut",
			options: ["", ...REINSCRIPTION_STATUTS].join("\n"),
			change() {
				filters.statut = this.get_value() || null;
				load_report();
			}
		});

		page.set_primary_action(__("Exporter CSV"), export_csv, "download");
	}

	function load_report() {
		frappe.call({
			method: "udshed.api.general_report.get_general_report",
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
		$(document).off("click.bureauReport").on("click.bureauReport", function (e) {
			if (!$(e.target).closest(".bureau-search-wrap").length) {
				$(".bureau-search-results").empty().hide();
			}
		});
		render_quick_links();
		render_inscription_section();
		render_reinscription_section();
	}

	function render_quick_links() {
		let buttons = QUICK_LINKS.map(l => `
			<button class="bureau-quick-link" data-route='${esc(JSON.stringify(l.route))}'>
				${frappe.utils.icon(l.icon, "md")}
				<span>${esc(l.label)}</span>
			</button>`).join("");
		page.main.append(`<div class="bureau-quick-links">${buttons}</div>`);
		page.main.find(".bureau-quick-link").on("click", function () {
			let route = JSON.parse($(this).attr("data-route"));
			frappe.set_route(route);
		});
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

	function build_stats(cards_html) {
		return `<div class="bureau-stats-widget"><div class="bureau-stats-row">${cards_html}</div></div>`;
	}

	function render_inscription_section() {
		let ins = report_data.inscriptions || {};
		let rows = ins.rows || [];
		let container = $(`<div class="bureau-section" data-section="inscription"></div>`);
		container.append(section_header("Inscriptions", rows.length));
		page.main.append(container);
		refresh_inscription_stats(container, rows);
		container.append(search_box("Rechercher un candidat (nom, email, téléphone, filière, statut)…"));
		let $input = container.find(".bureau-search-input");
		$input.on("input", function () {
			update_inscription(container, rows, this.value);
		});
		$input.on("focus", function () {
			update_inscription(container, rows, this.value);
		});
	}

	function refresh_inscription_stats($sec, filtered) {
		let statut_counts = {};
		filtered.forEach(r => {
			let s = r.candidature_status || "En attente";
			statut_counts[s] = (statut_counts[s] || 0) + 1;
		});
		let cards = `${stat_card("Total inscriptions", filtered.length, "users")}`
			+ Object.entries(statut_counts).map(([k, v]) => stat_card(k, v)).join("");
		$sec.find(".bureau-stats-widget").remove();
		$sec.find(".bureau-search-wrap").before(build_stats(cards));
	}

	function update_inscription($sec, allRows, q) {
		let filtered = allRows.filter(r => matches_search(r, q, [
			"nom_complet", "email", "phone", "filiere_label",
			"niveau", "examination_centre", "candidature_status"
		]));
		refresh_inscription_stats($sec, filtered);
		let $results = $sec.find(".bureau-search-results");
		$results.empty();
		let items = filtered.slice(0, 50).map(r => `
			<div class="bureau-search-result" data-candidate="${esc(r.name)}">
				<span class="bureau-result-name">${esc(r.nom_complet)}</span>
				<span class="bureau-result-meta">${esc(r.filiere_label)} · ${esc(r.niveau)} · ${esc(r.candidature_status)}</span>
			</div>`).join("");
		if (!q) {
			$results.hide();
		} else if (!filtered.length) {
			$results.html(`<div class="bureau-search-empty">Aucun candidat trouvé</div>`).show();
		} else {
			$results.html(items).show();
		}
		$results.find(".bureau-search-result").on("click", function () {
			show_candidate_detail($(this).attr("data-candidate"));
			$results.empty().hide();
		});
	}

	function render_reinscription_section() {
		let re = report_data.reinscriptions || {};
		let rows = re.rows || [];
		let container = $(`<div class="bureau-section" data-section="reinscription"></div>`);
		container.append(section_header("Réinscriptions", rows.length));
		page.main.append(container);
		refresh_reinscription_stats(container, rows);
		container.append(search_box("Rechercher un étudiant (matricule, nom, filière, statut)…"));
		let $input = container.find(".bureau-search-input");
		$input.on("input", function () {
			update_reinscription(container, rows, this.value);
		});
		$input.on("focus", function () {
			update_reinscription(container, rows, this.value);
		});
	}

	function refresh_reinscription_stats($sec, filtered) {
		let statut_counts = {};
		filtered.forEach(r => {
			let s = r.statut || "Validée";
			statut_counts[s] = (statut_counts[s] || 0) + 1;
		});
		let cards = `${stat_card("Total réinscriptions", filtered.length, "file-check")}`
			+ Object.entries(statut_counts).map(([k, v]) => stat_card(k, v)).join("");
		$sec.find(".bureau-stats-widget").remove();
		$sec.find(".bureau-search-wrap").before(build_stats(cards));
	}

	function update_reinscription($sec, allRows, q) {
		let filtered = allRows.filter(r => matches_search(r, q, [
			"matricule", "nom_etudiant", "filiere_label", "niveau",
			"semestre", "academic_year", "statut", "email"
		]));
		refresh_reinscription_stats($sec, filtered);
		let $results = $sec.find(".bureau-search-results");
		$results.empty();
		let items = filtered.slice(0, 50).map((r, i) => `
			<div class="bureau-search-result" data-reinscription="${esc(r.name)}" data-idx="${i}">
				<span class="bureau-result-name">${esc(r.nom_etudiant) || esc(r.matricule)}</span>
				<span class="bureau-result-meta">${esc(r.matricule)} · ${esc(r.filiere_label)} · ${esc(r.statut)}</span>
			</div>`).join("");
		if (!q) {
			$results.hide();
		} else if (!filtered.length) {
			$results.html(`<div class="bureau-search-empty">Aucun étudiant trouvé</div>`).show();
		} else {
			$results.html(items).show();
		}
		$results.find(".bureau-search-result").on("click", function () {
			show_reinscription_detail(filtered[parseInt($(this).attr("data-idx"), 10)]);
			$results.empty().hide();
		});
	}

	function show_reinscription_detail(r) {
		if (!r) return;
		let dialog = new frappe.ui.Dialog({
			title: r.nom_etudiant || r.matricule,
			size: "large",
		});
		dialog.$body.append(`
			<div class="bureau-detail-section">
				<h6>${__("Réinscription")}</h6>
				<div class="bureau-detail-grid">
					${detail_item(__("Matricule"), r.matricule)}
					${detail_item(__("Étudiant"), r.nom_etudiant)}
					${detail_item(__("Filière"), r.filiere_label)}
					${detail_item(__("Niveau"), r.niveau)}
					${detail_item(__("Semestre"), r.semestre)}
					${detail_item(__("Année académique"), r.academic_year)}
					${detail_item(__("Statut"), r.statut)}
					${detail_item(__("Email"), r.email)}
				</div>
			</div>`);
		dialog.show();
	}

	function detail_item(label, value) {
		return `<div class="bureau-detail-item">
			<div class="bureau-detail-label">${esc(label)}</div>
			<div class="bureau-detail-value">${value == null || value === "" ? "—" : esc(value)}</div>
		</div>`;
	}

	function detail_doc_link(label, url) {
		let content = url
			? `<a href="${esc(url)}" target="_blank">${__("Voir le document")}</a>`
			: "—";
		return `<div class="bureau-detail-item">
			<div class="bureau-detail-label">${esc(label)}</div>
			<div class="bureau-detail-value">${content}</div>
		</div>`;
	}

	function show_candidate_detail(name) {
		if (!name) return;
		frappe.call({
			method: "udshed.udshed.doctype.session_inscription_candidate.session_inscription_candidate.get_candidate_detail",
			args: { name },
			callback(r) {
				if (!r.message) return;
				let d = r.message;

				let choix_rows = (d.choix_de_formation || []).map(c => `<tr>
					<td>${esc(c.choix)}</td>
					<td>${esc(c.filiere)}</td>
					<td>${esc(c.niveau)}</td>
				</tr>`).join("");
				let choix_html = (d.choix_de_formation || []).length
					? `<table class="table table-sm table-bordered">
						<thead><tr><th>${__("Choix")}</th><th>${__("Filière")}</th><th>${__("Niveau")}</th></tr></thead>
						<tbody>${choix_rows}</tbody>
					</table>`
					: "";

				let diplomes_rows = (d.diplome_formation || []).map(x => `<tr>
					<td>${esc(x.diplome)}</td>
					<td>${esc(x.year)}</td>
					<td>${esc(x.serie)}</td>
					<td>${esc(x.lieu)}</td>
					<td>${esc(x.mention)}</td>
				</tr>`).join("");
				let diplomes_html = (d.diplome_formation || []).length
					? `<table class="table table-sm table-bordered">
						<thead><tr><th>${__("Diplôme")}</th><th>${__("Année")}</th><th>${__("Série")}</th><th>${__("Lieu")}</th><th>${__("Mention")}</th></tr></thead>
						<tbody>${diplomes_rows}</tbody>
					</table>`
					: "";

				let html = `
					<div class="bureau-detail-section">
						<h6>${__("Statut du dossier")}</h6>
						<div class="bureau-detail-grid">
							<div class="bureau-detail-item">
								<div class="bureau-detail-label">${__("Statut")}</div>
								<div class="bureau-detail-value"><span class="bureau-status-pill">${esc(d.candidature_status)}</span></div>
							</div>
							${detail_item(__("Dernière mise à jour"), d.status_updated_on)}
							${detail_item(__("Motif / Commentaire"), d.status_comment)}
							${detail_item(__("Soumis le"), d.submitted_on)}
						</div>
					</div>
					<div class="bureau-detail-section">
						<h6>${__("Informations personnelles")}</h6>
						<div class="bureau-detail-grid">
							${detail_item(__("Nom complet"), d.full_name)}
							${detail_item(__("Sexe"), d.sexe)}
							${detail_item(__("Date de naissance"), d.birthdate)}
							${detail_item(__("Lieu de naissance"), d.birth_place)}
							${detail_item(__("Nationalité"), d.nationality)}
							${detail_item(__("Religion"), d.religion)}
							${detail_item(__("Situation matrimoniale"), d.marital_status)}
							${detail_item(__("Situation d'emploi"), d.employment_status)}
							${detail_item(__("Langue"), d.language)}
							${detail_item(__("Handicap"), d.handicap)}
							${detail_item(__("Téléphone"), d.phone)}
							${detail_item(__("Email"), d.email)}
							${detail_item(__("Téléphone parent"), d.parent_phone)}
							${detail_item(__("Email parent"), d.email_parent)}
							${detail_item(__("Ville"), d.home_city)}
						</div>
					</div>
					<div class="bureau-detail-section">
						<h6>${__("Père")}</h6>
						<div class="bureau-detail-grid">
							${detail_item(__("Nom et prénom(s)"), d.father_name)}
							${detail_item(__("Téléphone"), d.father_phone)}
							${detail_item(__("Profession"), d.father_profession)}
							${detail_item(__("Email"), d.father_email)}
							${detail_item(__("Ville de résidence"), d.father_city)}
							${detail_item(__("Pays de résidence"), d.father_country)}
						</div>
					</div>
					<div class="bureau-detail-section">
						<h6>${__("Mère")}</h6>
						<div class="bureau-detail-grid">
							${detail_item(__("Nom et prénom(s)"), d.mother_name)}
							${detail_item(__("Téléphone"), d.mother_phone)}
							${detail_item(__("Profession"), d.mother_profession)}
							${detail_item(__("Email"), d.mother_email)}
							${detail_item(__("Ville de résidence"), d.mother_city)}
							${detail_item(__("Pays de résidence"), d.mother_country)}
						</div>
					</div>
					<div class="bureau-detail-section">
						<h6>${__("Sponsor / Financeur")}</h6>
						<div class="bureau-detail-grid">
							${detail_item(__("Nom et prénom(s)"), d.sponsor_name)}
							${detail_item(__("Téléphone"), d.sponsor_phone)}
							${detail_item(__("Profession"), d.sponsor_profession)}
							${detail_item(__("Email"), d.sponsor_email)}
							${detail_item(__("Ville de résidence"), d.sponsor_city)}
							${detail_item(__("Pays de résidence"), d.sponsor_country)}
						</div>
					</div>
					<div class="bureau-detail-section">
						<h6>${__("Informations académiques")}</h6>
						<div class="bureau-detail-grid">
							${detail_item(__("Filière"), d.filiere_label)}
							${detail_item(__("Niveau"), d.niveau)}
							${detail_item(__("Centre d'examen"), d.examination_centre)}
							${detail_item(__("Dernier établissement fréquenté"), d.last_establishment)}
							${detail_item(__("Diplôme d'entrée"), d.entry_diploma)}
							${detail_item(__("Matricule du diplôme"), d.diploma_matricule)}
						</div>
					</div>
					${choix_html ? `<div class="bureau-detail-section"><h6>${__("Choix de formation")}</h6>${choix_html}</div>` : ""}
					${diplomes_html ? `<div class="bureau-detail-section"><h6>${__("Diplômes")}</h6>${diplomes_html}</div>` : ""}
					<div class="bureau-detail-section">
						<h6>${__("Informations complémentaires")}</h6>
						<div class="bureau-detail-grid">
							${detail_item(__("Activité(s) sportive(s)"), d.sports_activities)}
							${detail_item(__("Activité(s) associative(s)"), d.associative_activities)}
							${detail_item(__("Activité(s) culturelle(s)"), d.cultural_activities)}
							${detail_item(__("Connaissances informatiques"), d.it_knowledge)}
						</div>
					</div>
					<div class="bureau-detail-section">
						<h6>${__("Pièces du dossier")}</h6>
						<div class="bureau-detail-grid">
							${detail_doc_link(__("Acte de naissance"), d.birth_certificate)}
							${detail_doc_link(__("Copie du diplôme d'accès"), d.access_diploma_copy)}
							${detail_doc_link(__("Photo d'identité"), d.id_photo)}
							${detail_doc_link(__("Reçu de dépôt"), d.remittance_receipt)}
						</div>
					</div>`;

				let dialog = new frappe.ui.Dialog({
					title: d.full_name || name,
					size: "large",
				});
				dialog.$body.append(html);
				dialog.show();
			}
		});
	}

	function export_csv() {
		let ins = (report_data && report_data.inscriptions && report_data.inscriptions.rows) || [];
		let re = (report_data && report_data.reinscriptions && report_data.reinscriptions.rows) || [];
		if (!ins.length && !re.length) {
			frappe.msgprint(__("Aucune donnée à exporter."));
			return;
		}
		let cols = ["Type", "Nom", "Téléphone", "Email/Matricule", "Filière", "Niveau", "Semestre", "Année", "Centre", "Soumis le", "Statut"];
		let lines = [];

		ins.forEach(r => {
			lines.push([
				"Inscription", r.nom_complet, r.phone, r.email, r.filiere_label,
				r.niveau, "", "", r.examination_centre,
				frappe.datetime.str_to_user(r.creation || ""), r.candidature_status
			]);
		});
		re.forEach(r => {
			lines.push([
				"Réinscription", r.nom_etudiant, "", r.matricule, r.filiere_label,
				r.niveau, r.semestre, r.academic_year, "", "", r.statut
			]);
		});

		let csv_lines = lines.map(cells =>
			cells.map(c => `"${String(c == null ? "" : c).replace(/"/g, '""')}"`).join(",")
		);
		let csv = cols.map(c => `"${c}"`).join(",") + "\n" + csv_lines.join("\n");
		let blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
		let link = document.createElement("a");
		link.href = URL.createObjectURL(blob);
		link.download = `bureau_inscriptions_reinscriptions.csv`;
		link.click();
	}

	setup_filters();
	load_report();
};
