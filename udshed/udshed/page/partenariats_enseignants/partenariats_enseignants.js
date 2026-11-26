// Partenariats enseignants : heures, vacations et conventions de chaque enseignant de l'année,
// téléchargement des fiches (PDF / Word). Données : udshed.api.documents_enseignant.
frappe.pages["partenariats-enseignants"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Partenariats enseignants"), single_column: true });
	const API = "udshed.api.documents_enseignant.";
	const gestion = frappe.user.has_role("Responsable des partenariats") || frappe.user.has_role("System Manager");
	const etat = { periode: "Année complète", vacataires: 1, data: null };
	const esc = (v) => frappe.utils.escape_html(v === null || v === undefined ? "" : String(v));
	const nombre = (v) => (Number(v) || 0).toLocaleString("fr-FR", { maximumFractionDigits: 1 });
	const SYMBOLES = { XAF: "FCFA", XOF: "FCFA", EUR: "€", USD: "$" };
	// 6 500 FCFA : même présentation que sur les documents.
	const argent = (v, devise) => `${Math.round(Number(v) || 0).toLocaleString("fr-FR")} ${SYMBOLES[devise] || devise || ""}`.trim();
	const annee = (window.Udshed && Udshed.Session && Udshed.Session.annee()) || frappe.defaults.get_user_default("academic_year");
	if (annee) page.set_indicator(__("Année {0}", [annee]), "gray");

	page.add_field({
		fieldtype: "Select", fieldname: "periode", label: __("Période"),
		options: ["Année complète", "Semestre 1", "Semestre 2"], default: etat.periode,
		change() { etat.periode = this.get_value(); charger(); },
	});
	page.add_field({
		fieldtype: "Check", fieldname: "vacataires", label: __("Vacataires seulement"), default: 1,
		change() { etat.vacataires = this.get_value() ? 1 : 0; charger(); },
	});
	if (gestion) {
		page.set_primary_action(__("Créer les conventions manquantes"), () => {
			frappe.confirm(__("Créer une convention « Brouillon » pour chaque vacataire de l'année qui n'en a pas ?"), () =>
				frappe.xcall(API + "creer_conventions", { academic_year: annee }).then((r) => {
					frappe.show_alert({ message: __("{0} convention(s) créée(s).", [(r.crees || []).length]), indicator: "green" });
					charger();
				}));
		});
	}
	page.add_inner_button(__("Conventions"), () => frappe.set_route("List", "Convention Vacation", { academic_year: annee }));
	page.add_inner_button(__("Documents produits"), () => frappe.set_route("List", "Document Enseignant", { academic_year: annee }));

	$(`<style>
		.pe { max-width: 1280px; margin: 0 auto; padding: 4px 0 32px; font-size: 14px; }
		.pe-cartes { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-bottom: 16px; }
		.pe-carte { border: 1px solid var(--border-color); border-radius: 10px; padding: 14px 16px; background: var(--card-bg); }
		.pe-carte .v { font-size: 22px; font-weight: 600; color: var(--text-color); }
		.pe-carte .l { color: var(--text-muted); font-size: 13px; margin-top: 2px; }
		.pe table { width: 100%; border-collapse: collapse; background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; overflow: hidden; }
		.pe th { text-align: left; font-weight: 600; color: var(--text-muted); font-size: 13px; padding: 10px 12px; background: var(--subtle-fg); border-bottom: 1px solid var(--border-color); }
		.pe td { padding: 10px 12px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
		.pe td.n, .pe th.n { text-align: right; font-variant-numeric: tabular-nums; }
		.pe .etiquette { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; background: var(--subtle-fg); color: var(--text-muted); }
		.pe .etiquette.ok { background: var(--green-50, #eef6f0); color: var(--green-700, #2f6b46); }
		.pe .etiquette.att { background: var(--yellow-50, #fbf6e9); color: var(--yellow-800, #7a5b12); }
		.pe .alerte { color: var(--red-600, #b42318); font-size: 12px; }
		.pe .vide { padding: 32px; text-align: center; color: var(--text-muted); border: 1px dashed var(--border-color); border-radius: 10px; }
	</style>`).appendTo(page.main);
	const $racine = $(`<div class="pe"><div class="pe-cartes"></div><div class="pe-table"></div></div>`).appendTo(page.main);

	function telecharger(type_acte, teacher, format) {
		open_url_post("/api/method/" + API + "telecharger",
			{ type_acte, teacher, academic_year: annee, periode: etat.periode, format }, true);
	}

	function menu(ligne) {
		const docs = [["Fiche de règlement des vacations", __("Règlement des vacations")],
			["Fiche de progression des cours", __("Progression des cours")],
			["Attestation d'enseignement", __("Attestation d'enseignement")]];
		if (ligne.convention) docs.push(["Convention de vacation", __("Convention de vacation")]);
		return `<div class="dropdown">
			<button class="btn btn-default btn-sm dropdown-toggle" data-toggle="dropdown">${__("Documents")}</button>
			<div class="dropdown-menu dropdown-menu-right">
				${docs.map(([type, libelle]) => `
					<div class="dropdown-header">${esc(libelle)}</div>
					<a class="dropdown-item" data-type="${esc(type)}" data-format="pdf" data-teacher="${esc(ligne.enseignant)}">PDF</a>
					<a class="dropdown-item" data-type="${esc(type)}" data-format="docx" data-teacher="${esc(ligne.enseignant)}">Word</a>`).join("")}
			</div></div>`;
	}

	function rendre() {
		const d = etat.data || { lignes: [] };
		const lignes = d.lignes || [];
		const vacataires = lignes.filter((l) => l.vacataire);
		const signees = lignes.filter((l) => l.convention_statut === "Signée").length;
		$racine.find(".pe-cartes").html([
			[lignes.length, __("Enseignants")],
			[nombre(lignes.reduce((s, l) => s + l.heures_faites, 0)) + " h", __("Heures faites ({0})", [etat.periode.toLowerCase()])],
			[argent(vacataires.reduce((s, l) => s + l.net, 0), d.devise), __("Net à payer (vacataires)")],
			[`${signees} / ${vacataires.length}`, __("Conventions signées")],
		].map(([v, l]) => `<div class="pe-carte"><div class="v">${v}</div><div class="l">${esc(l)}</div></div>`).join(""));
		if (!lignes.length) {
			$racine.find(".pe-table").html(`<div class="vide">${__("Aucun enseignant n'intervient dans les cours de cette année.")}</div>`);
			return;
		}
		$racine.find(".pe-table").html(`<table><thead><tr>
			<th>${__("Enseignant")}</th><th>${__("Statut")}</th><th class="n">${__("Prévu (h)")}</th><th class="n">${__("Fait (h)")}</th>
			<th class="n">${__("Avancement")}</th><th class="n">${__("Net à payer")}</th><th>${__("Convention")}</th><th></th>
		</tr></thead><tbody>${lignes.map((l) => `<tr>
			<td><a href="/desk/teacher/${encodeURIComponent(l.enseignant)}">${esc(l.nom)}</a>
				${l.alerte_tarif ? `<div class="alerte">${__("Tarif manquant pour « {0} »", [esc(l.alerte_tarif)])}</div>` : ""}</td>
			<td>${esc(l.statut)}</td>
			<td class="n">${nombre(l.heures_prevues)}</td><td class="n">${nombre(l.heures_faites)}</td>
			<td class="n">${nombre(l.avancement)} %</td>
			<td class="n">${l.vacataire ? argent(l.net, d.devise) : "—"}</td>
			<td>${l.convention
				? `<a href="/desk/convention-vacation/${encodeURIComponent(l.convention)}"><span class="etiquette ${l.convention_statut === "Signée" ? "ok" : "att"}">${esc(__(l.convention_statut))}</span></a>`
				: (l.vacataire ? `<span class="etiquette">${__("Aucune")}</span>` : "—")}</td>
			<td>${gestion ? menu(l) : ""}</td></tr>`).join("")}</tbody></table>`);
	}

	$racine.on("click", ".dropdown-item[data-type]", function (e) {
		e.preventDefault();
		telecharger($(this).data("type"), $(this).data("teacher"), $(this).data("format"));
	});

	function charger() {
		frappe.xcall(API + "tableau", { academic_year: annee, periode: etat.periode, vacataires: etat.vacataires })
			.then((r) => { etat.data = r; rendre(); });
	}
	charger();
};
