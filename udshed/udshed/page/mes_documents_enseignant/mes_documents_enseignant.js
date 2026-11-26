// Mes documents (enseignant) : résumé de l'année, fiches à télécharger (PDF / Word), convention.
// Données : udshed.api.documents_enseignant.mes_documents (limité au compte connecté).
frappe.pages["mes-documents-enseignant"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Mes documents"), single_column: true });
	const API = "udshed.api.documents_enseignant.";
	const etat = { periode: "Année complète", data: null };
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

	$(`<style>
		.md { max-width: 1100px; margin: 0 auto; padding: 4px 0 32px; font-size: 14px; }
		.md-cartes { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 18px; }
		.md-carte { border: 1px solid var(--border-color); border-radius: 10px; padding: 14px 16px; background: var(--card-bg); }
		.md-carte .v { font-size: 22px; font-weight: 600; }
		.md-carte .l { color: var(--text-muted); font-size: 13px; }
		.md h5 { margin: 20px 0 10px; font-weight: 600; }
		.md-doc { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 12px 16px;
			border: 1px solid var(--border-color); border-radius: 10px; margin-bottom: 8px; background: var(--card-bg); flex-wrap: wrap; }
		.md-doc .titre { font-weight: 600; }
		.md-doc .msg { color: var(--text-muted); font-size: 13px; }
		.md table { width: 100%; border-collapse: collapse; background: var(--card-bg); border: 1px solid var(--border-color); }
		.md th { text-align: left; font-weight: 600; color: var(--text-muted); font-size: 13px; padding: 9px 12px; background: var(--subtle-fg); }
		.md td { padding: 9px 12px; border-top: 1px solid var(--border-color); }
		.md td.n, .md th.n { text-align: right; font-variant-numeric: tabular-nums; }
		.md .vide { padding: 28px; text-align: center; color: var(--text-muted); border: 1px dashed var(--border-color); border-radius: 10px; }
	</style>`).appendTo(page.main);
	const $racine = $(`<div class="md"></div>`).appendTo(page.main);

	function rendre() {
		const d = etat.data;
		const cartes = [
			[nombre(d.heures_prevues) + " h", __("Heures prévues")],
			[nombre(d.heures_faites) + " h", __("Heures faites ({0})", [d.periode])],
		];
		if (d.vacataire) cartes.push([argent(d.net, d.devise), __("Net à payer ({0})", [d.periode])]);
		if (d.convention) cartes.push([esc(__(d.convention.statut)), __("Convention de vacation")]);
		const docs = (d.documents || []).map((doc) => `<div class="md-doc">
			<div><div class="titre">${esc(__(doc.type_acte))}</div>${doc.possible ? "" : `<div class="msg">${esc(doc.message)}</div>`}</div>
			${doc.possible ? `<div><button class="btn btn-default btn-sm" data-type="${esc(doc.type_acte)}" data-format="pdf">PDF</button>
				<button class="btn btn-default btn-sm" data-type="${esc(doc.type_acte)}" data-format="docx">Word</button></div>` : ""}
		</div>`).join("");
		const lignes = (d.lignes || []).map((l) => `<tr><td>${esc(l.intitule)}</td><td>${esc(l.classes)}</td><td>${esc(l.type)}</td>
			<td class="n">${nombre(l.prevu)}</td><td class="n">${nombre(l.fait)}</td><td class="n">${nombre(l.avancement)} %</td></tr>`).join("");
		$racine.html(`
			<div class="md-cartes">${cartes.map(([v, l]) => `<div class="md-carte"><div class="v">${v}</div><div class="l">${esc(l)}</div></div>`).join("")}</div>
			<h5>${__("Documents")}</h5>${docs || `<div class="vide">${__("Aucun document disponible.")}</div>`}
			<h5>${__("Mes cours")}</h5>
			${lignes ? `<table><thead><tr><th>${__("Cours")}</th><th>${__("Classes")}</th><th>${__("Type")}</th>
				<th class="n">${__("Prévu (h)")}</th><th class="n">${__("Fait (h)")}</th><th class="n">${__("Avancement")}</th></tr></thead>
				<tbody>${lignes}</tbody></table>` : `<div class="vide">${__("Aucun cours ne vous est affecté pour cette année.")}</div>`}
		`);
	}

	$racine.on("click", "button[data-type]", function () {
		open_url_post("/api/method/" + API + "telecharger", {
			type_acte: $(this).data("type"), format: $(this).data("format"), academic_year: annee, periode: etat.periode,
		}, true);
	});

	function charger() {
		frappe.xcall(API + "mes_documents", { academic_year: annee, periode: etat.periode })
			.then((r) => { etat.data = r; rendre(); })
			.catch(() => $racine.html(`<div class="vide">${__("Aucune fiche enseignant n'est liée à votre compte.")}</div>`));
	}
	charger();
};
