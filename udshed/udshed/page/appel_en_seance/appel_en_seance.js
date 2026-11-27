// Appel en séance : l'enseignant marque les présences de ses séances (utilisable au téléphone).
// Un étudiant qui atteint le seuil d'absences d'une matière est signalé à la coordination,
// qui décide de la suite (udshed/utils/assiduite.py).
frappe.pages["appel-en-seance"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Appel en séance"), single_column: true });
	const esc = (v) => frappe.utils.escape_html(v === null || v === undefined ? "" : String(v));
	const STATUTS = ["Présent", "Absent", "Retard", "Excusé"];

	$(`<style>
		.app { max-width: 920px; margin: 0 auto; padding: 8px 12px 40px; font-size: 15px; }
		.app-seance { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 12px 14px;
			border: 1px solid var(--border-color); border-radius: 10px; margin-bottom: 8px; background: var(--card-bg); cursor: pointer; }
		.app-seance:hover { border-color: var(--gray-400, #a0a7b4); }
		.app-seance .app-quand { color: var(--text-muted); font-size: 13px; }
		.app-etat { font-size: 12px; white-space: nowrap; }
		.app-ligne { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 8px 0;
			border-bottom: 1px solid var(--border-color); }
		.app-choix { display: flex; gap: 4px; flex-wrap: wrap; justify-content: flex-end; }
		.app-choix button { min-width: 40px; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border-color);
			background: var(--card-bg); font-size: 13px; }
		.app-choix button.actif[data-s="Présent"] { background: var(--green-100, #dcfce7); border-color: var(--green-500, #22c55e); }
		.app-choix button.actif[data-s="Absent"] { background: var(--red-100, #fee2e2); border-color: var(--red-500, #ef4444); }
		.app-choix button.actif[data-s="Retard"] { background: var(--orange-100, #ffedd5); border-color: var(--orange-500, #f97316); }
		.app-choix button.actif[data-s="Excusé"] { background: var(--blue-100, #dbeafe); border-color: var(--blue-500, #3b82f6); }
		.app-vide { padding: 28px; text-align: center; color: var(--text-muted); border: 1px dashed var(--border-color); border-radius: 10px; }
		@media (max-width: 560px) { .app-ligne { flex-direction: column; align-items: flex-start; } }
	</style>`).appendTo(page.main);
	const $racine = $(`<div class="app"></div>`).appendTo(page.main);

	function liste() {
		page.clear_primary_action();
		page.set_title(__("Appel en séance"));
		$racine.html(`<p class="text-muted">${__("Vos séances des 7 derniers jours et de demain. Touchez une séance pour faire l'appel.")}</p>`);
		frappe.call({ method: "udshed.utils.assiduite.mes_seances", type: "GET" }).then((r) => {
			const seances = r.message || [];
			if (!seances.length) {
				$racine.append(`<div class="app-vide">${__("Aucune séance sur cette période.")}</div>`);
				return;
			}
			seances.forEach((s) => {
				const etat = s.appel
					? `<span class="indicator-pill ${s.absents ? "orange" : "green"} app-etat">${__("Appel fait")} · ${__("{0} absent(s)", [s.absents || 0])}</span>`
					: `<span class="indicator-pill gray app-etat">${__("À faire")}</span>`;
				$(`<div class="app-seance"><div><div><strong>${esc(s.intitule || s.cours)}</strong> · ${esc(s.type)}</div>
					<div class="app-quand">${esc(frappe.datetime.str_to_user(s.date))}${s.salle ? " · " + esc(s.salle) : ""}</div></div>${etat}</div>`)
					.on("click", () => appel(s.name)).appendTo($racine);
			});
		});
	}

	function appel(planning_item) {
		frappe.call({ method: "udshed.utils.assiduite.preparer_appel", args: { planning_item }, type: "GET" }).then((r) => {
			const a = r.message;
			const presences = a.presences.map((p) => ({ ...p }));
			page.set_title(a.intitule || __("Appel"));
			page.set_primary_action(__("Enregistrer l'appel"), () => {
				frappe.call({
					method: "udshed.utils.assiduite.enregistrer_appel",
					args: { planning_item, presences: JSON.stringify(presences) },
					freeze: true,
				}).then((res) => {
					frappe.show_alert({ message: __("Appel enregistré : {0} absent(s).", [res.message.absents]), indicator: "green" });
					liste();
				});
			});
			$racine.html(`<div class="d-flex justify-content-between align-items-center mb-2">
				<button class="btn btn-default btn-sm app-retour">${__("← Séances")}</button>
				<span class="text-muted">${esc(frappe.datetime.str_to_user(a.date))} · ${__("{0} étudiant(s)", [presences.length])}</span></div>
				<div class="mb-2"><button class="btn btn-default btn-xs app-tous">${__("Tous présents")}</button></div>`);
			$racine.find(".app-retour").on("click", liste);
			if (!presences.length) {
				$racine.append(`<div class="app-vide">${__("Aucun étudiant inscrit à ce cours.")}</div>`);
				return;
			}
			const $liste = $(`<div></div>`).appendTo($racine);
			const dessiner = () => {
				$liste.html(presences.map((p, i) => `<div class="app-ligne" data-i="${i}"><span>${esc(p.nom)}</span>
					<div class="app-choix">${STATUTS.map((s) => `<button type="button" data-s="${s}" class="${p.statut === s ? "actif" : ""}">${esc(__(s))}</button>`).join("")}</div></div>`).join(""));
			};
			dessiner();
			$liste.on("click", "button[data-s]", function () {
				presences[$(this).closest(".app-ligne").data("i")].statut = $(this).data("s");
				dessiner();
			});
			$racine.find(".app-tous").on("click", () => { presences.forEach((p) => (p.statut = "Présent")); dessiner(); });
		});
	}

	liste();
};
