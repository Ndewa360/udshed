frappe.pages["correction-copies"].on_page_load = function (wrapper) {
	const API = "udshed.api.examen_anonymat.";

	const state = {
		academic_year: null,
		session: null,
		teaching_unit: null,
		copies: [],
		busy: false,
	};

	const role_actions = ["System Manager", "Coordonateur", "Registration Manager"].some((r) =>
		frappe.boot.user.roles.includes(r)
	);

	// ----------------------------------------------------------------------
	// helpers
	// ----------------------------------------------------------------------
	function esc(s) {
		return String(s === null || s === undefined ? "" : s).replace(
			/[&<>"']/g,
			(c) =>
				({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
		);
	}

	function toast(message, indicator) {
		frappe.show_alert({ message, indicator: indicator || "green" }, 4);
	}

	function api(method, args) {
		return frappe.call({ method: API + method, args }).then((r) => r.message);
	}

	function to_num(v) {
		if (v === null || v === undefined) return null;
		if (typeof v === "string") {
			v = v.trim().replace(",", ".");
			if (v === "") return null;
		}
		const n = Number(v);
		return Number.isFinite(n) ? n : null;
	}

	function fill_select($sel, items, get_label, selected) {
		const before = selected;
		const opts = items.map((it) => ({ label: get_label(it), value: it }));
		$sel.empty()
			.append(new Option("—", ""))
			.append(...opts.map((o) => new Option(o.label, o.value)));
		if (before) $sel.val(before);
	}

	function on_select_change($sel) {
		const field = $sel.data("field");
		state[field] = $sel.val() || null;
		if (field === "academic_year") {
			state.session = null;
			load_sessions();
		}
		if (field === "session") {
			state.teaching_unit = null;
			if (state.session) load_matieres();
		}
		if (field === "teaching_unit") {
			if (state.session) load_copies();
		}
	}

	// ----------------------------------------------------------------------
	// construction de l'interface
	// ----------------------------------------------------------------------
	$(wrapper).empty();

	$page = $(wrapper);
	$page
		.append(
			'<div class="row" style="padding:8px 0">'
			+ '  <div class="col-sm-3 text-muted" style="padding-top:6px">Correction des copies d\'examen — anonymat préservé (aucune identité affichée)</div>'
			+ '  <div class="col-sm-2">'
			+ '    <select class="form-control" data-field="academic_year"><option value="">Année académique…</option></select>'
			+ '  </div>'
			+ '  <div class="col-sm-3">'
			+ '    <select class="form-control" data-field="session"><option value="">Session d\'examen…</option></select>'
			+ '  </div>'
			+ '  <div class="col-sm-2">'
			+ '    <select class="form-control" data-field="teaching_unit"><option value="">Matière (toutes)…</option></select>'
			+ '  </div>'
			+ '  <div class="col-sm-2">'
			+ '    <button class="btn btn-primary btn-sm" id="cb_reload" disabled>Charger</button>'
			+ '  </div>'
			+ '</div>'
			+ '<div class="row" style="padding:4px 0">'
			+ '  <div class="col-sm-12" id="resume_wrap"></div>'
			+ '</div>'
			+ '<div class="row" style="padding:4px 0">'
			+ '  <div class="col-sm-12">'
			+ '    <div class="btn-group" role="group">'
			+ (role_actions
				? '      <button class="btn btn-default btn-sm" id="cb_generer">Générer les codes</button>'
					+ '      <button class="btn btn-default btn-sm" id="cb_valider">Valider les corrections</button>'
					+ '      <button class="btn btn-danger btn-sm" id="cb_lever">Lever l\'anonymat</button>'
				: "")
			+ '    </div>'
			+ '  </div>'
			+ '</div>'
			+ '<div class="row" style="padding:6px 0">'
			+ '  <div class="col-sm-12">'
			+ '    <div class="panel panel-default"><div class="panel-body" id="copies_wrap">'
			+ '      <div class="text-muted">Sélectionnez une session puis chargez les copies.</div>'
			+ '    </div></div>'
			+ '  </div>'
			+ '</div>'
		);

	const $academic_year = $page.find('[data-field="academic_year"]');
	const $session = $page.find('[data-field="session"]');
	const $ue = $page.find('[data-field="teaching_unit"]');
	$academic_year.data("field", "academic_year");
	$session.data("field", "session");
	$ue.data("field", "teaching_unit");

	$academic_year.on("change", function () {
		on_select_change($academic_year);
	});
	$session.on("change", function () {
		on_select_change($session);
	});
	$ue.on("change", function () {
		on_select_change($ue);
	});
	$("#cb_reload").on("click", function () {
		load_matieres();
	});
	$("#cb_generer").on("click", function () {
		if (!state.session) return toast("Choisissez d'abord une session", "orange");
		return api("generer_codes", { session: state.session }).then((r) => {
			toast("Codes générés : " + (r.genere || 0));
			load_matieres();
		});
	});
	$("#cb_valider").on("click", function () {
		if (!state.session) return toast("Choisissez d'abord une session", "orange");
		return api("valider_corrections", {
			session: state.session,
			teaching_unit: state.teaching_unit || undefined,
		}).then((r) => {
			toast("Copies validées : " + (r.validees || 0));
			load_matieres();
		});
	});
	$("#cb_lever").on("click", function () {
		if (!state.session) return toast("Choisissez d'abord une session", "orange");
		frappe.confirm(
			"Lever l'anonymat enregistre définitivement les notes corrigées dans le flux de validation. Continuer ?",
			() =>
				api("lever_anonymat", { session: state.session }).then((r) => {
					toast("Notes injectées : " + (r.injectees || 0) + " — codes levés : " + (r.levees || 0));
					load_matieres();
				})
		);
	});

	function render_resume(matieres) {
		const wrap = $page.find("#resume_wrap");
		const entries = Object.entries(matieres || {});
		if (!entries.length) {
			wrap.html('<div class="text-muted">Aucune copie générée pour cette session.</div>');
			$ue.empty().append(new Option("Matière (toutes)…", ""));
			return;
		}
		let html = '<table class="table table-condensed table-bordered" style="margin-bottom:0">'
			+ "<thead><tr><th>Matière</th><th>Total</th><th>Corrigées</th><th>Validées</th><th>Manquantes</th></tr></thead><tbody>";
		const ue_vals = [];
		for (const [ue, info] of entries) {
			ue_vals.push(ue);
			html += "<tr><td>" + esc(ue) + "</td><td>" + info.total + "</td><td>" + info.corrigees
				+ "</td><td>" + info.validees + "</td><td>" + info.manquantes + "</td></tr>";
		}
		html += "</tbody></table>";
		wrap.html(html);

		const current = $ue.val();
		$ue.empty()
			.append(new Option("Matière (toutes)…", ""))
			.append(...ue_vals.map((v) => new Option(v, v)));
		if (current && ue_vals.includes(current)) $ue.val(current);
		if (state.teaching_unit && !ue_vals.includes(state.teaching_unit)) {
			state.teaching_unit = null;
			$ue.val("");
		}
		load_copies();
	}

	function load_sessions() {
		api("obtenir_sessions", { academic_year: state.academic_year || undefined }).then((r) => {
			fill_select($session, r.sessions, (s) => (s.name || "") + " — " + (s.type_dexamen || ""), state.session);
			if (state.session) load_matieres();
		});
	}

	function load_matieres() {
		if (!state.session) return;
		api("obtenir_ues_session", { session: state.session }).then((r) => render_resume(r.matieres));
	}

	function load_copies() {
		if (!state.session) return;
		state.busy = true;
		$("#cb_reload").attr("disabled", true);
		return api("charger_copies", {
			session: state.session,
			teaching_unit: state.teaching_unit || undefined,
		}).then((r) => {
			state.copies = r.copies || [];
			render_copies();
			state.busy = false;
			$("#cb_reload").attr("disabled", false);
		});
	}

	function render_copies() {
		const wrap = $page.find("#copies_wrap");
		if (!state.copies.length) {
			wrap.html('<div class="text-muted">Aucune copie pour cette sélection.</div>');
			return;
		}
		let html = '<table class="table table-bordered" style="margin-bottom:0">'
			+ "<thead><tr><th>Code</th><th>Fichier</th><th>Note /20</th><th>Observation</th><th>Statut</th><th>Absent</th><th></th></tr></thead><tbody>";
		for (const c of state.copies) {
			html += "<tr data-name=\"" + esc(c.name) + "\">"
				+ "<td><b>" + esc(c.code_anonymat) + "</b></td>"
				+ "<td>"
				+ (c.fichier_copie ? '<a href="' + esc(c.fichier_copie) + '" target="_blank">Voir la copie</a>' : "—")
				+ ' <button class="btn btn-xs btn-default btn-upload" type="button">Téléverser</button>'
				+ "</td>"
				+ "<td><input class=\"form-control input-sm inp-note\" type=\"text\" size=\"4\" value=\"" + esc(c.note_examen) + "\"></td>"
				+ "<td><input class=\"form-control input-sm inp-obs\" type=\"text\" value=\"" + esc(c.observation) + "\"></td>"
				+ "<td>" + esc(c.statut_correction) + "</td>"
				+ "<td><input class=\"inp-absent\" type=\"checkbox\"" + (c.absent ? " checked" : "") + "></td>"
				+ "<td><button class=\"btn btn-primary btn-xs btn-save\" type=\"button\">Enregistrer</button></td>"
				+ "</tr>";
		}
		html += "</tbody></table>";
		wrap.html(html);

		wrap.find(".btn-upload").on("click", function () {
			const name = $(this).closest("tr").data("name");
			new frappe.ui.FileUploader({
				doctype: "Copie Examen",
				docname: name,
				is_private: 1,
				on_success: (file) =>
					frappe.xcall("frappe.client.set_value", {
						doc: "Copie Examen",
						name,
						fieldname: { fichier_copie: file.file_url },
					}).then(() => toast("Copie téléversée")).then(load_copies),
			});
		});

		wrap.find(".btn-save").on("click", function () {
			const $tr = $(this).closest("tr");
			const name = $tr.data("name");
			const note = $tr.find(".inp-note").val();
			const observation = $tr.find(".inp-obs").val();
			const absent = $tr.find(".inp-absent").is(":checked") ? 1 : 0;
			if (!absent && to_num(note) === null) {
				return toast("Saisissez une note (0 à 20) ou cochez « Absent »", "orange");
			}
			api("enregistrer_correction", { copie: name, note, observation, absent }).then(() => {
				toast("Correction enregistrée");
				load_copies();
				load_matieres();
			});
		});
	}

	// ----------------------------------------------------------------------
	// initialisation
	// ----------------------------------------------------------------------
	api("obtenir_sessions", {}).then((r) => {
		fill_select($academic_year, r.years, (y) => y, state.academic_year);
		fill_select($session, r.sessions, (s) => (s.name || "") + " — " + (s.type_dexamen || ""), state.session);
	});
};