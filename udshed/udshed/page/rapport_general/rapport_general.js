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

	function breakdown_table(title, data) {
		let entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1]);
		let rows = entries.map(([k, v]) =>
			`<tr><td>${esc(k)}</td><td class="text-right">${v}</td></tr>`
		).join("");
		let body = entries.length
			? rows
			: `<tr><td colspan="2" class="text-muted">Aucune donnée</td></tr>`;
		return `<div class="col-sm-12 col-md-6">
			<table class="table table-sm table-bordered">
				<thead><tr><th>${esc(title)}</th><th class="text-right">Nombre</th></tr></thead>
				<tbody>${body}</tbody>
			</table>
		</div>`;
	}

	function status_badge(s) {
		return `<span class="bureau-status-badge">${esc(s)}</span>`;
	}

	function render_inscription_section() {
		let ins = report_data.inscriptions || {};
		let total = ins.total || 0;
		let cards = `<div class="bureau-stats-row">
			${stat_card("Total inscriptions", total, "users")}
			${(ins.par_statut ? Object.entries(ins.par_statut) : []).map(([k, v]) =>
				stat_card(k, v)
			).join("")}
		</div>`;
		let breakdowns = `<div class="row">
			${breakdown_table("Répartition par filière", ins.par_filiere)}
			${breakdown_table("Répartition par niveau", ins.par_niveau)}
		</div>`;
		let rows = (ins.rows || []).map(r => `<tr>
			<td><button class="bureau-candidate-link" data-candidate="${esc(r.name)}">${esc(r.nom_complet)}</button></td>
			<td>${esc(r.phone)}</td>
			<td>${esc(r.email)}</td>
			<td>${esc(r.filiere_label)}</td>
			<td>${esc(r.niveau)}</td>
			<td>${esc(r.examination_centre)}</td>
			<td>${frappe.datetime.str_to_user(r.creation || "")}</td>
			<td>${status_badge(r.candidature_status)}</td>
		</tr>`).join("");
		let body = rows
			|| `<tr><td colspan="8" class="text-center text-muted">Aucune inscription</td></tr>`;
		page.main.append(section_header("Inscriptions", total)
			+ cards + breakdowns + `<div class="table-responsive mt-2">
				<table class="table table-sm table-bordered table-hover">
					<thead><tr>
						<th>Candidat</th>
						<th>Téléphone</th>
						<th>Email</th>
						<th>Filière</th>
						<th>Niveau</th>
						<th>Centre d'examen</th>
						<th>Soumis le</th>
						<th>Statut</th>
					</tr></thead>
					<tbody>${body}</tbody>
				</table>
			</div>`);
		page.main.find(".bureau-candidate-link").on("click", function () {
			show_candidate_detail($(this).attr("data-candidate"));
		});
	}

	function render_reinscription_section() {
		let re = report_data.reinscriptions || {};
		let total = re.total || 0;
		let cards = `<div class="bureau-stats-row">
			${stat_card("Total réinscriptions", total, "file-check")}
			${(re.par_statut ? Object.entries(re.par_statut) : []).map(([k, v]) =>
				stat_card(k, v)
			).join("")}
		</div>`;
		let breakdowns = `<div class="row">
			${breakdown_table("Répartition par filière", re.par_filiere)}
			${breakdown_table("Répartition par niveau", re.par_niveau)}
		</div>`;
		let rows = (re.rows || []).map(r => `<tr>
			<td>${esc(r.matricule)}</td>
			<td>${esc(r.nom_etudiant)}</td>
			<td>${esc(r.filiere_label)}</td>
			<td>${esc(r.niveau)}</td>
			<td>${esc(r.semestre)}</td>
			<td>${esc(r.academic_year)}</td>
			<td>${status_badge(r.statut)}</td>
		</tr>`).join("");
		let body = rows
			|| `<tr><td colspan="7" class="text-center text-muted">Aucune réinscription</td></tr>`;
		page.main.append(section_header("Réinscriptions", total)
			+ cards + breakdowns + `<div class="table-responsive mt-2">
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
			</div>`);
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
