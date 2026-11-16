// Saisie des notes du concours d'entrée, par code d'anonymat.
// Aucune identité (nom, numéro de table) n'est jamais affichée ici.
frappe.pages["saisie-notes-concours"].on_page_load = function (wrapper) {
	const API = "udshed.api.concours_resultats.";
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Saisie des notes du concours"),
		single_column: true,
	});

	const state = { liste: [], scolarite: false, concours: null, matiere: null, data: null, modifie: false };

	const esc = (s) => frappe.utils.escape_html(s === null || s === undefined ? "" : String(s));
	const api = (method, args) => frappe.call({ method: API + method, args }).then((r) => r.message);

	const $body = $(`
		<div class="snc">
			<div class="row" style="margin-bottom:10px">
				<div class="col-sm-5"><select class="form-control" data-f="concours"></select></div>
				<div class="col-sm-4"><select class="form-control" data-f="matiere" disabled></select></div>
				<div class="col-sm-3 text-muted small" style="padding-top:8px">
					${__("Anonymat préservé : seuls les codes sont affichés.")}
				</div>
			</div>
			<div class="snc-bandeau"></div>
			<div class="snc-table"></div>
		</div>`).appendTo(page.body);
	const $concours = $body.find('[data-f="concours"]');
	const $matiere = $body.find('[data-f="matiere"]');

	page.set_primary_action(__("Enregistrer"), enregistrer, "save");
	page.btn_primary.prop("disabled", true);

	// Rechargement de la page sur une autre route (ex. depuis le formulaire du concours).
	wrapper.snc_ouvrir = (concours) => charger_liste(concours);
	charger_liste(frappe.route_options && frappe.route_options.concours);
	frappe.route_options = null;

	function charger_liste(preselection) {
		api("concours_pour_saisie").then((r) => {
			state.liste = r.concours;
			state.scolarite = r.scolarite;
			$concours.empty().append(new Option(__("Choisir un concours…"), ""));
			r.concours.forEach((c) => $concours.append(new Option(`${c.titre} (${c.name}) — ${c.statut}`, c.name)));
			if (!r.concours.length) {
				$body.find(".snc-table").html(
					`<div class="text-muted">${__("Aucun concours en cours d'épreuves pour lequel vous pouvez saisir des notes.")}</div>`
				);
			}
			if (preselection && r.concours.some((c) => c.name === preselection)) {
				$concours.val(preselection).trigger("change");
			}
		});
	}

	$concours.on("change", () => {
		if (!confirmer_abandon()) return $concours.val(state.concours || "");
		state.concours = $concours.val() || null;
		state.matiere = null;
		state.data = null;
		const c = state.liste.find((x) => x.name === state.concours);
		$matiere.empty().append(new Option(__("Choisir une épreuve…"), "")).prop("disabled", !c);
		(c ? c.matieres : []).forEach((m) =>
			$matiere.append(new Option(m.matiere + (m.validee ? " ✔ " + __("validée") : ""), m.matiere))
		);
		afficher();
	});

	$matiere.on("change", () => {
		if (!confirmer_abandon()) return $matiere.val(state.matiere || "");
		state.matiere = $matiere.val() || null;
		charger_copies();
	});

	function confirmer_abandon() {
		return !state.modifie || window.confirm(__("Des notes ne sont pas enregistrées. Les abandonner ?"));
	}

	function charger_copies() {
		state.modifie = false;
		if (!state.concours || !state.matiere) return afficher();
		api("charger_copies", { concours: state.concours, matiere: state.matiere }).then((d) => {
			state.data = d;
			afficher();
		});
	}

	function afficher() {
		const d = state.data;
		page.clear_inner_toolbar();
		const $t = $body.find(".snc-table").empty();
		const $b = $body.find(".snc-bandeau").empty();
		page.btn_primary.prop("disabled", !(d && d.modifiable));
		if (!d) return;

		const pct = d.total ? Math.round((100 * d.saisies) / d.total) : 0;
		$b.html(`
			<div class="alert ${d.validee ? "alert-success" : "alert-info"}" style="padding:8px 12px">
				<b>${esc(d.matiere)}</b> — ${d.saisies} / ${d.total} ${__("copies saisies")} (${pct} %),
				${d.absents} ${__("absent(s)")}
				${d.validee ? " — <b>" + __("Notes validées : saisie verrouillée") + "</b>" : ""}
				${!d.modifiable && !d.validee ? " — " + __("Saisie fermée") : ""}
			</div>`);

		if (state.scolarite) {
			if (!d.validee) {
				page.add_inner_button(__("Valider les notes de l'épreuve"), valider);
			} else {
				page.add_inner_button(__("Annuler la validation"), annuler_validation);
			}
		}

		if (!d.copies.length) {
			$t.html(`<div class="text-muted">${__("Aucune copie pour cette épreuve.")}</div>`);
			return;
		}
		const ro = d.modifiable ? "" : "disabled";
		const lignes = d.copies
			.map(
				(c, i) => `
				<tr data-code="${esc(c.code)}">
					<td class="text-muted">${i + 1}</td>
					<td><b style="font-family:monospace;font-size:1.1em">${esc(c.code)}</b></td>
					<td><input type="text" inputmode="decimal" class="form-control input-sm snc-note" style="width:110px"
						value="${c.note === null || c.note === undefined ? "" : c.note}" ${ro} ${c.absent ? "disabled" : ""}></td>
					<td><input type="checkbox" class="snc-absent" ${c.absent ? "checked" : ""} ${ro}></td>
					<td class="snc-etat small">${c.saisie ? '<span class="text-success">✔</span>' : '<span class="text-muted">' + __("à saisir") + "</span>"}</td>
				</tr>`
			)
			.join("");
		$t.html(`
			<table class="table table-bordered table-condensed" style="max-width:640px">
				<thead><tr><th>#</th><th>${__("Code d'anonymat")}</th><th>${__("Note /20")}</th>
				<th>${__("Absent")}</th><th>${__("État")}</th></tr></thead>
				<tbody>${lignes}</tbody>
			</table>`);

		$t.find(".snc-note").on("input", function () {
			state.modifie = true;
			const v = normaliser($(this).val());
			$(this).toggleClass("is-invalid", v === false).css("border-color", v === false ? "#e74c3c" : "");
		});
		// Entrée : passer à la copie suivante (saisie rapide au clavier).
		$t.find(".snc-note").on("keydown", function (e) {
			if (e.key !== "Enter") return;
			e.preventDefault();
			const $inputs = $t.find(".snc-note:enabled");
			$inputs.eq($inputs.index(this) + 1).focus().select();
		});
		$t.find(".snc-absent").on("change", function () {
			state.modifie = true;
			const $note = $(this).closest("tr").find(".snc-note");
			$note.prop("disabled", this.checked);
			if (this.checked) $note.val("");
		});
		$t.find(".snc-note:enabled").first().focus();
	}

	// "" -> null ; "12,5" -> 12.5 ; hors [0, 20] ou illisible -> false
	function normaliser(v) {
		v = String(v || "").trim().replace(",", ".");
		if (v === "") return null;
		const n = Number(v);
		return Number.isFinite(n) && n >= 0 && n <= 20 ? n : false;
	}

	function enregistrer() {
		const notes = [];
		let erreur = null;
		$body.find(".snc-table tbody tr").each(function () {
			const code = $(this).data("code");
			const absent = $(this).find(".snc-absent").is(":checked");
			const note = normaliser($(this).find(".snc-note").val());
			if (!absent && note === false) erreur = erreur || code;
			notes.push({ code, note: absent ? null : note, absent: absent ? 1 : 0 });
		});
		if (erreur) {
			frappe.msgprint(__("Code {0} : la note doit être un nombre entre 0 et 20.", [erreur]));
			return;
		}
		frappe
			.call({
				method: API + "enregistrer_notes",
				args: { concours: state.concours, matiere: state.matiere, notes },
				freeze: true,
				freeze_message: __("Enregistrement…"),
			})
			.then((r) => {
				frappe.show_alert({ message: __("{0} copie(s) enregistrée(s)", [r.message.enregistrees]), indicator: "green" });
				charger_copies();
			});
	}

	function valider() {
		if (state.modifie) {
			frappe.msgprint(__("Enregistrez d'abord les notes."));
			return;
		}
		frappe.confirm(
			__("Valider les notes de « {0} » ? La saisie sera verrouillée pour tous les correcteurs.", [state.matiere]),
			() =>
				api("valider_notes", { concours: state.concours, matiere: state.matiere }).then(() => {
					frappe.show_alert({ message: __("Notes validées"), indicator: "green" });
					rafraichir_matieres();
				})
		);
	}

	function annuler_validation() {
		frappe.confirm(__("Rouvrir la saisie de « {0} » ?", [state.matiere]), () =>
			api("annuler_validation", { concours: state.concours, matiere: state.matiere }).then(() =>
				rafraichir_matieres()
			)
		);
	}

	function rafraichir_matieres() {
		const concours = state.concours, matiere = state.matiere;
		api("concours_pour_saisie").then((r) => {
			state.liste = r.concours;
			const c = state.liste.find((x) => x.name === concours);
			$matiere.empty().append(new Option(__("Choisir une épreuve…"), ""));
			(c ? c.matieres : []).forEach((m) =>
				$matiere.append(new Option(m.matiere + (m.validee ? " ✔ " + __("validée") : ""), m.matiere))
			);
			$matiere.val(matiere);
			charger_copies();
		});
	}
};

frappe.pages["saisie-notes-concours"].on_page_show = function (wrapper) {
	if (frappe.route_options && frappe.route_options.concours && wrapper.snc_ouvrir) {
		const c = frappe.route_options.concours;
		frappe.route_options = null;
		wrapper.snc_ouvrir(c);
	}
};
