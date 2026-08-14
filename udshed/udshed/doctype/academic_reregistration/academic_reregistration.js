frappe.ui.form.on("Academic Reregistration", {

	// =============================================
	// REFRESH
	// =============================================
	refresh(frm) {
		const isCoordinator = frappe.user.has_role("System Manager") || frappe.user.has_role("Coordonateur") || frappe.user.has_role("Agent de scolarité");

		if (!frm.is_new() && isCoordinator) {
			// Brouillon -> En attente
			if (frm.doc.statut === "Brouillon") {
				frm.add_custom_button("Soumettre", () => {
					frappe.confirm(
						"Soumettre cette réinscription pour validation ?",
						() => {
							frappe.call({
								method: "udshed.api.reregistration.soumettre_reregistration",
								args: { reregistration_name: frm.doc.name },
								callback(r) {
									frappe.show_alert({
										message: r.message.message,
										indicator: "blue"
									}, 5);
									frm.reload_doc();
								}
							});
						}
					);
				}, "Actions").addClass("btn-primary");
			}

			// En attente -> Validée / Refusée (ou retour en brouillon)
			if (frm.doc.statut === "En attente") {
				frm.add_custom_button("Valider la réinscription", () => {
					frappe.confirm(
						"Voulez-vous vraiment valider cette réinscription ?",
						() => {
							frappe.call({
								method: "udshed.api.reregistration.valider_reregistration",
								args: { reregistration_name: frm.doc.name },
								callback(r) {
									frappe.show_alert({
										message: r.message.message,
										indicator: "green"
									}, 5);
									frm.reload_doc();
								}
							});
						}
					);
				}, "Actions").addClass("btn-success");

				frm.add_custom_button("Refuser", () => {
					frappe.prompt(
						{ label: "Motif du refus", fieldname: "motif", fieldtype: "Small Text" },
						(values) => {
							frappe.call({
								method: "udshed.api.reregistration.refuser_reregistration",
								args: {
									reregistration_name: frm.doc.name,
									motif: values.motif
								},
								callback(r) {
									frappe.show_alert({
										message: r.message.message,
										indicator: "red"
									}, 5);
									frm.reload_doc();
								}
							});
						},
						"Refuser la réinscription"
					);
				}, "Actions").addClass("btn-danger");

				frm.add_custom_button("Rouvrir (brouillon)", () => {
					frappe.confirm(
						"Rouvrir cette réinscription en brouillon pour correction ?",
						() => {
							frappe.call({
								method: "udshed.api.reregistration.reouvrir_reregistration",
								args: { reregistration_name: frm.doc.name },
								callback(r) {
									frappe.show_alert({
										message: r.message.message,
										indicator: "orange"
									}, 5);
									frm.reload_doc();
								}
							});
						}
					);
				}, "Actions");
			}
		}

		// Afficher le statut en couleur
		if (frm.doc.statut === "Validée") {
			frm.set_intro("Réinscription validée", "green");
		} else if (frm.doc.statut === "Refusée") {
			frm.set_intro("Réinscription refusée", "red");
		} else if (frm.doc.statut === "En attente") {
			frm.set_intro("En attente de validation", "orange");
		} else if (frm.doc.statut === "Brouillon") {
			frm.set_intro("Brouillon - soumettez pour validation", "blue");
		}

		// Charger les niveaux si la filière est déjà définie
		if (frm.doc.filiere) {
			charger_niveaux(frm);
		}
	},

	// =============================================
	// ÉTUDIANT
	// =============================================
	student(frm) {
		if (!frm.doc.student) return;

		frappe.db.get_doc("Student", frm.doc.student).then(student => {
			if (student.filiere) {
				frm.set_value("filiere", student.filiere);
			}
		});
	},

	// =============================================
	// SESSION
	// =============================================
	reinscription_session(frm) {
		if (!frm.doc.reinscription_session) return;

		frappe.db.get_doc("Session Reinscription", frm.doc.reinscription_session).then(session => {
			frm.set_value("academic_year", session.academic_year);
		});
	},

	// =============================================
	// FILIÈRE
	// =============================================
	filiere(frm) {
		frm.set_value("niveau", "");
		frm.set_value("niveau_precedent", "");

		if (!frm.doc.filiere) return;

		charger_niveaux(frm);
	},

	// =============================================
	// NIVEAU
	// =============================================
	niveau(frm) {
		if (!frm.doc.niveau || !frm.doc.filiere) return;

		// Calculer le niveau précédent côté JS avant de charger
		calculer_niveau_precedent_js(frm, () => {
			charger_matieres_precedentes(frm);
		});
	},

	// =============================================
	// ANNÉE ACADÉMIQUE
	// =============================================
	academic_year(frm) {
		if (!frm.doc.academic_year || !frm.doc.niveau) return;
		charger_matieres_precedentes(frm);
	},

	// =============================================
	// SEMESTRE
	// =============================================
	semestre(frm) {
		if (!frm.doc.semestre || !frm.doc.niveau) return;
		charger_matieres_precedentes(frm);
	}
});


