// Liste unique de tous les inscrits : inscriptions de début d'année
// (candidature) et inscriptions en cours d'année (hors candidature, 25Z…).
frappe.pages["liste-des-inscriptions"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Liste des inscriptions",
		single_column: true,
	});

	const ORIGINE_HORS_CANDIDATURE = "Hors candidature";
	const API = "udshed.api.inscription_import_export";
	let filters = { filiere: null, annee_academique: null, cycle: null, niveau: null, statut: null, origine: null };
	// Niveaux par cycle (même référence que udshed/utils/niveaux.py)
	const NIVEAUX_PAR_CYCLE = {
		"Licence": ["Licence 1", "Licence 2", "Licence 3"],
		"BTS": ["BTS 1", "BTS 2"],
		"Master": ["Master 1", "Master 2"],
		"Doctorat": ["Doctorat 1", "Doctorat 2", "Doctorat 3", "Doctorat 4", "Doctorat 5", "Doctorat 6", "Doctorat 7"],
	};
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

	// Barre de filtres titrée (construite une fois) au-dessus du contenu
	// (indicateurs, tableau, panneau) qui est redessiné à chaque chargement.
	const $filtres = $(`<section class="li-filtres" aria-label="${__("Filtres")}"></section>`).appendTo(page.main);
	const $contenu = $(`<div></div>`).appendTo(page.main);
	const champs = {};
	const TOUS_NIVEAUX = [].concat(...Object.values(NIVEAUX_PAR_CYCLE));

	function champ_filtre(df, apres_changement) {
		const $wrap = $(`<div class="li-filtre"></div>`).appendTo($filtres);
		const ctrl = frappe.ui.form.make_control({
			parent: $wrap,
			df: {
				...df,
				onchange() {
					const valeur = ctrl.get_value() || null;
					if (valeur === filters[df.fieldname]) return;
					filters[df.fieldname] = valeur;
					if (apres_changement) apres_changement(valeur);
					load_data();
				},
			},
			render_input: true,
		});
		ctrl.refresh();
		champs[df.fieldname] = ctrl;
		return ctrl;
	}

	function setup_filters() {
		champ_filtre({ fieldtype: "Link", fieldname: "annee_academique", label: __("Année académique"), options: "Academic Year" });
		champ_filtre({ fieldtype: "Link", fieldname: "filiere", label: __("Filière"), options: "Field of study" });
		champ_filtre(
			{ fieldtype: "Select", fieldname: "cycle", label: __("Cycle"), options: ["", ...Object.keys(NIVEAUX_PAR_CYCLE)] },
			(cycle) => {
				// Les niveaux proposés suivent le cycle choisi
				const niveaux = cycle ? NIVEAUX_PAR_CYCLE[cycle] : TOUS_NIVEAUX;
				champs.niveau.df.options = ["", ...niveaux];
				champs.niveau.refresh();
				if (filters.niveau && !niveaux.includes(filters.niveau)) {
					filters.niveau = null;
					champs.niveau.set_value("");
				}
			}
		);
		champ_filtre({ fieldtype: "Select", fieldname: "niveau", label: __("Niveau"), options: ["", ...TOUS_NIVEAUX] });
		champ_filtre({
			fieldtype: "Select", fieldname: "statut", label: __("Statut"),
			options: ["", "Inscrit", "En attente de matricule", "Sans inscription académique"],
		});
		champ_filtre({
			fieldtype: "Select", fieldname: "origine", label: __("Origine"),
			options: [
				{ value: "", label: "" },
				{ value: "Candidature", label: __("Début d'année (candidature)") },
				{ value: ORIGINE_HORS_CANDIDATURE, label: __("En cours d'année") },
			],
		});
		$(`<button type="button" class="btn btn-link btn-sm li-reinit">${__("Réinitialiser")}</button>`)
			.appendTo($filtres)
			.on("click", reinitialiser_filtres);
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

	let reinitialisation = false;
	function reinitialiser_filtres() {
		reinitialisation = true;
		Promise.all(Object.keys(filters).map(cle => {
			filters[cle] = null;
			return champs[cle] ? champs[cle].set_value("") : null;
		})).then(() => {
			champs.niveau.df.options = ["", ...TOUS_NIVEAUX];
			champs.niveau.refresh();
			reinitialisation = false;
			current_query = "";
			load_data();
		});
	}

	function load_data() {
		if (reinitialisation) return; // un seul rechargement après remise à zéro
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

	// ------------------------------------------------------------------ //
	//  Affichage : indicateurs, tableau paginé et panneau de détail
	// ------------------------------------------------------------------ //
	const PAR_PAGE = 20;
	const COLONNES = [
		{ cle: "matricule", label: "Matricule" },
		{ cle: "nom_complet", label: "Étudiant" },
		{ cle: "filiere_label", label: "Filière" },
		{ cle: "niveau", label: "Niveau" },
		{ cle: "origine", label: "Origine" },
		{ cle: "statut", label: "Statut" },
	];
	let page_courante = 1;
	let tri = { cle: "creation", sens: -1 };
	let selection = null; // row.name de la ligne affichée dans le panneau
	let $vue = null;

	// Encore utilisé par le bilan d'importation
	function stat_card(label, value, icon) {
		return `<div class="bureau-stat-card">
			<div class="bureau-stat-icon">${frappe.utils.icon(icon || "list", "md")}</div>
			<div>
				<div class="bureau-stat-value">${value}</div>
				<div class="bureau-stat-label">${esc(label)}</div>
			</div>
		</div>`;
	}

	function matches_search(row, q) {
		if (!q) return true;
		q = q.toLowerCase();
		return SEARCH_KEYS.some(k => String(row[k] || "").toLowerCase().includes(q));
	}

	function lignes_visibles() {
		let rows = (report_data.rows || []).filter(r => matches_search(r, current_query));
		return rows.sort((a, b) => tri.sens * String(a[tri.cle] || "").localeCompare(
			String(b[tri.cle] || ""), "fr", { numeric: true, sensitivity: "base" }
		));
	}

	function initiales(nom) {
		return (nom || "?").trim().split(/\s+/).slice(0, 2).map(x => x[0]).join("").toUpperCase();
	}

	function pill_statut(statut) {
		const couleur = { "Inscrit": "green", "En attente de matricule": "orange" }[statut] || "gray";
		return `<span class="indicator-pill ${couleur}">${esc(statut)}</span>`;
	}

	function pill_origine(origine) {
		return origine === ORIGINE_HORS_CANDIDATURE
			? `<span class="indicator-pill blue">En cours d'année</span>`
			: `<span class="indicator-pill gray">Début d'année</span>`;
	}

	function render() {
		$contenu.empty();
		if (!report_data) return;
		$vue = $(`<div class="li-vue">
			<div class="li-sous-titre"></div>
			<div class="li-kpis"></div>
			<div class="li-main">
				<section class="li-card">
					<div class="li-toolbar">
						<div class="li-search">
							<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
							<input type="search" class="li-search-input" placeholder="${__("Rechercher : matricule, nom, email, téléphone, parent…")}" aria-label="${__("Rechercher un inscrit")}">
						</div>
						<span class="li-count"></span>
					</div>
					<div class="li-table-wrap"><table class="li-table"><thead></thead><tbody></tbody></table></div>
					<div class="li-foot"><span class="li-pager-info"></span><span class="li-pager"></span></div>
				</section>
				<aside class="li-card li-detail" aria-live="polite"></aside>
			</div>
		</div>`).appendTo($contenu);

		$vue.find(".li-search-input").val(current_query).on("input", function () {
			current_query = this.value;
			page_courante = 1;
			rafraichir();
		});
		rafraichir();
	}

	function rafraichir() {
		const rows = lignes_visibles();
		const pages = Math.max(1, Math.ceil(rows.length / PAR_PAGE));
		page_courante = Math.min(page_courante, pages);
		if (!rows.some(r => r.name === selection)) selection = rows.length ? rows[0].name : null;

		$vue.find(".li-sous-titre").text(
			(filters.annee_academique ? __("Année académique {0}", [filters.annee_academique]) : __("Toutes les années"))
			+ " · " + __("inscriptions de début d'année et en cours d'année")
		);
		render_kpis(rows);
		render_tableau(rows, pages);
		render_detail(rows.find(r => r.name === selection));
	}

	function render_kpis(rows) {
		const total = rows.length;
		const en_cours = rows.filter(r => r.origine === ORIGINE_HORS_CANDIDATURE).length;
		const debut = total - en_cours;
		const attente = rows.filter(r => r.statut !== "Inscrit").length;
		const pct = x => (total ? (x / total) * 100 : 0);
		$vue.find(".li-kpis").html(`
			<div class="li-kpi">
				<span class="li-kpi-v">${total}</span><span class="li-kpi-l">${__("Inscrits")}</span>
				<div class="li-bar" title="${__("Début d'année / en cours d'année")}">
					<span class="li-bar-debut" style="width:${pct(debut)}%"></span><span class="li-bar-cours" style="width:${pct(en_cours)}%"></span>
				</div>
			</div>
			<div class="li-kpi"><span class="li-kpi-v">${debut}</span><span class="li-kpi-l">${__("Début d'année (candidature)")}</span></div>
			<div class="li-kpi"><span class="li-kpi-v">${en_cours}</span><span class="li-kpi-l">${__("En cours d'année (25Z…)")}</span></div>
			<div class="li-kpi ${attente ? "li-kpi-alerte" : ""}"><span class="li-kpi-v">${attente}</span><span class="li-kpi-l">${__("En attente de matricule")}</span></div>`);
	}

	function render_tableau(rows, pages) {
		const debut = (page_courante - 1) * PAR_PAGE;
		const visibles = rows.slice(debut, debut + PAR_PAGE);

		$vue.find(".li-count").text(__("{0} inscrit(s)", [rows.length]));
		$vue.find(".li-table thead").html(`<tr>${COLONNES.map(c => `
			<th data-cle="${c.cle}" class="${tri.cle === c.cle ? "li-trie" : ""}" tabindex="0">
				${esc(c.label)} <span class="li-tri">${tri.cle === c.cle ? (tri.sens > 0 ? "▲" : "▼") : "↕"}</span>
			</th>`).join("")}</tr>`);

		$vue.find(".li-table tbody").html(visibles.length ? visibles.map(r => `
			<tr data-name="${esc(r.name)}" tabindex="0" class="${r.name === selection ? "li-sel" : ""}">
				<td>${r.matricule ? `<span class="li-mat">${esc(r.matricule)}</span>` : `<span class="li-mat li-mat-vide">${__("à générer")}</span>`}</td>
				<td><div class="li-qui"><span class="li-av">${esc(initiales(r.nom_complet))}</span>
					<span>${esc(r.nom_complet)}<small>${esc(r.email)}</small></span></div></td>
				<td>${esc(r.filiere_label)}</td>
				<td>${esc(r.niveau)}</td>
				<td>${pill_origine(r.origine)}</td>
				<td>${pill_statut(r.statut)}</td>
			</tr>`).join("")
			: `<tr><td colspan="${COLONNES.length}" class="li-vide">${__("Aucun inscrit ne correspond à ces filtres.")}</td></tr>`);

		$vue.find(".li-pager-info").text(rows.length
			? __("{0}–{1} sur {2}", [debut + 1, debut + visibles.length, rows.length]) : "");
		$vue.find(".li-pager").html(pages > 1 ? `
			<button class="btn btn-xs btn-default li-prec" ${page_courante === 1 ? "disabled" : ""}>‹</button>
			<span>${page_courante} / ${pages}</span>
			<button class="btn btn-xs btn-default li-suiv" ${page_courante === pages ? "disabled" : ""}>›</button>` : "");

		$vue.find(".li-table th").on("click keydown", function (e) {
			if (e.type === "keydown" && e.key !== "Enter") return;
			const cle = $(this).attr("data-cle");
			tri = { cle, sens: tri.cle === cle ? -tri.sens : 1 };
			rafraichir();
		});
		$vue.find(".li-table tbody tr[data-name]").on("click keydown", function (e) {
			if (e.type === "keydown" && e.key !== "Enter") return;
			selection = $(this).attr("data-name");
			rafraichir();
		});
		$vue.find(".li-prec").on("click", () => { page_courante -= 1; rafraichir(); });
		$vue.find(".li-suiv").on("click", () => { page_courante += 1; rafraichir(); });
	}

	function ligne_dl(label, value) {
		return value ? `<dt>${esc(label)}</dt><dd>${esc(value)}</dd>` : "";
	}

	function render_detail(r) {
		const $d = $vue.find(".li-detail");
		if (!r) {
			$d.html(`<p class="li-vide">${__("Sélectionnez un inscrit pour voir sa fiche.")}</p>`);
			return;
		}
		const parents = [
			["Père", r.father_name, r.father_phone, r.father_profession],
			["Mère", r.mother_name, r.mother_phone, r.mother_profession],
			["Sponsor", r.sponsor_name, r.sponsor_phone, r.sponsor_profession],
		].filter(p => p[1]).map(p => ligne_dl(p[0], [p[1], p[2], p[3]].filter(Boolean).join(" · "))).join("");

		const actions = [];
		if (r.inscription) {
			if (r.matricule) {
				actions.push(`<button class="btn btn-primary btn-sm li-fiche">${__("Télécharger la fiche")}</button>`);
			} else if (!r.dossier_origine && report_data.peut_gerer) {
				actions.push(`<button class="btn btn-primary btn-sm li-generer">${__("Générer le matricule et la fiche")}</button>`);
			}
			actions.push(`<button class="btn btn-default btn-sm li-inscription">${__("Ouvrir l'inscription")}</button>`);
		}
		if (r.dossier_origine) {
			actions.push(`<button class="btn btn-default btn-sm li-dossier">${__("Ouvrir le dossier candidat")}</button>`);
		}

		$d.html(`
			<div class="li-qui li-detail-tete">
				<span class="li-av li-av-grand">${esc(initiales(r.nom_complet))}</span>
				<div><h4>${esc(r.nom_complet)}</h4>
					<div class="li-meta">${r.matricule ? esc(r.matricule) : __("Matricule à générer")} · ${pill_statut(r.statut)}</div></div>
			</div>
			<h6>${__("Inscription")}</h6>
			<dl class="li-dl">
				${ligne_dl(__("Année"), r.annee_academique)}
				${ligne_dl(__("Filière"), r.filiere_label)}
				${ligne_dl(__("Niveau"), r.niveau)}
				<dt>${__("Origine")}</dt><dd>${pill_origine(r.origine)}</dd>
				${ligne_dl(__("N° dossier"), r.dossier_origine)}
				${ligne_dl(__("Centre d'examen"), r.examination_centre !== "Non défini" ? r.examination_centre : "")}
			</dl>
			<h6>${__("Contact")}</h6>
			<dl class="li-dl">
				${ligne_dl(__("Email"), r.email)}
				${ligne_dl(__("Téléphone"), r.phone)}
				${ligne_dl(__("Sexe"), r.sexe)}
				${ligne_dl(__("Naissance"), [r.date_naissance, r.lieu_naissance].filter(Boolean).join(" · "))}
			</dl>
			${parents ? `<h6>${__("Parents / tuteur")}</h6><dl class="li-dl">${parents}</dl>` : ""}
			<div class="li-actions">${actions.join("")}</div>`);

		$d.find(".li-dossier").on("click", () => frappe.set_route("Form", "Session Inscription Candidate", r.dossier_origine));
		$d.find(".li-inscription").on("click", () => frappe.set_route("Form", "Inscription Academique", r.inscription));
		$d.find(".li-fiche").on("click", () => window.open(fiche_url(r.inscription), "_blank"));
		$d.find(".li-generer").on("click", () => {
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
					window.open(res.message.pdf_url, "_blank");
					load_data();
				},
			});
		});
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

	setup_filters();
	load_data();
};
