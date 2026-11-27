// Accueil : point d'arrivée de tout le personnel après connexion.
// Les tuiles sont construites à partir des barres latérales que l'utilisateur peut voir
// (frappe.boot.module_sidebars, déjà filtrées par ses droits), dans l'ordre du dock :
// chaque rôle ne voit donc que ses propres espaces et actions.
frappe.pages["accueil-udshed"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Accueil"), single_column: true });
	const esc = (v) => frappe.utils.escape_html(v === null || v === undefined ? "" : String(v));
	// Icône absente de la bibliothèque (ancien nom) : icône « document » à la place.
	const existe = (nom) => !!(nom && document.getElementById("icon-" + nom));
	const icone = (nom) => {
		try {
			return frappe.utils.icon(existe(nom) ? nom : "file", "md");
		} catch (e) {
			return "";
		}
	};

	$(`<style>
		.acc { max-width: 1180px; margin: 0 auto; padding: 8px 16px 40px; font-size: 15px; }
		.acc-bonjour { font-size: 22px; font-weight: 600; margin: 4px 0 2px; color: var(--text-color); }
		.acc-sous { color: var(--text-muted); margin-bottom: 22px; }
		.acc-espace { margin-bottom: 26px; }
		.acc-espace h4 { font-size: 16px; font-weight: 600; margin: 0 0 10px; color: var(--text-color);
			display: flex; align-items: center; justify-content: flex-start; gap: 8px; }
		.acc-espace h4 svg { flex: 0 0 auto; width: 18px; height: 18px; margin: 0; }
		.acc-espace h4 .icon { color: var(--text-muted); }
		.acc-tuiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 10px; }
		.acc-tuile { display: flex; align-items: center; gap: 12px; padding: 14px 16px; min-height: 58px;
			border: 1px solid var(--border-color); border-radius: 10px; background: var(--card-bg);
			color: var(--text-color); text-align: left; cursor: pointer; font-size: 15px; line-height: 1.3;
			justify-content: flex-start; width: 100%; }
		.acc-tuile > svg { flex: 0 0 auto; width: 20px; height: 20px; margin: 0; }
		.acc-tuile > span { flex: 1 1 auto; text-align: left; }
		.acc-tuile:hover, .acc-tuile:focus { border-color: var(--gray-400, #a0a7b4); background: var(--subtle-fg); outline: none; }
		.acc-tuile .icon { flex: none; color: var(--text-muted); }
		.acc-vide { padding: 32px; text-align: center; color: var(--text-muted); border: 1px dashed var(--border-color); border-radius: 10px; }
	</style>`).appendTo(page.main);

	const prenom = (frappe.boot.user && (frappe.boot.user.first_name || frappe.boot.user.full_name)) || "";
	const annee = window.Udshed && Udshed.Session && Udshed.Session.annee();
	if (annee) page.set_indicator(__("Année {0}", [annee]), "gray");

	const ordre = ((frappe.boot.dock && frappe.boot.dock.udshed) || [])
		.filter((e) => e.link_type === "Sidebar" && e.link_to !== "Accueil" && !e.hidden)
		.map((e) => e.link_to);
	const barres = frappe.boot.module_sidebars || {};
	const espaces = ordre
		.map((nom) => {
			const barre = barres[nom];
			const liens = ((barre && barre.items) || []).filter((i) => i.type === "Link" && i.link_to);
			return liens.length ? { nom: (barre && barre.label) || nom, icone: barre && barre.header_icon, liens } : null;
		})
		.filter(Boolean);

	const $racine = $(`<div class="acc">
		<div class="acc-bonjour">${esc(prenom ? __("Bonjour {0}", [prenom]) : __("Bonjour"))}</div>
		<div class="acc-sous">${__("Que souhaitez-vous faire ?")}</div>
	</div>`).appendTo(page.main);

	// File « À faire » : actions qui vous attendent, déduites de l'état des données. Elle se vide
	// d'elle-même quand l'action est faite ; au-delà du délai, une relance part, puis le responsable
	// est prévenu (udshed/notifications/attentes.py).
	$(`<style>
		.acc-taches { margin: 0 0 28px; }
		.acc-taches h4 { font-size: 16px; font-weight: 600; margin: 0 0 10px; display: flex; align-items: center; gap: 8px; }
		.acc-taches h4 .acc-nb { font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 10px;
			background: var(--blue-100, #dbeafe); color: var(--blue-700, #1d4ed8); }
		.acc-groupes { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 10px; }
		.acc-groupe { border: 1px solid var(--border-color); border-radius: 10px; background: var(--card-bg); padding: 12px 14px; }
		.acc-groupe.retard { border-left: 4px solid var(--orange-500, #f97316); }
		.acc-groupe.escalade { border-left: 4px solid var(--red-500, #ef4444); }
		.acc-groupe-tete { display: flex; justify-content: space-between; gap: 8px; font-weight: 600; margin-bottom: 6px; }
		.acc-groupe-tete .acc-compte { color: var(--text-muted); font-weight: 500; white-space: nowrap; }
		.acc-groupe ul { margin: 0; padding: 0; list-style: none; }
		.acc-groupe li { display: flex; justify-content: space-between; gap: 8px; padding: 4px 0; font-size: 14px;
			border-top: 1px solid var(--border-color); }
		.acc-groupe li:first-child { border-top: 0; }
		.acc-groupe li a { color: var(--text-color); }
		.acc-groupe li a:hover { color: var(--primary); }
		.acc-age { color: var(--text-muted); font-size: 12px; white-space: nowrap; }
		.acc-age.retard { color: var(--orange-600, #ea580c); font-weight: 600; }
		.acc-rien { color: var(--text-muted); padding: 12px 14px; border: 1px dashed var(--border-color); border-radius: 10px; }
	</style>`).appendTo(page.main);
	const $taches = $(`<div class="acc-taches"></div>`).appendTo($racine);
	const age = (j) => (j <= 0 ? __("aujourd'hui") : j === 1 ? __("depuis 1 jour") : __("depuis {0} jours", [j]));
	function charger_taches() {
		frappe.call({ method: "udshed.notifications.api.mes_taches", type: "GET" }).then((r) => {
			const groupes = r.message || [];
			const total = groupes.reduce((s, g) => s + g.nombre, 0);
			$taches.html(`<h4>${__("À faire")}${total ? ` <span class="acc-nb">${total}</span>` : ""}</h4>`);
			if (!groupes.length) {
				$taches.append(`<div class="acc-rien">${__("Rien ne vous attend pour le moment.")}</div>`);
				return;
			}
			const $grille = $(`<div class="acc-groupes"></div>`).appendTo($taches);
			groupes.forEach((g) => {
				const classe = g.escalade ? "escalade" : g.en_retard ? "retard" : "";
				const lignes = g.elements.map((e) => `<li><a href="${esc(e.lien)}">${esc(e.titre)}</a>
					<span class="acc-age ${e.age >= 3 ? "retard" : ""}">${esc(age(e.age))}</span></li>`).join("");
				const reste = g.nombre - g.elements.length;
				$grille.append(`<div class="acc-groupe ${classe}">
					<div class="acc-groupe-tete"><span>${esc(g.groupe)}</span><span class="acc-compte">${g.nombre}</span></div>
					<ul>${lignes}</ul>
					${reste > 0 ? `<div class="acc-age">${__("et {0} autre(s)", [reste])}</div>` : ""}
				</div>`);
			});
		});
	}
	charger_taches();
	wrapper.udshed_recharger = charger_taches;

	// Notifications facultatives : chacun choisit ses canaux (les obligatoires ne se coupent pas).
	page.set_secondary_action(__("Mes notifications"), () => {
		frappe.call({ method: "udshed.notifications.api.mes_preferences", type: "GET" }).then((r) => {
			const regles = (r.message || []).filter((x) => !x.obligatoire);
			const lignes = regles.map((x) => `<tr data-regle="${esc(x.code)}">
				<td>${esc(__(x.libelle))}<div class="text-muted small">${esc(__(x.categorie || ""))}</div></td>
				${["application", "email", "sms"].map((c) => {
					const dispo = x["canal_" + c];
					return `<td class="text-center">${dispo ? `<input type="checkbox" data-canal="${c}" ${x["pref_" + c] ? "checked" : ""}>` : "—"}</td>`;
				}).join("")}
			</tr>`).join("");
			const d = new frappe.ui.Dialog({
				title: __("Mes notifications"),
				size: "large",
				fields: [{ fieldtype: "HTML", fieldname: "liste" }],
				primary_action_label: __("Fermer"),
				primary_action() { d.hide(); },
			});
			d.fields_dict.liste.$wrapper.html(`
				<p class="text-muted small">${__("Les décisions et les échéances vous sont toujours envoyées. Choisissez ici comment recevoir les autres messages.")}</p>
				<div style="max-height:60vh;overflow:auto"><table class="table table-sm">
				<thead><tr><th>${__("Notification")}</th><th class="text-center">${__("Application")}</th>
				<th class="text-center">${__("E-mail")}</th><th class="text-center">SMS</th></tr></thead>
				<tbody>${lignes || `<tr><td colspan="4" class="text-muted">${__("Aucune notification facultative.")}</td></tr>`}</tbody></table></div>`);
			d.fields_dict.liste.$wrapper.on("change", "input[type=checkbox]", function () {
				const $tr = $(this).closest("tr");
				const val = (c) => ($tr.find(`[data-canal=${c}]`).length ? ($tr.find(`[data-canal=${c}]`).is(":checked") ? 1 : 0) : 1);
				frappe.call({
					method: "udshed.notifications.api.enregistrer_preference",
					args: { regle: $tr.data("regle"), application: val("application"), email: val("email"), sms: val("sms") },
				}).then(() => frappe.show_alert({ message: __("Préférence enregistrée."), indicator: "green" }));
			});
			d.show();
		});
	});

	if (!espaces.length) {
		$racine.append(`<div class="acc-vide">${__("Aucun espace ne vous est attribué. Contactez l'administrateur.")}</div>`);
		return;
	}
	espaces.forEach((espace) => {
		const $bloc = $(`<div class="acc-espace"><h4>${icone(espace.icone)}<span>${esc(__(espace.nom))}</span></h4>
			<div class="acc-tuiles"></div></div>`).appendTo($racine);
		espace.liens.forEach((lien) => {
			$(`<button type="button" class="acc-tuile">${icone(lien.icon)}<span>${esc(__(lien.label))}</span></button>`)
				.on("click", () => ouvrir(lien))
				.appendTo($bloc.find(".acc-tuiles"));
		});
	});

	function ouvrir(lien) {
		if (lien.link_type === "Page") frappe.set_route(lien.link_to);
		else if (lien.link_type === "DocType") frappe.set_route("List", lien.link_to);
		else if (lien.link_type === "Report") frappe.set_route("query-report", lien.link_to);
		else if (lien.link_type === "URL" && lien.url) window.open(lien.url, "_blank");
	}
};

// Retour sur l'accueil : la file « À faire » est rechargée (une action vient peut-être d'être faite).
frappe.pages["accueil-udshed"].on_page_show = function (wrapper) {
	if (wrapper.udshed_vu && wrapper.udshed_recharger) wrapper.udshed_recharger();
	wrapper.udshed_vu = true;
};
