frappe.pages["liste-des-inscriptions"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Liste des inscriptions",
		single_column: true,
	});

	const API = "udshed.api.inscription_import_export";
	let filters = { filiere: null, annee_academique: null, niveau: null, statut: null };
	let current_query = "";
	let report_data = null;
	let actions_ready = false;
	const SEARCH_KEYS = [
		"matricule", "nom_complet", "email", "phone",
		"filiere_label", "niveau", "father_name", "mother_name", "sponsor_name"
	];

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
				filters.filiere = this.get_value();
				load_data();
			}
		});
		page.add_field({
			fieldtype: "Link",
			label: "Année académique",
			fieldname: "annee_academique",
			options: "Academic Year",
			change() {
				filters.annee_academique = this.get_value();
				load_data();
			}
		});
		page.add_field({
			fieldtype: "Data",
			label: "Niveau",
			fieldname: "niveau",
			change() {
				filters.niveau = this.get_value();
				load_data();
			}
		});
		page.add_field({
			fieldtype: "Select",
			label: "Statut",
			fieldname: "statut",
			options: ["", "Inscrit", "En attente de matricule", "Sans inscription académique"],
			change() {
				filters.statut = this.get_value();
				load_data();
			}
		});
	}

	function setup_actions() {
		if (actions_ready || !report_data) return;
		actions_ready = true;

		if (report_data.peut_exporter) {
			page.add_inner_button(__("Excel (.xlsx)"), () => export_list("xlsx"), __("Exporter"));
			page.add_inner_button(__("CSV (.csv)"), () => export_list("csv"), __("Exporter"));
		}
		if (report_data.peut_gerer) {
			page.add_inner_button(__("Importer un fichier"), open_import_dialog, __("Importer"));
			page.add_inner_button(__("Télécharger le modèle (.xlsx)"), () => download_template("xlsx"), __("Importer"));
			page.add_inner_button(__("Télécharger le modèle (.csv)"), () => download_template("csv"), __("Importer"));
			page.set_primary_action(__("Ajouter un étudiant"), () => {
				frappe.new_doc("Inscription Academique");
			}, "add");
		}
	}

	function load_data() {
		frappe.call({
			method: "udshed.api.inscription.get_liste_inscriptions",
			args: filters,
			callback(r) {
				if (!r.message) return;
				report_data = r.message;
				setup_actions();
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
		$input.val(current_query);
		$input.on("input", function () {
			update_results(container, rows, this.value);
		});
		$input.on("focus", function () {
			update_results(container, rows, this.value);
		});
		if (current_query) refresh_stats(container, rows.filter(r => matches_search(r, current_query, SEARCH_KEYS)));
	}

	function refresh_stats($sec, filtered) {
		let par_filiere = {};
		let par_niveau = {};
		filtered.forEach(r => {
			par_filiere[r.filiere_label] = (par_filiere[r.filiere_label] || 0) + 1;
			par_niveau[r.niveau] = (par_niveau[r.niveau] || 0) + 1;
		});
		let en_attente = filtered.filter(r => r.statut === "En attente de matricule").length;
		let cards = `<div class="bureau-stats-row">
			${stat_card("Total inscrits", filtered.length, "users")}
			${en_attente ? stat_card("En attente de matricule", en_attente, "clock") : ""}
			${Object.entries(par_filiere).map(([k, v]) => stat_card(`${k}`, v, "layers")).join("")}
		</div>
		<div class="bureau-stats-row">
			${Object.entries(par_niveau).map(([k, v]) => stat_card(`Niveau ${k}`, v, "graduation-cap")).join("")}
		</div>`;
		$sec.find(".bureau-stats-widget").remove();
		$sec.find(".bureau-search-wrap").before(`<div class="bureau-stats-widget">${cards}</div>`);
	}

	function update_results($sec, allRows, q) {
		current_query = q || "";
		let filtered = allRows.filter(r => matches_search(r, q, SEARCH_KEYS));
		refresh_stats($sec, filtered);
		let $results = $sec.find(".bureau-search-results");
		$results.empty();
		let items = filtered.slice(0, 50).map((r, i) => `
			<div class="bureau-search-result" data-idx="${i}">
				<span class="bureau-result-name">${esc(r.matricule) || esc(r.nom_complet)} — ${esc(r.nom_complet)}</span>
				<span class="bureau-result-meta">${esc(r.filiere_label)} · ${esc(r.niveau)}${r.statut !== "Inscrit" ? " · " + esc(r.statut) : ""}</span>
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
		let actions = [];
		if (r.dossier_origine) {
			actions.push(`<button class="btn btn-default btn-sm bureau-open-dossier">Ouvrir le dossier candidat</button>`);
		}
		if (r.inscription) {
			actions.push(`<button class="btn btn-default btn-sm bureau-open-inscription">Ouvrir l'inscription</button>`);
			if (r.matricule) {
				actions.push(`<button class="btn btn-primary btn-sm bureau-fiche">Télécharger la fiche</button>`);
			} else if (!r.dossier_origine && report_data.peut_gerer) {
				actions.push(`<button class="btn btn-primary btn-sm bureau-generer">Générer le matricule et la fiche</button>`);
			}
		}
		dialog.$body.append(`
			<div class="bureau-detail-section">
				<h6>Inscription</h6>
				<div class="bureau-detail-grid">
					${detail_item("Matricule", r.matricule)}
					${detail_item("Statut", r.statut)}
					${detail_item("Année académique", r.annee_academique)}
					${detail_item("Nom complet", r.nom_complet)}
					${detail_item("Email", r.email)}
					${detail_item("Téléphone", r.phone)}
					${detail_item("Filière", r.filiere_label)}
					${detail_item("Niveau", r.niveau)}
					${detail_item("Origine", r.origine)}
					${detail_item("Centre d'examen", r.examination_centre)}
					${detail_item("Numéro de dossier", r.dossier_origine)}
				</div>
			</div>
			<div class="bureau-detail-section">
				<h6>Parents / Tuteur</h6>
				<div class="bureau-detail-grid">
					${detail_item("Père — Nom", r.father_name)}
					${detail_item("Père — Téléphone", r.father_phone)}
					${detail_item("Père — Profession", r.father_profession)}
					${detail_item("Père — Email", r.father_email)}
					${detail_item("Père — Ville", r.father_city)}
					${detail_item("Père — Pays", r.father_country)}
					${detail_item("Mère — Nom", r.mother_name)}
					${detail_item("Mère — Téléphone", r.mother_phone)}
					${detail_item("Mère — Profession", r.mother_profession)}
					${detail_item("Mère — Email", r.mother_email)}
					${detail_item("Mère — Ville", r.mother_city)}
					${detail_item("Mère — Pays", r.mother_country)}
					${detail_item("Sponsor — Nom", r.sponsor_name)}
					${detail_item("Sponsor — Téléphone", r.sponsor_phone)}
					${detail_item("Sponsor — Profession", r.sponsor_profession)}
					${detail_item("Sponsor — Email", r.sponsor_email)}
					${detail_item("Sponsor — Ville", r.sponsor_city)}
					${detail_item("Sponsor — Pays", r.sponsor_country)}
					${detail_item("Contact parent", r.parent_phone)}
					${detail_item("Email parent", r.email_parent)}
				</div>
			</div>
			<div class="bureau-detail-actions">${actions.join(" ")}</div>`);
		dialog.$body.find(".bureau-open-dossier").on("click", function () {
			frappe.set_route("Form", "Session Inscription Candidate", r.dossier_origine);
		});
		dialog.$body.find(".bureau-open-inscription").on("click", function () {
			frappe.set_route("Form", "Inscription Academique", r.inscription);
		});
		dialog.$body.find(".bureau-fiche").on("click", function () {
			window.open(fiche_url(r.inscription), "_blank");
		});
		dialog.$body.find(".bureau-generer").on("click", function () {
			frappe.call({
				method: `${API}.generer_matricule_et_fiche`,
				args: { inscription: r.inscription },
				freeze: true,
				freeze_message: __("Génération du matricule…"),
				callback(res) {
					if (!res.message) return;
					frappe.show_alert({
						message: __("Matricule attribué : {0}", [res.message.matricule]),
						indicator: "green",
					});
					dialog.hide();
					window.open(res.message.pdf_url, "_blank");
					load_data();
				},
			});
		});
		dialog.show();
	}

	function fiche_url(inscription) {
		return "/api/method/udshed.api.inscription.telecharger_fiche_inscription?nom="
			+ encodeURIComponent(inscription);
	}

	// ------------------------------------------------------------------ //
	//  Export / modèle / import
	// ------------------------------------------------------------------ //
	function download(method, args) {
		let params = Object.entries(args)
			.filter(([, v]) => v != null && v !== "")
			.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
			.join("&");
		window.open(`/api/method/${API}.${method}?${params}`, "_blank");
	}

	function export_list(format) {
		download("exporter_inscriptions", { format, ...filters, recherche: current_query });
	}

	function download_template(format) {
		download("telecharger_modele_import", { format });
	}

	const STATUT_INDICATOR = {
		"Importée": "green",
		"À importer": "blue",
		"Ignorée": "orange",
		"Rejetée": "red",
	};

	function render_bilan(bilan) {
		let titre = bilan.valide ? __("Bilan de l'importation") : __("Vérification du fichier (rien n'a encore été enregistré)");
		let ignorees = (bilan.colonnes_ignorees || []).length
			? `<p class="text-muted small">${__("Colonnes non reconnues (ignorées)")} : ${esc(bilan.colonnes_ignorees.join(", "))}</p>`
			: "";
		let lignes = (bilan.lignes || []).map(l => `
			<tr>
				<td>${l.ligne}</td>
				<td><span class="indicator-pill ${STATUT_INDICATOR[l.statut] || "gray"}">${esc(l.statut)}</span></td>
				<td>${esc(l.matricule)}</td>
				<td>${esc(l.nom)}</td>
				<td>${esc(l.motif)}</td>
			</tr>`).join("");
		return `
			<h6 class="mt-3">${esc(titre)}</h6>
			<div class="bureau-stats-row">
				${stat_card(bilan.valide ? __("Importées") : __("À importer"), bilan.importees, "check")}
				${stat_card(__("Ignorées"), bilan.ignorees, "skip")}
				${stat_card(__("Rejetées"), bilan.rejetees, "close")}
			</div>
			${ignorees}
			<div style="max-height: 360px; overflow: auto;">
				<table class="table table-bordered table-sm">
					<thead><tr>
						<th>${__("Ligne")}</th><th>${__("Statut")}</th><th>${__("Matricule")}</th>
						<th>${__("Étudiant")}</th><th>${__("Motif")}</th>
					</tr></thead>
					<tbody>${lignes}</tbody>
				</table>
			</div>`;
	}

	function open_import_dialog() {
		let etape = "verifier";
		let bilan = null;

		// Déclaré avant construction : les onchange peuvent se déclencher pendant
		// l'initialisation des valeurs par défaut.
		let d = null;
		d = new frappe.ui.Dialog({
			title: __("Importer des étudiants"),
			size: "extra-large",
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "aide",
					options: `<p class="text-muted">${__("Utilisez le modèle d'importation (menu Importer). Le fichier est d'abord vérifié sans rien enregistrer ; vous confirmez ensuite l'importation.")}</p>`,
				},
				{
					fieldtype: "Attach",
					fieldname: "fichier",
					label: __("Fichier Excel (.xlsx) ou CSV (.csv)"),
					reqd: 1,
					onchange() { reset(); },
				},
				{
					fieldtype: "Link",
					fieldname: "annee_academique",
					label: __("Année académique (si absente du fichier)"),
					options: "Academic Year",
					default: report_data.annee_courante,
					onchange() { reset(); },
				},
				{
					fieldtype: "Check",
					fieldname: "envoyer_email",
					label: __("Envoyer l'e-mail du matricule aux étudiants importés"),
					default: 1,
				},
				{ fieldtype: "HTML", fieldname: "bilan" },
			],
			primary_action_label: __("Vérifier le fichier"),
			primary_action: on_primary,
			secondary_action_label: __("Télécharger le bilan (CSV)"),
			secondary_action() {
				if (!bilan) {
					frappe.msgprint(__("Vérifiez d'abord le fichier."));
					return;
				}
				frappe.tools.downloadify(
					[[__("Ligne"), __("Statut"), __("Matricule"), __("Étudiant"), __("Motif")]].concat(
						bilan.lignes.map(l => [l.ligne, l.statut, l.matricule, l.nom, l.motif])
					),
					null,
					"bilan_import_inscriptions"
				);
			},
		});

		function on_primary(values) {
			if (etape === "termine") {
				d.hide();
				return;
			}
			frappe.call({
				method: `${API}.importer_inscriptions`,
				args: {
					file_url: values.fichier,
					annee_academique: values.annee_academique,
					valider: etape === "valider" ? 1 : 0,
					envoyer_email: values.envoyer_email ? 1 : 0,
				},
				freeze: true,
				freeze_message: etape === "valider" ? __("Importation en cours…") : __("Vérification du fichier…"),
				callback(r) {
					if (!r.message) return;
					bilan = r.message;
					d.fields_dict.bilan.$wrapper.html(render_bilan(bilan));
					if (bilan.valide) {
						etape = "termine";
						d.set_primary_action(__("Fermer"), on_primary);
						load_data();
					} else if (bilan.importees) {
						etape = "valider";
						d.set_primary_action(
							__("Confirmer l'importation ({0} lignes)", [bilan.importees]),
							on_primary
						);
					}
				},
			});
		}

		function reset() {
			if (etape === "termine" || !d) return;
			etape = "verifier";
			bilan = null;
			d.fields_dict.bilan.$wrapper.empty();
			d.set_primary_action(__("Vérifier le fichier"), on_primary);
		}

		d.show();
	}

	$(document).on("click.listeInscriptions", function (e) {
		if (!$(e.target).closest(".bureau-search-wrap").length) {
			$(".bureau-search-results").empty().hide();
		}
	});

	setup_filters();
	load_data();
};
