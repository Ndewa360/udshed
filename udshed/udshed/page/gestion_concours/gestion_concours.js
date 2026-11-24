// Gestion des concours : tout le déroulé d'un concours sur une seule page,
// étape par étape (candidats -> notes -> délibération -> admissions), dans le
// même esprit que « Liste des inscriptions » (indicateurs, tableau, panneau).
frappe.pages["gestion-concours"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Gestion des concours"), single_column: true });

	const API = "udshed.api.concours_gestion.";
	const API_RES = "udshed.api.concours_resultats.";
	const API_DELIB = "udshed.api.concours_deliberation.";
	const API_FIN = "udshed.api.concours_finalisation.";
	const CLE_MEMOIRE = "udshed_gestion_concours";

	let data = null;
	let onglet = null;
	let selection = null;
	let recherche = "";
	let filtre_admission = "tous";

	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
	const initiales = (nom) => (nom || "?").trim().split(/\s+/).slice(0, 2).map((x) => x[0]).join("").toUpperCase();
	const date_fr = (d) => (d ? frappe.datetime.str_to_user(String(d).slice(0, 10)) : "—");
	const nombre = (n) => (n == null || n === "" ? "—" : Number(n).toLocaleString("fr-FR", { maximumFractionDigits: 2 }));
	const appel = (method, args, freeze_message) =>
		frappe.call({ method, args, freeze: true, freeze_message }).then((r) => r.message);

	page.set_primary_action(__("Nouveau concours"), () => frappe.new_doc("Concours"), "add");
	page.add_menu_item(__("Paramètres du concours (formulaire)"), () => {
		if (data) frappe.set_route("Form", "Concours", data.concours.name);
	});
	page.add_menu_item(__("Saisie des notes"), () => {
		frappe.route_options = data ? { concours: data.concours.name } : null;
		frappe.set_route("saisie-notes-concours");
	});

	// ------------------------------------------------------------------ barre
	const $barre = $(`<section class="gc-barre gc-vue"></section>`).appendTo(page.main);
	const $sel = $(`<div></div>`).appendTo($barre);
	const $info = $(`<div class="gc-barre-info"></div>`).appendTo($barre);
	const $contenu = $(`<div></div>`).appendTo(page.main);

	const champ_concours = frappe.ui.form.make_control({
		parent: $sel,
		df: {
			fieldtype: "Link", fieldname: "concours", label: __("Concours"), options: "Concours",
			onchange() {
				const v = champ_concours.get_value();
				if (v && (!data || data.concours.name !== v)) {
					onglet = null;
					selection = null;
					charger(v);
				}
			},
		},
		render_input: true,
	});
	champ_concours.refresh();

	function charger(nom) {
		if (!nom) return;
		localStorage.setItem(CLE_MEMOIRE, nom);
		return frappe.call({ method: API + "tableau", args: { concours: nom } }).then((r) => {
			data = r.message;
			if (!onglet) onglet = onglet_par_defaut();
			rendre();
		});
	}
	const recharger = () => charger(data.concours.name);

	// Appelé au premier affichage puis à chaque retour sur la page.
	frappe.pages["gestion-concours"].on_page_show = () => {
		const demande = frappe.route_options && frappe.route_options.concours;
		frappe.route_options = null;
		if (demande) { champ_concours.set_value(demande); return; }
		if (data) { recharger(); return; }
		const memo = localStorage.getItem(CLE_MEMOIRE);
		frappe.call({ method: API + "liste_concours" }).then((r) => {
			const liste = r.message || [];
			if (!liste.length) {
				$contenu.html(`<div class="gc-vue"><div class="gc-card gc-vide">${__("Aucun concours pour l'instant.")}
					<br><br><button class="btn btn-primary btn-sm gc-nouveau">${__("Créer un concours")}</button></div></div>`);
				$contenu.find(".gc-nouveau").on("click", () => frappe.new_doc("Concours"));
				return;
			}
			// Le plus récent concours encore en cours ; à défaut, le dernier consulté.
			const choisi = liste.find((c) => c.statut !== "Clôturé") || liste.find((c) => c.name === memo) || liste[0];
			champ_concours.set_value(choisi.name);
		});
	};

	function onglet_par_defaut() {
		return {
			"Brouillon": "candidats", "Candidatures ouvertes": "candidats", "Épreuves": "notes",
			"Délibération": "deliberation", "Résultats publiés": "admissions", "Clôturé": "admissions",
		}[data.concours.statut] || "candidats";
	}

	// ------------------------------------------------------------------ rendu
	function rendre() {
		const c = data.concours;
		$info.html(`${esc(c.academic_year || "")} · ${data.formations.length} ${__("formation(s)")} · ${data.kpis.places} ${__("place(s)")}`);
		const $vue = $(`<div class="gc-vue">
			<section class="gc-tete">
				<div class="gc-tete-haut">
					<div><h3>${esc(c.titre)}</h3><div class="gc-meta">${esc(c.name)} · ${__("Statut")} : <b>${esc(c.statut)}</b></div></div>
					<div class="gc-toolbar-actions gc-tete-actions"></div>
				</div>
				<ol class="gc-etapes">${data.etapes.map((e, i) => `
					<li class="gc-etape ${i < data.etape ? "gc-faite" : ""} ${i === data.etape ? "gc-courante" : ""}">${esc(e)}</li>`).join("")}
				</ol>
				<div class="gc-guide-slot"></div>
			</section>
			<div class="gc-kpis"></div>
			<nav class="gc-onglets" role="tablist"></nav>
			<div class="gc-onglet-contenu"></div>
		</div>`);
		$contenu.empty().append($vue);
		rendre_tete($vue);
		rendre_kpis($vue.find(".gc-kpis"));
		rendre_onglets($vue);
	}

	function rendre_tete($vue) {
		const c = data.concours;
		const $a = $vue.find(".gc-tete-actions");
		$(`<button class="btn btn-default btn-sm">${__("Paramètres")}</button>`).appendTo($a)
			.on("click", () => frappe.set_route("Form", "Concours", c.name));
		if (data.statut_suivant && data.scolarite) {
			const libelles = {
				"Candidatures ouvertes": __("Ouvrir les candidatures"),
				"Épreuves": __("Clore les candidatures et passer aux épreuves"),
				"Clôturé": __("Clôturer le concours"),
			};
			$(`<button class="btn btn-primary btn-sm">${esc(libelles[data.statut_suivant] || data.statut_suivant)}</button>`)
				.appendTo($a).on("click", () => {
					frappe.confirm(__("Passer le concours au statut « {0} » ?", [data.statut_suivant]), () =>
						appel(API + "changer_statut", { concours: c.name, statut: data.statut_suivant }).then(recharger));
				});
		}
		const guide = texte_guide();
		if (guide) {
			$vue.find(".gc-guide-slot").html(`<div class="gc-guide ${guide.alerte ? "gc-alerte" : ""}"><span>${guide.texte}</span></div>`);
		}
	}

	function texte_guide() {
		const c = data.concours, k = data.kpis;
		if (["Brouillon", "Candidatures ouvertes"].includes(c.statut) && !c.session_ouverte) {
			return { texte: __("Attention : ce concours est rattaché à la session d'inscription {0}, qui est fermée. Les nouvelles candidatures ne lui seront pas rattachées : choisissez la session ouverte dans « Paramètres ».", [esc(c.session_inscription || "—")]), alerte: true };
		}
		switch (c.statut) {
			case "Brouillon":
				return { texte: __("Complétez les formations, places et épreuves dans « Paramètres », puis ouvrez les candidatures.") };
			case "Candidatures ouvertes":
				return k.candidats
					? { texte: __("{0} candidat(s) autorisé(s) à concourir ; chacun a reçu sa convocation. Quand la liste est complète, passez aux épreuves.", [k.candidats]) }
					: { texte: __("Aucun candidat pour l'instant. Dans la liste des candidatures, sélectionnez les dossiers qui demandent une formation de ce concours et faites « Changer le statut » → « Autorisé à concourir »."), alerte: true };
			case "Épreuves": {
				const tout = data.saisie.length && data.saisie.every((m) => m.validee);
				return tout
					? { texte: __("Toutes les épreuves sont validées : vous pouvez lever l'anonymat (onglet Notes).") }
					: { texte: __("Saisie des notes en cours : chaque épreuve doit être saisie puis validée avant la levée de l'anonymat.") };
			}
			case "Délibération":
				if (!c.classement_calcule_le) return { texte: __("Calculez le classement (onglet Délibération)."), alerte: true };
				if (data.problemes.length) return { texte: __("{0} point(s) à régler avant de publier les résultats (onglet Délibération).", [data.problemes.length]), alerte: true };
				return { texte: __("La délibération est complète : vous pouvez publier les résultats.") };
			case "Résultats publiés":
				if (k.depasse) return { texte: __("{0} admis ont dépassé leur délai : leur place sera libérée automatiquement cette nuit, ou enregistrez leur désistement.", [k.depasse]), alerte: true };
				return { texte: __("{0} inscrit(s), {1} admis en attente de confirmation. Les places non confirmées dans le délai sont reproposées à la liste d'attente.", [k.inscrits, k.a_confirmer]) };
			default:
				return null;
		}
	}

	function kpi(v, l, cls) {
		return `<div class="gc-kpi ${cls || ""}"><span class="gc-kpi-v">${v}</span><span class="gc-kpi-l">${esc(l)}</span></div>`;
	}

	function rendre_kpis($k) {
		const k = data.kpis, statut = data.concours.statut;
		let html = kpi(k.places, __("Places")) + kpi(k.candidats, __("Candidats"));
		if (statut === "Épreuves") {
			const v = data.saisie.filter((m) => m.validee).length;
			html += kpi(`${v}/${data.saisie.length}`, __("Épreuves validées"), v < data.saisie.length ? "gc-kpi-alerte" : "gc-kpi-bon");
		}
		if (["Délibération", "Résultats publiés", "Clôturé"].includes(statut)) {
			html += kpi(k.admis, __("Admis")) + kpi(k.attente, __("Liste d'attente"));
		}
		if (["Résultats publiés", "Clôturé"].includes(statut)) {
			html += kpi(k.inscrits, __("Inscrits (confirmés)"), "gc-kpi-bon")
				+ kpi(k.a_confirmer, __("À confirmer"))
				+ kpi(k.depasse, __("Délai dépassé"), k.depasse ? "gc-kpi-alerte" : "")
				+ kpi(k.desistes, __("Désistés"));
		}
		$k.html(html);
	}

	const ONGLETS = [
		{ cle: "candidats", label: __("Candidats"), badge: () => data.candidats.length },
		{ cle: "notes", label: __("Notes"), badge: () => data.saisie.length ? `${data.saisie.filter((m) => m.validee).length}/${data.saisie.length}` : "" },
		{ cle: "deliberation", label: __("Délibération"), badge: () => data.problemes.length || "" },
		{ cle: "admissions", label: __("Admissions"), badge: () => (["Résultats publiés", "Clôturé"].includes(data.concours.statut) ? data.kpis.admis + data.kpis.desistes : "") },
	];

	function rendre_onglets($vue) {
		const $nav = $vue.find(".gc-onglets");
		ONGLETS.forEach((o) => {
			const b = o.badge();
			$(`<button class="gc-onglet ${o.cle === onglet ? "gc-actif" : ""}" role="tab">${esc(o.label)}${b !== "" && b != null ? `<span class="gc-badge">${b}</span>` : ""}</button>`)
				.appendTo($nav).on("click", () => { onglet = o.cle; selection = null; recherche = ""; rendre(); });
		});
		const $c = $vue.find(".gc-onglet-contenu");
		({ candidats: onglet_candidats, notes: onglet_notes, deliberation: onglet_deliberation, admissions: onglet_admissions })[onglet]($c);
	}

	// Tableau générique + panneau de détail
	function tableau_avec_panneau($c, { colonnes, lignes, actions_html, filtres_html, vide, detail, apres }) {
		const $m = $(`<div class="gc-main">
			<section class="gc-card">
				<div class="gc-toolbar">
					<div class="gc-search">
						<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
						<input type="search" class="gc-search-input" placeholder="${__("Rechercher un candidat, un n° de table…")}">
					</div>
					<div class="gc-toolbar-actions">${actions_html || ""}</div>
				</div>
				${filtres_html || ""}
				<div class="gc-table-wrap"><table class="gc-table"><thead><tr>${colonnes.map((c) => `<th class="${c.num ? "gc-num" : ""}">${esc(c.label)}</th>`).join("")}</tr></thead><tbody></tbody></table></div>
			</section>
			<aside class="gc-card gc-detail" aria-live="polite"></aside>
		</div>`).appendTo($c);

		const dessiner = () => {
			const q = recherche.toLowerCase();
			const visibles = lignes.filter((r) => !q || [r.nom_complet, r.numero_table, r.centre_examen, r.email]
				.some((x) => String(x || "").toLowerCase().includes(q)));
			if (!visibles.some((r) => r.name === selection)) selection = visibles.length ? visibles[0].name : null;
			$m.find("tbody").html(visibles.length ? visibles.map((r) => `
				<tr data-name="${esc(r.name)}" tabindex="0" class="${r.name === selection ? "gc-sel" : ""}">
					${colonnes.map((c) => `<td class="${c.num ? "gc-num" : ""}">${c.rendu(r)}</td>`).join("")}
				</tr>`).join("") : `<tr><td colspan="${colonnes.length}" class="gc-vide">${esc(vide)}</td></tr>`);
			$m.find("tbody tr[data-name]").on("click keydown", function (e) {
				if (e.type === "keydown" && e.key !== "Enter") return;
				selection = $(this).data("name");
				dessiner();
			});
			const r = visibles.find((x) => x.name === selection);
			const $d = $m.find(".gc-detail");
			if (!r) $d.html(`<p class="gc-vide">${__("Sélectionnez un candidat.")}</p>`);
			else detail(r, $d);
		};
		$m.find(".gc-search-input").val(recherche).on("input", function () { recherche = this.value; dessiner(); });
		if (apres) apres($m);
		dessiner();
	}

	function entete_detail(r, sous_titre) {
		return `<div class="gc-qui"><span class="gc-av gc-av-grand">${esc(initiales(r.nom_complet))}</span>
			<div><h4>${esc(r.nom_complet)}</h4><div class="gc-meta">${sous_titre}</div></div></div>`;
	}

	function pill(texte, couleur) {
		return `<span class="indicator-pill ${couleur}">${esc(texte)}</span>`;
	}

	// ---------------------------------------------------------- 1. candidats
	function onglet_candidats($c) {
		tableau_avec_panneau($c, {
			colonnes: [
				{ label: __("N° table"), rendu: (r) => `<b>${esc(r.numero_table || "—")}</b>` },
				{ label: __("Candidat"), rendu: (r) => `<div class="gc-qui"><span class="gc-av">${esc(initiales(r.nom_complet))}</span><div>${esc(r.nom_complet)}<small>${esc(r.candidature)}</small></div></div>` },
				{ label: __("Centre"), rendu: (r) => esc(r.centre_examen || "—") },
				{ label: __("Choix"), rendu: (r) => esc(r.choix.join(" · ")) },
			],
			lignes: data.candidats,
			vide: __("Aucun candidat autorisé à concourir pour l'instant."),
			actions_html: `<button class="btn btn-default btn-sm gc-emargement">${__("Liste d'émargement")}</button>
				<button class="btn btn-default btn-sm gc-dossiers">${__("Candidatures à examiner")}</button>`,
			apres: ($m) => {
				$m.find(".gc-emargement").on("click", emargement);
				$m.find(".gc-dossiers").on("click", () => frappe.set_route("consultation-candidatures"));
			},
			detail: (r, $d) => {
				$d.html(`${entete_detail(r, `${esc(r.numero_table || "")} · ${esc(r.centre_examen || "")}`)}
					<dl class="gc-dl">
						<dt>${__("Dossier")}</dt><dd>${esc(r.candidature)}</dd>
						<dt>${__("E-mail")}</dt><dd>${esc(r.email || "—")}</dd>
						<dt>${__("Téléphone")}</dt><dd>${esc(r.phone || "—")}</dd>
					</dl>
					<h6>${__("Choix de formation")}</h6>
					<div style="font-size:13px">${r.choix.map((x, i) => `${i + 1}. ${esc(x)}`).join("<br>") || "—"}</div>
					<div class="gc-actions">
						<button class="btn btn-default btn-sm gc-convoc">${__("Renvoyer la convocation")}</button>
						<button class="btn btn-default btn-sm gc-ouvrir">${__("Ouvrir le dossier")}</button>
					</div>`);
				$d.find(".gc-convoc").on("click", () => appel("udshed.api.concours.renvoyer_convocation", { fiche: r.name })
					.then(() => frappe.show_alert({ message: __("Convocation renvoyée"), indicator: "green" })));
				$d.find(".gc-ouvrir").on("click", () => frappe.set_route("Form", "Session Inscription Candidate", r.candidature));
			},
		});
	}

	function emargement() {
		frappe.call({ method: "udshed.api.concours.centres_du_concours", args: { concours: data.concours.name } }).then((r) => {
			const centres = r.message || [];
			if (!centres.length) { frappe.msgprint(__("Aucun candidat n'est encore autorisé à concourir.")); return; }
			const total = centres.reduce((s, c) => s + c.effectif, 0);
			const options = [__("Tous les centres ({0} candidats)", [total])].concat(centres.map((c) => `${c.centre || __("Sans centre")} (${c.effectif})`));
			const d = new frappe.ui.Dialog({
				title: __("Liste d'émargement"),
				fields: [{ fieldtype: "Select", fieldname: "choix", label: __("Centre"), options: options.join("\n"), default: options[0], reqd: 1 }],
				primary_action_label: __("Télécharger le PDF"),
				primary_action(v) {
					const i = options.indexOf(v.choix);
					const p = new URLSearchParams({ concours: data.concours.name });
					if (i > 0 && centres[i - 1].centre) p.set("centre", centres[i - 1].centre);
					window.open("/api/method/udshed.api.concours.telecharger_liste_emargement?" + p.toString());
					d.hide();
				},
			});
			d.show();
		});
	}

	// -------------------------------------------------------------- 2. notes
	function onglet_notes($c) {
		const c = data.concours;
		const $card = $(`<section class="gc-card"><div class="gc-card-corps"></div></section>`).appendTo($c);
		const $corps = $card.find(".gc-card-corps");
		if (!data.saisie.length) {
			$corps.html(`<p class="gc-vide">${__("La saisie des notes s'ouvre au statut « Épreuves ».")}</p>`);
			return;
		}
		const toutes = data.saisie.every((m) => m.validee);
		$corps.html(`<div class="gc-tete-haut"><h5>${__("Avancement de la saisie (copies anonymes)")}</h5>
				<div class="gc-toolbar-actions gc-notes-actions"></div></div>
			<div class="gc-epreuves">${data.saisie.map((m) => {
				const pct = m.total ? Math.round((m.saisies / m.total) * 100) : 0;
				return `<div class="gc-epreuve ${m.validee ? "gc-validee" : ""}">
					<span class="gc-epreuve-nom">${esc(m.matiere)}</span>
					<div class="gc-barre-prog"><span style="width:${pct}%"></span></div>
					<small>${m.saisies}/${m.total} ${__("copie(s)")} · ${m.validee ? `<b style="color:var(--gc-vert)">${__("validée")}</b>` : __("non validée")}</small>
				</div>`;
			}).join("")}</div>
			<p class="text-muted small">${c.anonymat_leve ? __("Anonymat levé : les notes sont nominatives et ne sont plus modifiables.") : __("Les correcteurs saisissent par code d'anonymat ; la scolarité valide chaque épreuve.")}</p>`);
		const $a = $corps.find(".gc-notes-actions");
		if (["Épreuves", "Délibération"].includes(c.statut) && !c.anonymat_leve) {
			$(`<button class="btn btn-default btn-sm">${__("Ouvrir la saisie des notes")}</button>`).appendTo($a).on("click", () => {
				frappe.route_options = { concours: c.name };
				frappe.set_route("saisie-notes-concours");
			});
		}
		if (c.statut === "Épreuves" && !c.anonymat_leve && data.scolarite) {
			$(`<button class="btn btn-primary btn-sm" ${toutes ? "" : "disabled"} title="${toutes ? "" : __("Toutes les épreuves doivent être validées")}">${__("Lever l'anonymat")}</button>`)
				.appendTo($a).on("click", () => frappe.confirm(
					__("Lever l'anonymat ? Les notes deviennent nominatives, ne sont plus modifiables, et le concours passe en « Délibération »."),
					() => appel(API_RES + "lever_anonymat", { concours: c.name }).then(() => { onglet = "deliberation"; recharger(); })));
		}
	}

	// ------------------------------------------------------- 3. délibération
	const DECISIONS = ["", "Admis", "Liste d'attente", "Non admis"];

	function onglet_deliberation($c) {
		const c = data.concours;
		if (!c.anonymat_leve) {
			$c.html(`<section class="gc-card"><p class="gc-vide">${__("La délibération commence après la levée de l'anonymat (onglet Notes).")}</p></section>`);
			return;
		}
		const en_delib = c.statut === "Délibération";
		const editable = en_delib && data.scolarite;

		// Actions + résumé + problèmes
		const $haut = $(`<section class="gc-card"><div class="gc-card-corps">
			<div class="gc-tete-haut"><h5>${__("Résumé par formation")}</h5><div class="gc-toolbar-actions gc-delib-actions"></div></div>
			<div class="gc-table-wrap"><table class="gc-table"><thead><tr>
				<th>${__("Formation")}</th><th class="gc-num">${__("Places")}</th><th class="gc-num">${__("Candidats")}</th>
				<th class="gc-num">${__("Admis")}</th><th class="gc-num">${__("Attente")}</th><th class="gc-num">${__("Non admis")}</th>
				<th class="gc-num">${__("Désistés")}</th><th class="gc-num">${__("Sans décision")}</th></tr></thead>
				<tbody>${data.resume.map((s) => `<tr><td>${esc(s.filiere)}</td><td class="gc-num">${s.places}</td><td class="gc-num">${s.candidats}</td>
					<td class="gc-num" style="color:${s.admis > s.places ? "var(--gc-rouge)" : "var(--gc-vert)"}"><b>${s.admis}</b></td>
					<td class="gc-num">${s.attente}</td><td class="gc-num">${s.non_admis}</td><td class="gc-num">${s.desistes}</td>
					<td class="gc-num" style="${s.sans_decision ? "color:var(--gc-rouge)" : ""}">${s.sans_decision}</td></tr>`).join("")
					|| `<tr><td colspan="8" class="gc-vide">${__("Classement non calculé.")}</td></tr>`}</tbody></table></div>
			${data.problemes.length ? `<div><b class="small">${__("À régler avant la publication :")}</b><ul class="gc-problemes">${data.problemes.map((p) => `<li>${esc(p)}</li>`).join("")}</ul></div>` : ""}
		</div></section>`).appendTo($c);
		const $a = $haut.find(".gc-delib-actions");
		const bouton = (label, primaire, fn, actif = true) =>
			$(`<button class="btn ${primaire ? "btn-primary" : "btn-default"} btn-sm" ${actif ? "" : "disabled"}>${esc(label)}</button>`).appendTo($a).on("click", fn);

		if (editable) {
			bouton(c.classement_calcule_le ? __("Recalculer le classement") : __("Calculer le classement"), !c.classement_calcule_le, () =>
				appel(API_RES + "calculer_classement", { concours: c.name }, __("Calcul des moyennes et du classement…")).then(recharger));
			if (c.classement_calcule_le) {
				bouton(__("Reprendre les propositions"), false, () =>
					appel(API_DELIB + "appliquer_propositions", { concours: c.name }).then((r) => {
						frappe.show_alert({ message: __("{0} décision(s) reprises ; {1} ex æquo à trancher.", [r.appliquees, r.ex_aequo]), indicator: "green" });
						recharger();
					}));
			}
		}
		if (c.classement_calcule_le) {
			bouton(__("PV provisoire"), false, () => window.open(`/api/method/${API_RES}telecharger_pv_classement?concours=${encodeURIComponent(c.name)}`));
			bouton(__("PV de délibération"), false, () => window.open(`/api/method/${API_DELIB}telecharger_pv_deliberation?concours=${encodeURIComponent(c.name)}`));
		}
		if (editable && c.classement_calcule_le) {
			bouton(__("Publier les résultats"), true, publier, !data.problemes.length);
		}

		// Jury
		if (["Délibération", "Résultats publiés", "Clôturé"].includes(c.statut)) {
			const $j = $(`<section class="gc-card"><div class="gc-card-corps"><h5>${__("Jury")}</h5><div class="gc-jury"></div>
				${editable ? `<div><button class="btn btn-default btn-sm gc-jury-ok">${__("Enregistrer le jury")}</button></div>` : ""}</div></section>`).appendTo($c);
			const champs = {};
			[
				{ fieldtype: "Data", fieldname: "president_jury", label: __("Président du jury") },
				{ fieldtype: "Date", fieldname: "date_deliberation", label: __("Date de délibération") },
				{ fieldtype: "Small Text", fieldname: "membres_jury", label: __("Membres (un par ligne)") },
				{ fieldtype: "Small Text", fieldname: "observations_jury", label: __("Observations") },
			].forEach((df) => {
				champs[df.fieldname] = frappe.ui.form.make_control({ parent: $(`<div></div>`).appendTo($j.find(".gc-jury")), df: { ...df, read_only: editable ? 0 : 1 }, render_input: true });
				champs[df.fieldname].refresh();
				champs[df.fieldname].set_value(c[df.fieldname] || "");
			});
			$j.find(".gc-jury-ok").on("click", () => {
				const v = {};
				Object.keys(champs).forEach((k) => (v[k] = champs[k].get_value()));
				appel(API + "enregistrer_jury", { concours: c.name, ...v }).then(() => frappe.show_alert({ message: __("Jury enregistré"), indicator: "green" }));
			});
		}

		// Résultats par formation, décision modifiable en ligne
		if (!data.resultats.length) return;
		const $t = $(`<section class="gc-card">
			<div class="gc-toolbar"><h5>${__("Classement et décisions du jury")}</h5>
				<span class="text-muted small">${editable ? __("La décision se modifie directement dans le tableau.") : ""}</span></div>
			<div class="gc-table-wrap"><table class="gc-table"><thead><tr>
				<th class="gc-num">${__("Rang")}</th><th>${__("Candidat")}</th><th>${__("Choix")}</th>
				<th class="gc-num">${__("Moyenne")}</th><th>${__("Proposition")}</th><th>${__("Décision du jury")}</th></tr></thead><tbody></tbody></table></div>
		</section>`).appendTo($c);
		let groupe = null, html = "";
		data.resultats.forEach((l) => {
			const g = `${l.filiere} — ${l.niveau}`;
			if (g !== groupe) { groupe = g; html += `<tr class="gc-groupe"><td colspan="6">${esc(g)}</td></tr>`; }
			const tags = (l.ex_aequo ? `<span class="gc-tag gc-tag-orange">${__("ex æquo")}</span>` : "")
				+ (l.elimine ? `<span class="gc-tag gc-tag-rouge" title="${esc(l.motif || "")}">${__("éliminé")}</span>` : "");
			const decision = editable && l.decision !== "Désisté"
				? `<select class="gc-decision" data-ligne="${esc(l.name)}">${DECISIONS.map((d) => `<option value="${esc(d)}" ${d === (l.decision || "") ? "selected" : ""}>${esc(d || "—")}</option>`).join("")}</select>`
				: esc(l.decision || "—");
			html += `<tr><td class="gc-num">${l.rang || "—"}</td><td>${esc(l.nom_complet)} <small class="text-muted">${esc(l.numero_table || "")}</small>${tags}</td>
				<td>${esc(l.choix || "")}</td><td class="gc-num">${nombre(l.moyenne)}</td><td>${esc(l.proposition || "—")}</td><td>${decision}</td></tr>`;
		});
		$t.find("tbody").html(html);
		$t.find("select.gc-decision").on("change", function () {
			const $s = $(this);
			frappe.call({ method: API + "definir_decision", args: { resultat: $s.data("ligne"), decision: $s.val() } })
				.then(() => recharger())
				.catch(() => recharger());
		});
	}

	function publier() {
		frappe.confirm(
			__("Publier les résultats ? Chaque candidat reçoit un e-mail (admis, liste d'attente ou non admis) et les décisions ne sont plus modifiables. Les admis devront confirmer leur place avant la date limite ({0} jours).", [data.concours.delai_finalisation || 15]),
			() => appel(API_DELIB + "publier_resultats", { concours: data.concours.name }, __("Publication et envoi des e-mails…")).then((b) => {
				frappe.msgprint(__("Résultats publiés : {0} admis, {1} en liste d'attente, {2} non admis, {3} absents, {4} renvoyés à l'examen sur dossier.",
					[b["Admis"], b["Liste d'attente"], b["Non admis"], b["Absent"], b["Dossier"]]));
				onglet = "admissions";
				recharger();
			})
		);
	}

	// --------------------------------------------------------- 4. admissions
	const SITUATIONS = {
		inscrit: ["green", __("Inscrits")],
		a_confirmer: ["orange", __("À confirmer")],
		depasse: ["red", __("Délai dépassé")],
		attente: ["yellow", __("Liste d'attente")],
		desiste: ["gray", __("Désistés")],
	};

	function onglet_admissions($c) {
		const c = data.concours;
		if (!["Résultats publiés", "Clôturé"].includes(c.statut)) {
			$c.html(`<section class="gc-card"><p class="gc-vide">${__("Le suivi des admissions commence à la publication des résultats.")}</p></section>`);
			return;
		}
		const tous = data.candidats.filter((r) => SITUATIONS[r.etat_admission]);
		const lignes = filtre_admission === "tous" ? tous : tous.filter((r) => r.etat_admission === filtre_admission);
		const compte = (k) => tous.filter((r) => r.etat_admission === k).length;
		const rang_attente = (r) => {
			const l = (r.resultats || []).find((x) => x.decision === "Liste d'attente");
			return l ? `${esc(l.filiere)} · ${__("rang")} ${l.rang || "—"}` : "";
		};
		tableau_avec_panneau($c, {
			colonnes: [
				{ label: __("Candidat"), rendu: (r) => `<div class="gc-qui"><span class="gc-av">${esc(initiales(r.nom_complet))}</span><div>${esc(r.nom_complet)}<small>${esc(r.numero_table || "")}</small></div></div>` },
				{ label: __("Formation"), rendu: (r) => r.filiere_admise ? `${esc(r.filiere_admise_libelle)} <small class="text-muted">${esc(r.niveau_admis_libelle)}</small>` : rang_attente(r) || "—" },
				{ label: __("Date limite"), rendu: (r) => (r.etat_admission === "a_confirmer" || r.etat_admission === "depasse" ? date_fr(r.finaliser_avant) : "—") },
				{ label: __("Situation"), rendu: (r) => pill(r.etat_admission_libelle, SITUATIONS[r.etat_admission][0]) },
			],
			lignes,
			vide: __("Aucun candidat dans cette situation."),
			filtres_html: `<div class="gc-filtres-rapides">${[["tous", __("Tous"), tous.length]].concat(Object.entries(SITUATIONS).map(([k, v]) => [k, v[1], compte(k)]))
				.map(([k, l, n]) => `<button class="gc-chip ${filtre_admission === k ? "gc-actif" : ""}" data-filtre="${k}">${esc(l)} (${n})</button>`).join("")}</div>`,
			actions_html: c.statut === "Résultats publiés" && data.scolarite ? `<button class="btn btn-default btn-sm gc-appel">${__("Appeler la liste d'attente")}</button>` : "",
			apres: ($m) => {
				$m.find(".gc-chip").on("click", function () { filtre_admission = $(this).data("filtre"); selection = null; rendre(); });
				$m.find(".gc-appel").on("click", () => appel(API_DELIB + "completer_liste_attente", { concours: c.name }).then((r) => { afficher_promus(r.promus); recharger(); }));
			},
			detail: (r, $d) => detail_admission(r, $d),
		});
	}

	function detail_admission(r, $d) {
		const c = data.concours;
		const ouvert = c.statut === "Résultats publiés" && data.scolarite;
		const parcours = (r.resultats || []).map((l) => `<tr><td>${esc(l.filiere)}</td><td class="gc-num">${l.rang || "—"}</td><td class="gc-num">${nombre(l.moyenne)}</td><td>${esc(l.decision || "—")}</td></tr>`).join("");
		$d.html(`${entete_detail(r, pill(r.etat_admission_libelle, SITUATIONS[r.etat_admission][0]))}
			<dl class="gc-dl">
				<dt>${__("Formation")}</dt><dd>${r.filiere_admise ? `${esc(r.filiere_admise_libelle)} — ${esc(r.niveau_admis_libelle)}` : "—"}</dd>
				${r.etat_admission === "a_confirmer" || r.etat_admission === "depasse" ? `<dt>${__("Date limite")}</dt><dd><b>${date_fr(r.finaliser_avant)}</b></dd>` : ""}
				<dt>${__("E-mail")}</dt><dd>${esc(r.email || "—")}</dd>
				<dt>${__("Téléphone")}</dt><dd>${esc(r.phone || "—")}</dd>
				${r.motif_desistement ? `<dt>${__("Motif")}</dt><dd>${esc(r.motif_desistement)}</dd>` : ""}
			</dl>
			${parcours ? `<h6>${__("Résultats")}</h6><table class="gc-table"><thead><tr><th>${__("Formation")}</th><th class="gc-num">${__("Rang")}</th><th class="gc-num">${__("Moy.")}</th><th>${__("Décision")}</th></tr></thead><tbody>${parcours}</tbody></table>` : ""}
			<div class="gc-actions"></div>`);
		const $a = $d.find(".gc-actions");
		if (ouvert && ["a_confirmer", "depasse"].includes(r.etat_admission)) {
			$(`<button class="btn btn-default btn-sm">${__("Prolonger le délai")}</button>`).appendTo($a).on("click", () => {
				frappe.prompt({ fieldtype: "Date", fieldname: "date", label: __("Nouvelle date limite"), reqd: 1, default: r.finaliser_avant },
					(v) => appel(API + "prolonger_delai", { candidature: r.candidature, date: v.date }).then(recharger),
					__("Prolonger le délai de {0}", [r.nom_complet]), __("Enregistrer"));
			});
		}
		if (ouvert && ["a_confirmer", "depasse", "attente"].includes(r.etat_admission)) {
			$(`<button class="btn btn-danger btn-sm">${__("Le candidat ne vient pas (désistement)")}</button>`).appendTo($a).on("click", () => {
				frappe.prompt({ fieldtype: "Small Text", fieldname: "motif", label: __("Motif du désistement"), reqd: 1 },
					(v) => appel(API_FIN + "desister_candidature", { candidature: r.candidature, motif: v.motif }).then((res) => {
						afficher_promus(res.promus, true);
						recharger();
					}),
					__("Désistement de {0}", [r.nom_complet]), __("Enregistrer"));
			});
		}
		$(`<button class="btn btn-default btn-sm">${__("Ouvrir le dossier")}</button>`).appendTo($a)
			.on("click", () => frappe.set_route("Form", "Session Inscription Candidate", r.candidature));
	}

	function afficher_promus(promus, apres_desistement) {
		if (!promus || !promus.length) {
			frappe.msgprint(apres_desistement ? __("Désistement enregistré. Aucun candidat de la liste d'attente à appeler.")
				: __("Aucun candidat de la liste d'attente n'a pu être appelé (liste vide ou places déjà pourvues)."));
			return;
		}
		frappe.msgprint({
			title: __("Places reproposées"),
			message: "<ul>" + promus.map((p) => `<li>${esc(p.candidat)} (${esc(p.numero_table)}) — ${esc(p.filiere)}, ${__("rang")} ${p.rang}</li>`).join("")
				+ "</ul><p class='text-muted small'>" + __("Chaque candidat appelé a reçu un e-mail pour confirmer sa place avant sa date limite.") + "</p>",
		});
	}
};