// =============================================
// Charger les niveaux d'une filière
// =============================================
function charger_niveaux(frm) {
	frappe.call({
		method: "udshed.api.reregistration.get_ordered_levels",
		args: { filiere: frm.doc.filiere },
		callback(r) {
			if (!r.message) return;
			let options = r.message.map(l => l.level);
			frm.set_df_property("niveau", "options", ["", ...options]);
			frm.refresh_field("niveau");
		}
	});
}


// =============================================
// Calculer le niveau précédent côté JS
// =============================================
function calculer_niveau_precedent_js(frm, callback) {
	if (!frm.doc.filiere || !frm.doc.niveau) {
		if (callback) callback();
		return;
	}

	frappe.call({
		method: "udshed.api.reregistration.get_ordered_levels",
		args: { filiere: frm.doc.filiere },
		callback(r) {
			if (!r.message) {
				if (callback) callback();
				return;
			}

			let levels = r.message;
			let niveau_actuel_order = null;

			for (let i = 0; i < levels.length; i++) {
				if (levels[i].level === frm.doc.niveau) {
					niveau_actuel_order = levels[i].order;
					break;
				}
			}

			if (niveau_actuel_order === null || niveau_actuel_order <= 1) {
				frm.set_value("niveau_precedent", "");
			} else {
				for (let i = 0; i < levels.length; i++) {
					if (levels[i].order === niveau_actuel_order - 1) {
						frm.set_value("niveau_precedent", levels[i].level);
						break;
					}
				}
			}

			if (callback) callback();
		}
	});
}


// =============================================
// Charger les matières du niveau précédent
// =============================================
function charger_matieres_precedentes(frm) {
	if (!frm.doc.filiere || !frm.doc.niveau || !frm.doc.academic_year) return;

	// Récupérer la note minimale depuis la session
	let note_minimale = 10;
	frappe.db.get_value("Session Reinscription", frm.doc.reinscription_session, "note_minimale").then(r => {
		if (r.message && r.message.note_minimale) {
			note_minimale = r.message.note_minimale;
		}

		// Etape 1 : charger les matières du niveau précédent
		frappe.call({
			method: "udshed.api.reregistration.get_previous_level_courses",
			args: {
				filiere: frm.doc.filiere,
				niveau_label: frm.doc.niveau,
				academic_year: frm.doc.academic_year
			},
			callback(r) {
				if (!r.message || r.message.length === 0) {
					frappe.show_alert({
						message: "Aucune matière trouvée pour le niveau précédent",
						indicator: "orange"
					}, 4);
					return;
				}

				// Etape 2 : charger les notes de l'étudiant
				frappe.call({
					method: "udshed.api.reregistration.get_student_notes",
					args: {
						student: frm.doc.student,
						filiere: frm.doc.filiere,
						niveau_precedent_label: frm.doc.niveau_precedent
					},
					callback(notes_r) {
						// Dictionnaire notes par teaching_unit
						let notes_dict = {};
						if (notes_r.message) {
							notes_r.message.forEach(n => {
								notes_dict[n.teaching_unit] = n.note_finale || 0;
							});
						}

						frm.clear_table("resultats_precedents");

						r.message.forEach(matiere => {
							let note = notes_dict[matiere.name] || 0;
							let valide = note >= note_minimale ? 1 : 0;
							let est_dette = note < note_minimale ? 1 : 0;

							let row = frm.add_child("resultats_precedents");
							row.teaching_unit = matiere.name;
							row.intitule = matiere.intitule_cours;
							row.semestre = matiere.semestre;
							row.note = note;
							row.valide = valide;
							row.est_dette = est_dette;
						});

						frm.refresh_field("resultats_precedents");
						frappe.show_alert({
							message: `${r.message.length} matière(s) chargée(s)`,
							indicator: "blue"
						}, 3);
					}
				});
			}
		});
	});
}
