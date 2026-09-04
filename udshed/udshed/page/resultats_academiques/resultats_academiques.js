frappe.pages["resultats-academiques"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Résultats académiques"),
		single_column: true,
	});

	const API = "udshed.api.resultats_page.";
	const TYPE_NORMALE = "Examen de session normal";
	const TYPE_RATTRAPAGE = "Examen de rattrapage";

	const state = {
		data: null,
		loading: false,
		tab: "tableau",
		classes: [],
		academic_years: [],
		charts: [],
		filters: {
			academic_year: "",
			classe: "",
			semestre: "",
			session_type: "",
			statut: "",
			search: "",
		},
	};

	function esc(s) {
		return s == null ? "" : String(s).replace(/[&<>"']/g, (c) => ({
			"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
		}[c]));
	}

	function fmt_note(v) {
		return v == null || v === "" ? "—" : Number(v).toFixed(2);
	}

	function qs(params) {
		return Object.entries(params || {})
			.filter(([, v]) => v != null && v !== "")
			.map(([k, v]) => encodeURIComponent(k) + "=" + encodeURIComponent(v))
			.join("&");
	}

	function api_download(method, params) {
		const a = document.createElement("a");
		a.href = "/api/method/" + method + "?" + qs(params);
		a.style.display = "none";
		document.body.appendChild(a);
		a.click();
		a.remove();
	}

	function badge_statut(statut) {
		if (statut === "Validé" || statut === "Admis") {
			return `<span class="ra-badge ra-badge-ok">${esc(statut)}</span>`;
		}
		if (statut === "Non Validé" || statut === "Ajourné") {
			return `<span class="ra-badge ra-badge-ko">${esc(statut)}</span>`;
		}
		return `<span class="ra-badge ra-badge-neutral">${esc(statut || __("En attente"))}</span>`;
	}

	function filtres_backend() {
		const [filiere, niveau] = (state.filters.classe || "").split("|");
		return {
			academic_year: state.filters.academic_year || null,
			filiere: filiere || null,
			niveau: niveau || null,
			semestre: state.filters.semestre || null,
			session_type: state.filters.session_type || null,
			statut: state.filters.statut || null,
			search: state.filters.search || null,
		};
	}

	// ------------------------------------------------------------------ //
	//  Squelette de la page
	// ------------------------------------------------------------------ //
	page.main.html(`
		<div class="ra-page">
			<div class="ra-header">
				<div>
					<h3 class="ra-title">${__("Résultats académiques")}</h3>
					<p class="ra-subtitle">${__("Consultez et analysez les résultats des étudiants")}</p>
				</div>
				<div class="ra-header-actions">
					<button type="button" class="btn btn-default btn-sm ra-btn-calculer">
						${frappe.utils.icon("refresh", "sm")} ${__("Calculer les résultats")}
					</button>
					<button type="button" class="btn btn-default btn-sm ra-btn-filter">
						${frappe.utils.icon("filter", "sm")} ${__("Filtrer")}
					</button>
					<button type="button" class="btn btn-primary btn-sm ra-btn-pdf">
						${frappe.utils.icon("download", "sm")} ${__("Télécharger PDF")}
					</button>
				</div>
			</div>
			<div class="ra-stats"></div>
			<div class="ra-card ra-filters-card">
				<div class="ra-filters">
					<div class="ra-filter ra-filter-search">
						<label>${__("Rechercher un étudiant...")}</label>
						<input type="text" class="form-control ra-input-search"
							placeholder="${__("Matricule, nom ou prénom")}">
					</div>
					<div class="ra-filter">
						<label>${__("Classe")}</label>
						<select class="form-control ra-select-classe"></select>
					</div>
					<div class="ra-filter">
						<label>${__("Statut")}</label>
						<select class="form-control ra-select-statut">
							<option value="">${__("Tous les statuts")}</option>
							<option value="Admis">${__("Admis")}</option>
							<option value="Ajourné">${__("Échec (Ajourné)")}</option>
						</select>
					</div>
					<div class="ra-filter">
						<label>${__("Session")}</label>
						<select class="form-control ra-select-session">
							<option value="">${__("Toutes les sessions")}</option>
							<option value="${TYPE_NORMALE}">${__("Session normale")}</option>
							<option value="${TYPE_RATTRAPAGE}">${__("Session de rattrapage")}</option>
						</select>
					</div>
					<div class="ra-filter">
						<label>${__("Année académique")}</label>
						<select class="form-control ra-select-year"></select>
					</div>
					<div class="ra-filter">
						<label>${__("Semestre")}</label>
						<select class="form-control ra-select-semestre">
							<option value="">${__("Tous les semestres")}</option>
							<option value="Semestre 1">${__("Semestre 1")}</option>
							<option value="Semestre 2">${__("Semestre 2")}</option>
						</select>
					</div>
				</div>
			</div>
			<div class="ra-tabs">
				<button type="button" class="ra-tab active" data-tab="tableau">${__("Vue tableau")}</button>
				<button type="button" class="ra-tab" data-tab="cours">${__("Par cours")}</button>
				<button type="button" class="ra-tab" data-tab="analytiques">${__("Analytiques")}</button>
			</div>
			<div class="ra-content"></div>
		</div>
	`);

		const $stats = page.main.find(".ra-stats");
		const $filters_card = page.main.find(".ra-filters-card");
		const $content = page.main.find(".ra-content");

	// ------------------------------------------------------------------ //
	//  Chargement
	// ------------------------------------------------------------------ //
	function init() {
		render_stats(null);
		bind_events();
		frappe.call({
			method: "udshed.api.user_data.get_user_context",
			callback(r) {
				const ctx = (r.message || [])[0] || {};
				state.academic_years = (ctx.academic_year_list || []).map((y) => y.name);
				state.filters.academic_year = ctx.default_academic_year || state.academic_years[0] || "";
				remplir_annees();
				load_classes();
			},
			error() {
				load_classes();
			},
		});
	}

	function remplir_annees() {
		const $year = page.main.find(".ra-select-year");
		$year.empty();
		(state.academic_years || []).forEach((y) => {
			$year.append(`<option value="${esc(y)}">${esc(y)}</option>`);
		});
		$year.val(state.filters.academic_year);
	}

	function load_classes() {
		frappe.call({
			method: API + "get_classes",
			args: { academic_year: state.filters.academic_year || null },
			callback(r) {
				state.classes = r.message || [];
				remplir_classes();
				if (!state.filters.classe && state.classes.length) {
					state.filters.classe = state.classes[0].filiere + "|" + state.classes[0].niveau;
					page.main.find(".ra-select-classe").val(state.filters.classe);
				}
				load_data();
			},
			error() {
				render_error(__("Impossible de charger les classes."));
			},
		});
	}

	function remplir_classes() {
		const $classe = page.main.find(".ra-select-classe");
		$classe.empty();
		$classe.append(`<option value="">${__("Toutes les classes")}</option>`);
		state.classes.forEach((c) => {
			$classe.append(`<option value="${esc(c.filiere)}|${esc(c.niveau)}">${esc(c.label)}</option>`);
		});
		$classe.val(state.filters.classe || "");
	}

	function load_data() {
		if (!state.filters.classe) {
			state.data = null;
			render_stats(null);
			render_empty(__("Sélectionnez une classe pour afficher les résultats."));
			return;
		}
		state.loading = true;
		render_loading();
		frappe.call({
			method: API + "get_resultats",
			args: filtres_backend(),
			callback(r) {
				state.loading = false;
				state.data = r.message || null;
				render_stats(state.data ? state.data.statistiques : null);
				render_content();
			},
			error(xhr) {
				state.loading = false;
				let message = __("Impossible de charger les résultats.");
				try {
					const body = JSON.parse(xhr.responseText);
					if (body && body._server_messages) {
						const msgs = JSON.parse(body._server_messages);
						if (msgs.length) message = msgs[0];
					}
				} catch (e) { /* message générique */ }
				render_error(message);
			},
		});
	}

	// ------------------------------------------------------------------ //
	//  Statistiques
	// ------------------------------------------------------------------ //
	function stat_card(icon, label, value, cls) {
		return `
			<div class="ra-stat-card ${cls || ""}">
				<div class="ra-stat-icon">${frappe.utils.icon(icon, "md")}</div>
				<div>
					<div class="ra-stat-value">${value}</div>
					<div class="ra-stat-label">${esc(label)}</div>
				</div>
			</div>`;
	}

	function render_stats(stats) {
		const s = stats || {
			total_etudiants: 0, admis: 0, echecs: 0, moyenne_classe: 0, taux_reussite: 0,
		};
		$stats.html(
			stat_card("users", __("Total étudiants"), s.total_etudiants) +
			stat_card("check-circle", __("Admis"), s.admis, "ra-stat-ok") +
			stat_card("alert-circle", __("Échecs"), s.echecs, "ra-stat-ko") +
			stat_card("bar-chart-2", __("Moyenne classe"), `${fmt_note(s.moyenne_classe)} / 20`) +
			stat_card("percent", __("Taux de réussite"), `${fmt_note(s.taux_reussite)} %`)
		);
	}

	// ------------------------------------------------------------------ //
	//  États (chargement / vide / erreur)
	// ------------------------------------------------------------------ //
	function render_loading() {
		$content.html(`
			<div class="ra-card ra-state">
				<div class="ra-spinner"></div>
				<p>${__("Chargement des résultats...")}</p>
			</div>`);
	}

	function render_empty(message) {
		$content.html(`
			<div class="ra-card ra-state">
				<div class="ra-state-icon">${frappe.utils.icon("search", "lg")}</div>
				<p>${esc(message || __("Aucun résultat trouvé"))}</p>
			</div>`);
	}

	function render_error(message) {
		$content.html(`
			<div class="ra-card ra-state ra-state-error">
				<div class="ra-state-icon">${frappe.utils.icon("alert", "lg")}</div>
				<p>${esc(message)}</p>
			</div>`);
	}

	// ------------------------------------------------------------------ //
	//  Onglets et contenu
	// ------------------------------------------------------------------ //
	function render_content() {
		page.main.find(".ra-tab").removeClass("active");
		page.main.find(`.ra-tab[data-tab="${state.tab}"]`).addClass("active");

		if (!state.data || !state.data.etudiants.length) {
			render_empty(__("Aucun résultat trouvé"));
			return;
		}
		if (state.tab === "tableau") render_tableau();
		else if (state.tab === "cours") render_par_cours();
		else render_analytiques();
	}

	function render_tableau() {
		const lignes = state.data.lignes || [];
		if (!lignes.length) {
			render_empty(__("Aucun résultat trouvé"));
			return;
		}
		const rows = lignes.map((l) => `
			<tr>
				<td class="ra-rang">#${l.rang}</td>
				<td class="ra-matricule">${esc(l.matricule)}</td>
				<td>
					<div class="ra-student-cell">
						<span class="ra-student-name">${esc(l.nom_complet)}</span>
						<span class="ra-student-sub">${esc(l.classe)}${l.cycle ? " · " + esc(l.cycle) : ""}</span>
					</div>
				</td>
				<td>
					<div class="ra-course-cell">
						<span>${esc(l.cours_intitule)}</span>
						<span class="ra-student-sub">${esc(l.cours_code)}${l.est_rattrapage ? " · " + __("rattrapage retenu") : ""}</span>
					</div>
				</td>
				<td class="ra-note">${fmt_note(l.note_cc)}</td>
				<td class="ra-note">${fmt_note(l.note_examen)}</td>
				<td class="ra-note ra-note-strong">${fmt_note(l.note_finale)}</td>
				<td>${badge_statut(l.statut_ue)}</td>
				<td class="ra-actions-cell">
					<button type="button" class="btn btn-default btn-xs ra-btn-detail" data-student="${esc(l.student)}">
						${__("Détails")}
					</button>
				</td>
			</tr>`).join("");

		$content.html(`
			<div class="ra-card">
				<div class="ra-table-wrap">
					<table class="ra-table">
						<thead>
							<tr>
								<th>${__("Rang")}</th>
								<th>${__("Matricule")}</th>
								<th>${__("Nom")}</th>
								<th>${__("Cours")}</th>
								<th class="text-center">${__("Moy. CC")}</th>
								<th class="text-center">${__("Examen")}</th>
								<th class="text-center">${__("Moy. Finale")}</th>
								<th>${__("Statut")}</th>
								<th class="text-center">${__("Actions")}</th>
							</tr>
						</thead>
						<tbody>${rows}</tbody>
					</table>
				</div>
			</div>`);

		$content.find(".ra-btn-detail").on("click", function () {
			open_detail($(this).attr("data-student"));
		});
	}

	function render_par_cours() {
		const cours = state.data.par_cours || [];
		if (!cours.length) {
			render_empty(__("Aucun résultat trouvé"));
			return;
		}
		const cards = cours.map((c) => `
			<div class="ra-course-card">
				<div class="ra-course-head">
					<div>
						<div class="ra-course-title">${esc(c.intitule)}</div>
						<div class="ra-student-sub">${esc(c.code)} · ${c.credits} ${__("crédits")}</div>
					</div>
					<div class="ra-course-rate">${fmt_note(c.taux_reussite)} %</div>
				</div>
				<div class="ra-course-progress">
					<div class="ra-course-progress-bar" style="width:${Math.min(100, c.taux_reussite)}%;"></div>
				</div>
				<div class="ra-course-grid">
					<div><span>${__("Étudiants")}</span><b>${c.nb_etudiants}</b></div>
					<div><span>${__("Moyenne")}</span><b>${fmt_note(c.moyenne)}</b></div>
					<div><span>${__("Meilleure")}</span><b class="ra-ok">${fmt_note(c.meilleure)}</b></div>
					<div><span>${__("Plus faible")}</span><b class="ra-ko">${fmt_note(c.plus_faible)}</b></div>
					<div><span>${__("Admis")}</span><b class="ra-ok">${c.admis}</b></div>
					<div><span>${__("Échecs")}</span><b class="ra-ko">${c.echecs}</b></div>
				</div>
			</div>`).join("");
		$content.html(`<div class="ra-course-grid-cards">${cards}</div>`);
	}

	function render_analytiques() {
		const a = state.data.analytiques || {};
		const stats = state.data.statistiques || {};

		if (!stats.total_etudiants) {
			render_empty(__("Aucun résultat trouvé"));
			return;
		}

		state.charts.forEach((ch) => { try { ch.destroy(); } catch (e) { /* déjà détruit */ } });
		state.charts = [];

		$content.html(`
			<div class="ra-analytics">
				<div class="ra-card">
					<h6 class="ra-section-title">${__("Distribution des moyennes (/20)")}</h6>
					<div class="ra-chart" id="ra-chart-moyennes"></div>
				</div>
				<div class="ra-card">
					<h6 class="ra-section-title">${__("Distribution des grades")}</h6>
					<div class="ra-chart" id="ra-chart-grades"></div>
				</div>
				<div class="ra-card">
					<h6 class="ra-section-title">${__("Performances par cours")}</h6>
					<div class="ra-table-wrap">
						<table class="ra-table ra-table-compact">
							<thead>
								<tr>
									<th>${__("Cours")}</th>
									<th class="text-center">${__("Étudiants")}</th>
									<th class="text-center">${__("Moyenne")}</th>
									<th class="text-center">${__("Admis")}</th>
									<th class="text-center">${__("Échecs")}</th>
									<th class="text-center">${__("Taux de réussite")}</th>
								</tr>
							</thead>
							<tbody>
								${(a.par_cours || []).map((c) => `
									<tr>
										<td>${esc(c.code)} — ${esc(c.intitule)}</td>
										<td class="text-center">${c.nb_etudiants}</td>
										<td class="text-center">${fmt_note(c.moyenne)}</td>
										<td class="text-center ra-ok">${c.admis}</td>
										<td class="text-center ra-ko">${c.echecs}</td>
										<td class="text-center">${fmt_note(c.taux_reussite)} %</td>
									</tr>`).join("")}
							</tbody>
						</table>
					</div>
				</div>
			</div>`);

		const dist = a.distribution_moyennes || [];
		if (dist.length && typeof frappe.Chart !== "undefined") {
			state.charts.push(new frappe.Chart("#ra-chart-moyennes", {
				title: "",
				data: {
					labels: dist.map((d) => d.tranche),
					datasets: [{ name: __("Étudiants"), values: dist.map((d) => d.nb) }],
				},
				type: "bar",
				height: 220,
				colors: ["#1a5276"],
				barOptions: { spaceRatio: 0.4 },
			}));
		}
		const grades = a.distribution_grades || [];
		if (grades.length && typeof frappe.Chart !== "undefined") {
			state.charts.push(new frappe.Chart("#ra-chart-grades", {
				title: "",
				data: {
					labels: grades.map((g) => g.grade),
					datasets: [{ name: __("Étudiants"), values: grades.map((g) => g.nb) }],
				},
				type: "donut",
				height: 220,
				colors: ["#1e8449", "#2ecc71", "#f1c40f", "#e67e22", "#c0392b", "#7f8c8d", "#1a5276", "#8e44ad"],
			}));
		}
	}

	// ------------------------------------------------------------------ //
	//  Détail étudiant
	// ------------------------------------------------------------------ //
	function open_detail(student) {
		frappe.call({
			method: API + "get_resultat_detail",
			args: {
				student: student,
				academic_year: state.filters.academic_year || null,
				semestre: state.filters.semestre || null,
			},
			freeze: true,
			freeze_message: __("Chargement du détail..."),
			callback(r) {
				const d = r.message;
				if (!d) return;

				const rows = (d.ues || []).map((ue) => `
					<tr>
						<td>${esc(ue.code)}</td>
						<td>${esc(ue.intitule)}${ue.est_rattrapage ? ` <em>(${__("rattrapage retenu")})</em>` : ""}</td>
						<td class="text-center">${ue.credits}</td>
						<td class="text-center">${fmt_note(ue.note_cc)}</td>
						<td class="text-center">${fmt_note(ue.note_examen)}</td>
						<td class="text-center">${fmt_note(ue.session_rattrapage)}</td>
						<td class="text-center">${fmt_note(ue.note_examen_active)}</td>
						<td class="text-center"><b>${fmt_note(ue.note_finale)}</b></td>
						<td class="text-center">${esc(ue.grade)}</td>
						<td>${badge_statut(ue.statut_ue)}</td>
					</tr>`).join("");

				const info_item = (label, valeur) => `
					<div class="ra-detail-item">
						<div class="ra-detail-label">${esc(label)}</div>
						<div class="ra-detail-value">${valeur == null || valeur === "" ? "—" : esc(valeur)}</div>
					</div>`;

				const html = `
					<div class="ra-detail">
						<div class="ra-detail-grid">
							${info_item(__("Matricule"), d.matricule)}
							${info_item(__("Nom complet"), d.nom_complet)}
							${info_item(__("Filière"), d.filiere_name)}
							${info_item(__("Niveau"), d.niveau)}
							${info_item(__("Cycle"), d.cycle)}
							${info_item(__("Année académique"), d.academic_year)}
							${info_item(__("Semestre"), d.semestre)}
							${info_item(__("Session"), state.filters.session_type === TYPE_RATTRAPAGE
								? __("Session de rattrapage") : __("Session normale"))}
						</div>
						<div class="ra-detail-table mt-3">
							<div class="ra-table-wrap">
								<table class="ra-table ra-table-compact">
									<thead>
										<tr>
											<th>${__("Code")}</th>
											<th>${__("Cours / UE")}</th>
											<th class="text-center">${__("Crédits")}</th>
											<th class="text-center">${__("Moy. CC")}</th>
											<th class="text-center">${__("Examen")}</th>
											<th class="text-center">${__("Rattrapage")}</th>
											<th class="text-center">${__("Retenue")}</th>
											<th class="text-center">${__("Moy. finale")}</th>
											<th class="text-center">${__("Grade")}</th>
											<th>${__("Statut")}</th>
										</tr>
									</thead>
									<tbody>${rows || `<tr><td colspan="10" class="text-center text-muted">${__("Aucun résultat publié")}</td></tr>`}</tbody>
								</table>
							</div>
						</div>
						<div class="ra-detail-bilan mt-3">
							<div class="ra-bilan-card"><b>${d.total_credits}</b><span>${__("Total crédits")}</span></div>
							<div class="ra-bilan-card"><b>${d.credits_obtenus}</b><span>${__("Crédits obtenus")}</span></div>
							<div class="ra-bilan-card"><b>${fmt_note(d.mps)} %</b><span>${__("MPS")}</span></div>
							${d.mpc != null ? `<div class="ra-bilan-card"><b>${fmt_note(d.mpc)} %</b><span>${__("MPC")}</span></div>` : ""}
							<div class="ra-bilan-card ${d.decision === "Admis" ? "ra-ok-bg" : (d.decision === "Ajourné" ? "ra-ko-bg" : "")}">
								<b>${esc(d.decision)}</b><span>${__("Décision")}</span>
							</div>
						</div>
					</div>`;

				const dialog = new frappe.ui.Dialog({
					title: d.nom_complet || student,
					size: "extra-large",
					primary_action_label: __("Télécharger le résultat (PDF)"),
					primary_action() {
						frappe.show_alert({ message: __("Génération du PDF..."), indicator: "blue" });
						api_download(API + "download_resultat_etudiant_pdf", {
							student: student,
							academic_year: state.filters.academic_year || null,
							semestre: state.filters.semestre || null,
						});
					},
				});
				dialog.$body.append(html);
				dialog.show();
			},
			error() {
				frappe.hide_msgprint();
				frappe.msgprint({
					title: __("Erreur"),
					indicator: "red",
					message: __("Impossible de charger le détail de l'étudiant."),
				});
			},
		});
	}

	// ------------------------------------------------------------------ //
	//  Calcul en masse des résultats
	// ------------------------------------------------------------------ //
	function calculer_resultats() {
		const criteres = filtres_backend();
		if (!criteres.academic_year || !criteres.filiere || !criteres.niveau) {
			frappe.msgprint(__("Sélectionnez une année académique et une classe avant de lancer le calcul."));
			return;
		}
		if (state.loading) {
			return;
		}
		const libelle_classe = criteres.filiere + " — " + criteres.niveau;
		const libelle_semestre = criteres.semestre
			? criteres.semestre
			: __("tous les semestres (1 et 2)");
		frappe.confirm(
			__("Calculer les résultats du semestre pour la classe <b>") + libelle_classe +
				__("</b> (") + libelle_semestre + __(") ?"),
			function () {
				state.loading = true;
				$(".ra-btn-calculer").prop("disabled", true);
				frappe.show_alert({ message: __("Calcul des résultats en cours..."), indicator: "blue" });
				frappe.call({
					method: API + "calculer_resultats_classe",
					args: {
						academic_year: criteres.academic_year,
						filiere: criteres.filiere,
						niveau: criteres.niveau,
						semestre: criteres.semestre,
					},
					callback(r) {
						state.loading = false;
						$(".ra-btn-calculer").prop("disabled", false);
						if (!r || !r.message) {
							frappe.msgprint({
								title: __("Échec du calcul"),
								indicator: "red",
								message: __("Le calcul n'a pas abouti. Réessayez."),
							});
							return;
						}
						const m = r.message;
						let html = `${__("Étudiants traités")} : <b>${m.nb_etudiants}</b><br>
							${__("Résultats calculés / mis à jour")} : <b>${m.calcules}</b><br>
							${__("Aucune note publiée (ignorés)")} : <b>${m.ignores}</b>`;
						if (m.erreurs && m.erreurs.length) {
							html += `<br>${__("Erreurs")} : ` + m.erreurs
								.map((e) => esc(e))
								.join("<br>");
						}
						frappe.msgprint({
							title: __("Calcul terminé"),
							indicator: m.erreurs && m.erreurs.length ? "orange" : "green",
							message: html,
						});
						load_data();
					},
					error(r) {
						state.loading = false;
						$(".ra-btn-calculer").prop("disabled", false);
						frappe.msgprint({
							title: __("Erreur lors du calcul"),
							indicator: "red",
							message: r && r.message ? r.message : __("Vérifiez vos permissions et réessayez."),
						});
					},
				});
			},
			function () {},
		);
	}

	// ------------------------------------------------------------------ //
	//  PDF de la liste
	// ------------------------------------------------------------------ //
	function download_pdf() {
		if (!state.data || !state.data.etudiants.length) {
			frappe.msgprint(__("Aucun résultat à exporter pour ces critères."));
			return;
		}
		frappe.show_alert({ message: __("Génération du PDF..."), indicator: "blue" });
		api_download(API + "download_resultats_pdf", filtres_backend());
	}

	// ------------------------------------------------------------------ //
	//  Événements
	// ------------------------------------------------------------------ //
	let search_timer = null;
	function bind_events() {
		page.main.find(".ra-btn-calculer").on("click", calculer_resultats);
		page.main.find(".ra-btn-pdf").on("click", download_pdf);
		page.main.find(".ra-btn-filter").on("click", function () {
			$filters_card.toggleClass("ra-filters-hidden");
			const hidden = $filters_card.hasClass("ra-filters-hidden");
			$(this).find(".btn-icon").toggleClass("text-muted", hidden);
		});

		page.main.find(".ra-tab").on("click", function () {
			state.tab = $(this).attr("data-tab");
			render_content();
		});

		page.main.find(".ra-input-search").on("input", function () {
			clearTimeout(search_timer);
			const val = $(this).val();
			search_timer = setTimeout(() => {
				state.filters.search = val;
				load_data();
			}, 350);
		});

		page.main.find(".ra-select-classe").on("change", function () {
			state.filters.classe = $(this).val();
			load_data();
		});
		page.main.find(".ra-select-statut").on("change", function () {
			state.filters.statut = $(this).val();
			load_data();
		});
		page.main.find(".ra-select-session").on("change", function () {
			state.filters.session_type = $(this).val();
			load_data();
		});
		page.main.find(".ra-select-year").on("change", function () {
			state.filters.academic_year = $(this).val();
			load_classes();
		});
		page.main.find(".ra-select-semestre").on("change", function () {
			state.filters.semestre = $(this).val();
			load_data();
		});
	}

	init();
};
