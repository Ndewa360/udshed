// Direction académique (DAA) : indicateurs de chaque faculté et calendrier de saisie de l'établissement.
// Données : udshed.api.direction.tableau_etablissement.
frappe.pages["direction-academique"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Direction académique"), single_column: true });
	const annee = (window.Udshed && Udshed.Session && Udshed.Session.annee()) || frappe.defaults.get_user_default("academic_year");
	if (annee) page.set_indicator(__("Année {0}", [annee]), "gray");
	page.set_primary_action(__("Nouvelle période de saisie"), () => frappe.new_doc("Periode Saisie Notes", { academic_year: annee }), "add");
	page.add_inner_button(__("Calendrier de saisie"), () => frappe.set_route("List", "Periode Saisie Notes", { academic_year: annee }));
	const esc = (v) => frappe.utils.escape_html(v === null || v === undefined ? "" : String(v));
	const n = (v) => (Number(v) || 0).toLocaleString("fr-FR", { maximumFractionDigits: 1 });
	const date = (v) => (v ? frappe.datetime.str_to_user(v) : "");
	$(`<style>
		.dir { max-width: 1280px; margin: 0 auto; padding: 4px 0 40px; font-size: 15px; }
		.dir h5 { font-size: 16px; font-weight: 600; margin: 26px 0 10px; }
		.dir-cartes { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; }
		.dir-carte { border: 1px solid var(--border-color); border-radius: 10px; padding: 12px 14px; background: var(--card-bg); }
		.dir-carte .v { font-size: 21px; font-weight: 600; }
		.dir-carte .l { color: var(--text-muted); font-size: 13px; margin-top: 2px; }
		.dir-carte.alerte .v { color: var(--orange-600, #b54708); }
		.dir table { width: 100%; border-collapse: collapse; background: var(--card-bg); border: 1px solid var(--border-color); }
		.dir th { text-align: left; font-weight: 600; color: var(--text-muted); font-size: 13px; padding: 9px 12px; background: var(--subtle-fg); }
		.dir td { padding: 9px 12px; border-top: 1px solid var(--border-color); vertical-align: top; }
		.dir td.n, .dir th.n { text-align: right; font-variant-numeric: tabular-nums; }
		.dir .vide { padding: 22px; text-align: center; color: var(--text-muted); border: 1px dashed var(--border-color); border-radius: 10px; }
		.dir .etat { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; background: var(--subtle-fg); }
		.dir .etat.ouverte { background: var(--green-50, #eef6f0); color: var(--green-700, #2f6b46); }
		.dir .etat.fermée { background: var(--gray-100, #f2f4f7); color: var(--text-muted); }
		.dir .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
	</style>`).appendTo(page.main);
	const $racine = $(`<div class="dir"></div>`).appendTo(page.main);

	const carte = (v, l, alerte) => `<div class="dir-carte ${alerte ? "alerte" : ""}"><div class="v">${v}</div><div class="l">${esc(l)}</div></div>`;
	const cartes = (t) => `<div class="dir-cartes">
		${carte(n(t.inscrits), __("Inscrits"))}
		${carte(n(t.reinscrits), __("Réinscrits"))}
		${carte(n(t.avancement) + " %", __("Avancement des cours ({0} en retard)", [n(t.cours_en_retard)]), t.cours_en_retard > 0)}
		${carte(n(t.taux_saisie) + " %", __("Saisies confirmées ({0}/{1})", [n(t.saisies_confirmees), n(t.saisies_attendues)]))}
		${carte(n(t.taux_reussite) + " %", __("Taux de réussite"))}
		${carte(n(t.derogations), __("Dérogations à traiter"), t.derogations > 0)}
		${carte(n(t.actes_a_signer), __("Actes à signer"), t.actes_a_signer > 0)}
	</div>`;
	const periodes = (liste) => liste.length ? `<table><thead><tr><th>${__("Semestre")}</th><th>${__("Évaluation")}</th>
		<th>${__("Portée")}</th><th>${__("Ouverture")}</th><th>${__("Date limite")}</th><th>${__("État")}</th></tr></thead><tbody>
		${liste.map((p) => `<tr><td>${esc(p.semestre)}</td><td>${esc(__(p.type_evaluation))}</td><td>${esc(p.portee)}</td>
			<td>${esc(date(p.ouverture))}</td><td>${esc(date(p.fermeture))}</td>
			<td><span class="etat ${esc(p.etat)}">${esc(__(p.etat))}</span></td></tr>`).join("")}</tbody></table>`
		: `<div class="vide">${__("Aucune période de saisie n'est fixée pour cette année : la saisie des notes est libre.")}</div>`;
	function rendre(d) {
		const lignes = d.lignes.map((l) => `<tr><td><b>${esc(l.libelle)}</b>${l.doyen ? `<div class="text-muted small">${__("Doyen")} : ${esc(l.doyen)}</div>` : ""}</td>
			<td class="n">${n(l.inscrits)}</td><td class="n">${n(l.reinscrits)}</td><td class="n">${n(l.avancement)} %</td>
			<td class="n">${n(l.taux_saisie)} %</td><td class="n">${n(l.taux_reussite)} %</td><td class="n">${n(l.derogations)}</td>
			<td class="n">${n(l.actes_a_signer)}</td></tr>`).join("");
		$racine.html(`
			<h5 style="margin-top:6px">${__("Établissement")}</h5>
			${cartes(d.total)}
			<h5>${__("Par faculté")}</h5>
			${lignes ? `<table><thead><tr><th>${__("Faculté")}</th><th class="n">${__("Inscrits")}</th><th class="n">${__("Réinscrits")}</th>
				<th class="n">${__("Avancement")}</th><th class="n">${__("Saisie confirmée")}</th><th class="n">${__("Réussite")}</th>
				<th class="n">${__("Dérogations")}</th><th class="n">${__("Actes à signer")}</th></tr></thead><tbody>${lignes}</tbody></table>`
				: `<div class="vide">${__("Aucune faculté.")}</div>`}
			<h5>${__("Calendrier de saisie des notes")}</h5>
			${periodes(d.periodes)}`);
	}
	frappe.xcall("udshed.api.direction.tableau_etablissement", { academic_year: annee }).then(rendre);
};
