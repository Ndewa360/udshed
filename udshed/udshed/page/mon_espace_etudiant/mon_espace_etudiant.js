// Mon espace étudiant : lecture seule (profil, grille, planning, résultats).
// Toutes les données viennent de udshed.api.etudiant, limité au compte connecté.
frappe.pages["mon-espace-etudiant"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Mon espace étudiant"), single_column: true });
	const API = "udshed.api.etudiant.";
	const $racine = $(`
		<div class="mee">
			<div class="mee-profil"></div>
			<div class="mee-onglets" role="tablist">
				<button class="mee-onglet actif" data-onglet="grille" role="tab">${__("Ma grille d'enseignement")}</button>
				<button class="mee-onglet" data-onglet="planning" role="tab">${__("Mon planning")}</button>
				<button class="mee-onglet" data-onglet="resultats" role="tab">${__("Mes résultats")}</button>
				<button class="mee-onglet" data-onglet="reinscription" role="tab">${__("Ma réinscription")}</button>
			</div>
			<div class="mee-zone"></div>
		</div>`).appendTo(page.main);

	$(`<style>
		.mee { max-width: 1100px; margin: 0 auto; padding: 8px 0 32px; }
		.mee-profil { display: flex; gap: 16px; align-items: center; padding: 16px 18px; border: 1px solid var(--border-color);
			border-radius: 12px; background: var(--card-bg); margin-bottom: 16px; flex-wrap: wrap; }
		.mee-photo { width: 64px; height: 64px; border-radius: 50%; object-fit: cover; background: var(--control-bg); }
		.mee-nom { font-size: 18px; font-weight: 700; }
		.mee-meta { color: var(--text-muted); font-size: 13px; }
		.mee-onglets { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
		.mee-onglet { border: 1px solid var(--border-color); background: var(--card-bg); border-radius: 999px; padding: 6px 14px; font-size: 13px; }
		.mee-onglet.actif { background: var(--primary); color: #fff; border-color: var(--primary); }
		.mee-zone table { width: 100%; }
		.mee-vide { padding: 28px; text-align: center; color: var(--text-muted); border: 1px dashed var(--border-color); border-radius: 12px; }
		.mee-semaine { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
		.mee-jour { margin: 14px 0 6px; font-weight: 700; color: var(--primary); }
		.mee-seance { display: flex; gap: 14px; padding: 8px 12px; border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 6px; background: var(--card-bg); }
		.mee-heure { font-weight: 600; min-width: 110px; font-variant-numeric: tabular-nums; }
	</style>`).appendTo(page.main);

	const esc = (v) => frappe.utils.escape_html(v === null || v === undefined ? "" : String(v));
	const $zone = $racine.find(".mee-zone");
	let profil = {};
	let lundi = moment().startOf("isoWeek").format("YYYY-MM-DD");

	frappe.call({ method: API + "profil" }).then((r) => {
		profil = r.message || {};
		$racine.find(".mee-profil").html(`
			${profil.photo ? `<img class="mee-photo" src="${esc(profil.photo)}" alt="">` : `<div class="mee-photo"></div>`}
			<div>
				<div class="mee-nom">${esc(profil.nom_complet)}</div>
				<div class="mee-meta">${__("Matricule")} <b>${esc(profil.matricule)}</b> · ${esc(profil.filiere)} ${esc(profil.niveau)}
					${profil.annee ? " · " + esc(profil.annee) : ""}</div>
				<div class="mee-meta">${esc(profil.email)}</div>
			</div>`);
		afficher("grille");
	});

	$racine.on("click", ".mee-onglet", function () {
		$racine.find(".mee-onglet").removeClass("actif");
		$(this).addClass("actif");
		afficher($(this).data("onglet"));
	});

	function afficher(onglet) {
		if (onglet === "grille") return grille();
		if (onglet === "planning") return planning();
		if (onglet === "resultats") return resultats();
		$zone.html(`<div class="mee-vide">${__("La réinscription se fait chaque année pendant la session ouverte.")}<br><br>
			<a class="btn btn-primary btn-sm" href="/app/reinscription_etudiant">${__("Ouvrir ma réinscription")}</a></div>`);
	}

	function grille() {
		$zone.html(`<div class="text-muted">${__("Chargement...")}</div>`);
		frappe.call({ method: API + "ma_grille" }).then((r) => {
			const g = r.message || {};
			if (!(g.cours || []).length) {
				$zone.html(`<div class="mee-vide">${__("Aucune UE n'est encore enregistrée pour vous cette année.")}</div>`);
				return;
			}
			const lignes = g.cours.map((c) => `<tr><td>${esc(c.code)}</td><td>${esc(c.intitule)}</td><td>${esc(c.semestre)}</td>
				<td class="text-right">${esc(c.credits)}</td><td>${esc((c.enseignants || []).join(", "))}</td></tr>`).join("");
			$zone.html(`<div class="mee-meta" style="margin-bottom:8px">${esc(g.filiere)} ${esc(g.niveau)} · ${esc(g.annee)} ·
				${__("Total")} <b>${esc(g.total_credits)}</b> ${__("crédits")}</div>
				<div class="table-responsive"><table class="table table-bordered table-sm">
				<thead><tr><th>${__("Code")}</th><th>${__("Unité d'enseignement")}</th><th>${__("Semestre")}</th>
				<th class="text-right">${__("Crédits")}</th><th>${__("Enseignants")}</th></tr></thead><tbody>${lignes}</tbody></table></div>`);
		});
	}

	function planning() {
		$zone.html(`<div class="text-muted">${__("Chargement...")}</div>`);
		frappe.call({ method: API + "mon_planning", args: { week_start: lundi } }).then((r) => {
			const p = r.message || {};
			lundi = p.debut || lundi;
			let html = `<div class="mee-semaine">
				<button class="btn btn-default btn-xs mee-prec">&larr; ${__("Semaine précédente")}</button>
				<b>${__("Semaine du {0} au {1}", [frappe.datetime.str_to_user(p.debut), frappe.datetime.str_to_user(p.fin)])}</b>
				<button class="btn btn-default btn-xs mee-suiv">${__("Semaine suivante")} &rarr;</button></div>`;
			if (!(p.seances || []).length) {
				html += `<div class="mee-vide">${__("Aucune séance programmée cette semaine.")}</div>`;
			} else {
				let jour = "";
				p.seances.forEach((s) => {
					if (s.jour !== jour) {
						jour = s.jour;
						html += `<div class="mee-jour">${esc(moment(s.jour).format("dddd D MMMM"))}</div>`;
					}
					const lieu = s.mode === "En ligne" ? __("En ligne") : [s.batiment, s.salle].filter(Boolean).join(" · ") || __("Salle à préciser");
					html += `<div class="mee-seance"><div class="mee-heure">${esc(s.debut)} – ${esc(s.fin)}</div>
						<div><b>${esc(s.cours)}</b> <span class="text-muted">${esc(s.type)}</span><div class="mee-meta">${esc(lieu)}</div></div></div>`;
				});
			}
			$zone.html(html);
			$zone.find(".mee-prec").on("click", () => { lundi = frappe.datetime.add_days(lundi, -7); planning(); });
			$zone.find(".mee-suiv").on("click", () => { lundi = frappe.datetime.add_days(lundi, 7); planning(); });
		});
	}

	function resultats() {
		$zone.html(`<div class="text-muted">${__("Chargement...")}</div>`);
		frappe.call({ method: API + "mes_resultats" }).then((r) => {
			const lignes = (r.message || {}).resultats || [];
			if (!lignes.length) {
				$zone.html(`<div class="mee-vide">${__("Aucun résultat publié pour le moment.")}</div>`);
				return;
			}
			const corps = lignes.map((l) => `<tr><td>${esc(l.academic_year)}</td><td>${esc(l.semestre)}</td><td>${esc(l.ue_name || l.teaching_unit)}</td>
				<td class="text-right">${l.note_finale === null || l.note_finale === undefined ? "" : esc(Number(l.note_finale).toFixed(2))}</td>
				<td>${esc(l.grade)}</td><td>${esc(l.statut)}${l.est_rattrapage ? " (" + __("rattrapage") + ")" : ""}</td></tr>`).join("");
			$zone.html(`<div class="table-responsive"><table class="table table-bordered table-sm">
				<thead><tr><th>${__("Année")}</th><th>${__("Semestre")}</th><th>${__("UE")}</th><th class="text-right">${__("Note /20")}</th>
				<th>${__("Grade")}</th><th>${__("Statut")}</th></tr></thead><tbody>${corps}</tbody></table></div>`);
		});
	}
};
