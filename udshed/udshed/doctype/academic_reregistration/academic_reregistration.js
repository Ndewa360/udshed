frappe.ui.form.on("Academic Reregistration", {

	// =============================================
	// REFRESH
	// =============================================
	refresh(frm) {
		if (!frm.is_new()) {
			frm.set_intro("Réinscription validée — fiche disponible au téléchargement", "green");
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
			// Identité
			let nom_complet = ((student.nom || "") + " " + (student.prenom || "")).trim();
			frm.set_value("nom_prenom", nom_complet);
			frm.set_value("email", student.email || "");
			frm.set_value("date_naissance", student.birth_date || "");
			frm.set_value("lieu_naissance", student.birth_place || "");
			frm.set_value("telephone", student.phone || "");

			// Inscription
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

		// Niveau précédent calculé côté serveur (même règle que le backend)
		frappe.call({
			method: "udshed.api.reregistration.get_niveau_precedent",
			args: { filiere: frm.doc.filiere, niveau: frm.doc.niveau },
			callback(r) {
				frm.set_value("niveau_precedent", r.message || "");
				charger_matieres_precedentes(frm);
			}
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
// Charger les matières précédentes depuis le module de notes
// =============================================
function charger_matieres_precedentes(frm) {
	if (!frm.doc.filiere || !frm.doc.niveau_precedent || !frm.doc.student) return;

	frappe.call({
		method: "udshed.api.reregistration.get_student_notes",
		args: {
			student: frm.doc.student,
			filiere: frm.doc.filiere,
			niveau_precedent_label: frm.doc.niveau_precedent
		},
		callback(r) {
			frm.clear_table("resultats_precedents");

			(r.message || []).forEach(n => {
				let valide = n.statut === "Validé" ? 1 : 0;
				let row = frm.add_child("resultats_precedents");
				row.teaching_unit = n.teaching_unit;
				row.intitule = n.ue_name || n.teaching_unit;
				row.semestre = n.semestre || "";
				row.note = n.note_finale || 0;
				row.valide = valide;
				row.est_dette = valide ? 0 : 1;
			});

			frm.refresh_field("resultats_precedents");
			frappe.show_alert({
				message: `${(r.message || []).length} résultat(s) chargé(s) depuis le module de notes`,
				indicator: "blue"
			}, 3);
		}
	});
}
