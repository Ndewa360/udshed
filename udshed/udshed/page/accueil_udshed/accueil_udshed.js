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
