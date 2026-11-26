// Convention de vacation : vue d'ensemble (heures, montants, cours, documents, scan signé),
// aperçu à l'écran et génération du document à signer (PDF / Word).
frappe.ui.form.on("Convention Vacation", {
	refresh(frm) {
		const champ = frm.get_field("synthese");
		if (frm.is_new()) {
			champ.$wrapper.html(`<div class="text-muted">${__("Enregistrez la convention pour voir la synthèse.")}</div>`);
			return;
		}
		const args = { type_acte: "Convention de vacation", teacher: frm.doc.teacher,
			academic_year: frm.doc.academic_year, convention: frm.doc.name };
		frm.add_custom_button(__("Aperçu"), () =>
			window.open("/api/method/udshed.api.documents_enseignant.apercu?" + new URLSearchParams(args).toString(), "_blank"));
		const telecharger = (format) => open_url_post("/api/method/udshed.api.documents_enseignant.telecharger", { ...args, format }, true);
		frm.add_custom_button(__("PDF"), () => telecharger("pdf"), __("Convention à signer"));
		frm.add_custom_button(__("Word"), () => telecharger("docx"), __("Convention à signer"));
		frappe.xcall("udshed.api.documents_enseignant.synthese_convention", { convention: frm.doc.name })
			.then((s) => champ.$wrapper.html(synthese(s)));
	},
});

const SYMBOLES_CONV = { XAF: "FCFA", XOF: "FCFA", EUR: "€", USD: "$" };

function synthese(s) {
	const esc = (v) => frappe.utils.escape_html(v === null || v === undefined ? "" : String(v));
	const h = (v) => (Number(v) || 0).toLocaleString("fr-FR", { maximumFractionDigits: 1 });
	const argent = (v) => `${Math.round(Number(v) || 0).toLocaleString("fr-FR")} ${SYMBOLES_CONV[s.devise] || s.devise || ""}`;
	const carte = (v, l) => `<div class="cv-carte"><div class="v">${v}</div><div class="l">${esc(l)}</div></div>`;
	const lignes = (s.lignes || []).map((l) => `<tr><td>${esc(l.intitule)}</td><td>${esc(l.classes)}</td><td>${esc(l.type)}</td>
		<td class="n">${h(l.prevu)}</td><td class="n">${h(l.fait)}</td><td class="n">${argent(l.montant)}</td></tr>`).join("");
	const docs = (s.documents || []).map((d) => `<tr><td><a href="/desk/document-enseignant/${encodeURIComponent(d.name)}">${esc(d.name)}</a></td>
		<td>${esc(__(d.type_document))}</td><td>${esc(d.periode || "")}</td><td>${esc(frappe.datetime.str_to_user(d.genere_le) || "")}</td></tr>`).join("");
	let scan = `<div class="text-muted">${__("Aucun scan joint. Une fois signée, joignez la convention dans « Convention signée (scan) ».")}</div>`;
	if (s.scan) {
		const url = encodeURI(s.scan);
		scan = /\.pdf$/i.test(s.scan)
			? `<iframe src="${url}" class="cv-scan"></iframe>`
			: (/\.(png|jpe?g|gif|webp)$/i.test(s.scan) ? `<img src="${url}" class="cv-scan-img">` : `<a href="${url}" target="_blank">${esc(s.scan)}</a>`);
	}
	return `<style>
		.cv { font-size: 14px; }
		.cv-cartes { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin-bottom: 16px; }
		.cv-carte { border: 1px solid var(--border-color); border-radius: 10px; padding: 12px 14px; background: var(--card-bg); }
		.cv-carte .v { font-size: 19px; font-weight: 600; }
		.cv-carte .l { color: var(--text-muted); font-size: 13px; }
		.cv h6 { font-weight: 600; margin: 16px 0 8px; font-size: 14px; }
		.cv table { width: 100%; border-collapse: collapse; border: 1px solid var(--border-color); }
		.cv th { text-align: left; font-weight: 600; color: var(--text-muted); font-size: 13px; padding: 8px 10px; background: var(--subtle-fg); }
		.cv td { padding: 8px 10px; border-top: 1px solid var(--border-color); }
		.cv .n { text-align: right; font-variant-numeric: tabular-nums; }
		.cv-scan { width: 100%; height: 520px; border: 1px solid var(--border-color); border-radius: 8px; }
		.cv-scan-img { max-width: 100%; border: 1px solid var(--border-color); border-radius: 8px; }
		.cv-alerte { color: var(--red-600, #b42318); margin-bottom: 10px; }
	</style>
	<div class="cv">
		${s.alerte_tarif ? `<div class="cv-alerte">${__("Tarif horaire manquant pour « {0} » (Réglages › paiements par grade).", [esc(s.alerte_tarif)])}</div>` : ""}
		<div class="cv-cartes">
			${carte(h(s.volume_convenu) + " h", __("Volume convenu"))}
			${carte(h(s.heures_prevues) + " h", __("Heures prévues (grille)"))}
			${carte(h(s.heures_faites) + " h", __("Heures faites"))}
			${carte(argent(s.taux_convenu || s.taux), __("Taux horaire"))}
			${carte(argent(s.montant_previsionnel), __("Montant prévisionnel"))}
			${carte(argent(s.net), __("Net dû à ce jour"))}
		</div>
		<h6>${__("Cours de l'enseignant")}</h6>
		${lignes ? `<table><thead><tr><th>${__("Cours")}</th><th>${__("Classes")}</th><th>${__("Type")}</th>
			<th class="n">${__("Prévu (h)")}</th><th class="n">${__("Fait (h)")}</th><th class="n">${__("Montant")}</th></tr></thead>
			<tbody>${lignes}</tbody></table>` : `<div class="text-muted">${__("Aucun cours affecté pour cette année.")}</div>`}
		<h6>${__("Documents produits")}</h6>
		${docs ? `<table><thead><tr><th>${__("N°")}</th><th>${__("Document")}</th><th>${__("Période")}</th><th>${__("Généré le")}</th></tr></thead>
			<tbody>${docs}</tbody></table>` : `<div class="text-muted">${__("Aucun document produit.")}</div>`}
		<h6>${__("Convention signée")}</h6>
		${scan}
	</div>`;
}
