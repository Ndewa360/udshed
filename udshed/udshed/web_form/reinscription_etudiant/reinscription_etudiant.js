frappe.ready(() => {
	const form = frappe.web_form;

	function esc(s) {
		return String(s || "").replace(/[&<>"']/g, c => ({
			"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
		}[c]));
	}

	form.on("student", (field, value) => {
		if (value) {
			verifyStudent(value);
		} else {
			form.set_value("filiere", "");
			form.set_value("niveau", "");
			removeStudentInfo();
			removeReinscriptions();
		}
	});

	// Auto-fill from URL parameter ?student=XXX
	const urlParams = new URLSearchParams(window.location.search);
	const prefillStudent = urlParams.get("student");
	if (prefillStudent) {
		form.set_value("student", prefillStudent);
	}

	function verifyStudent(matricule) {
		removeStudentInfo();
		removeReinscriptions();
		$(`<div id="student-loading" class="alert alert-light border text-center" style="margin:15px 0;">
			<span class="text-muted">Vérification en cours…</span></div>`)
			.insertAfter($('input[data-fieldname="student"]').closest(".frappe-control"));

		frappe.call({
			method: "udshed.udshed.web_form.reinscription_etudiant.reinscription_etudiant.verify_student",
			args: { matricule },
			callback: (r) => {
				$("#student-loading").remove();
				if (!r.message || !r.message.exists) return;
				const info = r.message;

				form.set_value("filiere", info.filiere || "");
				form.set_value("niveau", info.niveau_suivant || info.niveau || "");
				if (info.semestre) form.set_value("semestre", info.semestre);

				showStudentInfo(info);
			},
			error: () => {
				$("#student-loading").remove();
			}
		});
	}

	function showStudentInfo(info) {
		removeStudentInfo();

		const niveau_label = info.niveau_suivant || info.niveau || "Non défini";
		const info_html = `
			<div id="student-info-card" class="alert alert-info" style="margin: 15px 0;">
				<h5 class="alert-heading mb-2">Étudiant identifié</h5>
				<div class="mb-0">
					<p class="mb-1"><strong>Nom :</strong> ${esc(info.student_name)}</p>
					<p class="mb-1"><strong>Matricule :</strong> ${esc(info.matricule)}</p>
					<p class="mb-1"><strong>Email :</strong> ${esc(info.email || "—")}</p>
					<p class="mb-1"><strong>Filière :</strong> ${esc(info.filiere_label || "Non définie")}</p>
					<p class="mb-0"><strong>Niveau proposé :</strong> ${esc(niveau_label)}</p>
				</div>
				<button type="button" id="btn-mes-reinscriptions"
					class="btn btn-sm btn-outline-primary mt-3">
					Consulter mes réinscriptions
				</button>
			</div>`;

		$('input[data-fieldname="student"]').closest(".frappe-control").after(info_html);
		$("#btn-mes-reinscriptions").on("click", () => loadReinscriptions(info.matricule));
	}

	function removeStudentInfo() {
		$("#student-info-card").remove();
	}

	function loadReinscriptions(matricule) {
		removeReinscriptions();
		$(`<div id="reinscriptions-loading" class="text-center text-muted" style="margin:10px 0;">
			Chargement des réinscriptions…</div>`).insertAfter("#student-info-card");

		frappe.call({
			method: "udshed.udshed.web_form.reinscription_etudiant.reinscription_etudiant.mes_reinscriptions",
			args: { matricule },
			callback: (r) => {
				$("#reinscriptions-loading").remove();
				renderReinscriptions(r.message || []);
			},
			error: () => {
				$("#reinscriptions-loading").remove();
			}
		});
	}

	function renderReinscriptions(liste) {
		removeReinscriptions();

		let html = `
			<div id="reinscriptions-card" class="alert alert-light border" style="margin: 10px 0 15px;">
				<h5 class="mb-3">Mes réinscriptions</h5>`;

		if (!liste.length) {
			html += `<p class="text-muted mb-0">Aucune réinscription trouvée pour ce matricule.</p>`;
		} else {
			html += `<div class="list-group">`;
			liste.forEach((r) => {
				const bouton = r.fiche_disponible
					? `<button type="button" class="btn btn-sm btn-success btn-telecharger-fiche"
							data-matricule="${esc(r.matricule)}" data-name="${esc(r.name)}">
							Télécharger la fiche</button>`
					: (r.fiche_telechargee
						? `<span class="badge badge-secondary">Fiche téléchargée</span>`
						: "");
				html += `
					<div class="list-group-item">
						<div class="d-flex justify-content-between align-items-center">
							<div>
								<strong>${esc(r.academic_year)}</strong> — ${esc(r.niveau)} (${esc(r.semestre)})<br>
								<small class="text-muted">${esc(r.name)} · ${esc(fmtDate(r.creation))}</small>
							</div>
							<div class="text-right">
								${badgeStatut(r.statut)}
								<button type="button" class="btn btn-sm btn-outline-secondary btn-historique"
									data-matricule="${esc(r.matricule)}" data-name="${esc(r.name)}">
									Voir l'historique</button>
								${bouton}
							</div>
						</div>
						<div class="historique-body" id="historique-${esc(r.name)}" style="display:none; margin-top:10px;"></div>
					</div>`;
			});
			html += `</div>`;
		}
		html += `</div>`;

		$("#student-info-card").after(html);

		$(".btn-historique").on("click", (e) => {
			const el = $(e.currentTarget);
			const matricule = el.data("matricule");
			const name = el.data("name");
			const body = $(`#historique-${CSS.escape(name)}`);

			if (body.is(":visible")) {
				body.slideUp();
				el.text("Voir l'historique");
				return;
			}

			frappe.call({
				method: "udshed.udshed.web_form.reinscription_etudiant.reinscription_etudiant.detail_reinscription",
				args: { matricule, reinscription: name },
				callback: (r) => {
					if (!r.message) return;
					body.html(historiqueHtml(r.message)).slideDown();
					el.text("Masquer l'historique");
				}
			});
		});

		$(".btn-telecharger-fiche").on("click", (e) => {
			const el = $(e.currentTarget);
			downloadFiche(el.data("matricule"), el.data("name"));
		});
	}

	function historiqueHtml(d) {
		let html = `<p class="text-muted mb-2">Réf. : ${esc(d.name)} · Filière : ${esc(d.filiere)} · Niveau précédent : ${esc(d.niveau_precedent || "—")}</p>`;

		html += `<h6>Résultats de l'année précédente (${esc(d.niveau_precedent || "—")})</h6>`;
		if (d.resultats_precedents && d.resultats_precedents.length) {
			html += `<table class="table table-sm table-bordered mb-3">
				<thead><tr><th>Matière</th><th>Semestre</th><th>Note</th><th>Résultat</th></tr></thead><tbody>`;
			d.resultats_precedents.forEach((r) => {
				const badge = r.valide ? "badge-success" : "badge-danger";
				const label = r.valide ? "Validé" : "Dette";
				html += `<tr>
					<td>${esc(r.intitule)}</td><td>${esc(r.semestre)}</td><td>${esc(r.note)}/20</td>
					<td><span class="badge ${badge}">${label}</span></td></tr>`;
			});
			html += `</tbody></table>`;
		} else {
			html += `<p class="text-muted">Aucun résultat enregistré (notes non publiées ou niveau précédent inconnu).</p>`;
		}

		html += `<h6>Matières inscrites (${d.cours_inscrits ? d.cours_inscrits.length : 0})</h6>`;
		if (d.cours_inscrits && d.cours_inscrits.length) {
			html += `<table class="table table-sm table-bordered mb-3">
				<thead><tr><th>Matière</th><th>Semestre</th><th>Statut</th><th>À inscrire</th><th>Motif</th></tr></thead><tbody>`;
			d.cours_inscrits.forEach((c) => {
				html += `<tr>
					<td>${esc(c.intitule)}</td><td>${esc(c.semestre)}</td><td>${esc(c.statut)}</td>
					<td>${c.inscrire ? "Oui" : "Non"}</td><td>${esc(c.motif)}</td></tr>`;
			});
			html += `</tbody></table>`;
		} else {
			html += `<p class="text-muted">Aucune matière inscrite.</p>`;
		}

		return html;
	}

	function removeReinscriptions() {
		$("#reinscriptions-card").remove();
	}

	function badgeStatut(statut) {
		return `<span class="badge badge-success">${statut || "Validée"}</span>`;
	}

	function fmtDate(date_str) {
		if (!date_str) return "";
		const d = new Date(date_str);
		return d.toLocaleDateString("fr-FR");
	}

	function downloadFiche(matricule, name) {
		const params = $.param({ matricule, reinscription: name });
		const url = window.location.origin
			+ "/api/method/udshed.udshed.web_form.reinscription_etudiant.reinscription_etudiant.telecharger_fiche_reinscription?"
			+ params;
		window.open(url, "_blank");
	}
});
