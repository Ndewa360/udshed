frappe.pages['reinscription_etudiant'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Réinscription Étudiant',
		single_column: true
	});

	var student_matricule = null;
	var selected_session = null;
	var selected_semestre = null;
	var reregistration_name = null;
	var student_data = null;

	// Get student matricule for current user
	frappe.call({
		method: 'udshed.api.reregistration.get_student_by_matricule',
		callback: function(r) {
			if (r.message) {
				student_data = r.message;
				student_matricule = r.message.name;
				render_student_info(r.message);
				load_sessions();
			} else {
				page.set_primary_action(__('Aucun étudiant lié'), function() {}, 'user');
				frappe.msgprint(__('Aucun étudiant n\'est lié à votre compte utilisateur.'));
			}
		}
	});

	function render_student_info(s) {
		page.add_field({
			fieldtype: 'Section Break',
			label: 'Votre identité'
		});
		page.add_field({
			fieldtype: 'Data', label: 'Nom complet',
			fieldname: 'disp_nom', read_only: 1, default: s.nom_complet
		});
		page.add_field({
			fieldtype: 'Data', label: 'Matricule',
			fieldname: 'disp_matricule', read_only: 1, default: s.matricule
		});
		page.add_field({
			fieldtype: 'Data', label: 'Email',
			fieldname: 'disp_email', read_only: 1, default: s.email
		});
		page.add_field({
			fieldtype: 'Data', label: 'Date de naissance',
			fieldname: 'disp_naissance', read_only: 1, default: s.date_naissance || '—'
		});
		page.add_field({
			fieldtype: 'Data', label: 'Lieu de naissance',
			fieldname: 'disp_lieu', read_only: 1, default: s.lieu_naissance || '—'
		});
		page.add_field({
			fieldtype: 'Data', label: 'Téléphone',
			fieldname: 'disp_tel', read_only: 1, default: s.telephone || '—'
		});
		page.add_field({
			fieldtype: 'Data', label: 'Filière',
			fieldname: 'disp_filiere', read_only: 1, default: s.filiere
		});
		page.add_field({
			fieldtype: 'Data', label: 'Niveau actuel',
			fieldname: 'disp_niveau', read_only: 1, default: s.niveau_actuel
		});
		page.add_field({
			fieldtype: 'Column Break'
		});

		if (s.nom_prenom_pere || s.nom_prenom_mere) {
			page.add_field({
				fieldtype: 'Section Break',
				label: 'Famille'
			});
			if (s.nom_prenom_pere) {
				page.add_field({
					fieldtype: 'Data', label: 'Père',
					fieldname: 'disp_pere', read_only: 1, default: s.nom_prenom_pere
				});
				page.add_field({
					fieldtype: 'Data', label: 'Tél. père',
					fieldname: 'disp_tel_pere', read_only: 1, default: s.pere_telephone || '—'
				});
			}
			if (s.nom_prenom_mere) {
				page.add_field({
					fieldtype: 'Data', label: 'Mère',
					fieldname: 'disp_mere', read_only: 1, default: s.nom_prenom_mere
				});
				page.add_field({
					fieldtype: 'Data', label: 'Tél. mère',
					fieldname: 'disp_tel_mere', read_only: 1, default: s.telephone_mere || '—'
				});
			}
			if (s.nom_prenom_sponsor) {
				page.add_field({
					fieldtype: 'Data', label: 'Sponsor',
					fieldname: 'disp_sponsor', read_only: 1, default: s.nom_prenom_sponsor
				});
				page.add_field({
					fieldtype: 'Data', label: 'Tél. sponsor',
					fieldname: 'disp_tel_sponsor', read_only: 1, default: s.telephone_sponsor || '—'
				});
			}
		}

		if (s.dernier_etablissement || s.diplome_entree) {
			page.add_field({
				fieldtype: 'Section Break',
				label: 'Études antérieures'
			});
			page.add_field({
				fieldtype: 'Data', label: 'Dernier établissement',
				fieldname: 'disp_etab', read_only: 1, default: s.dernier_etablissement || '—'
			});
			page.add_field({
				fieldtype: 'Data', label: 'Diplôme d\'entrée',
				fieldname: 'disp_diplome', read_only: 1, default: s.diplome_entree || '—'
			});
		}
	}

	function load_sessions() {
		frappe.call({
			method: 'udshed.api.reregistration.get_open_sessions',
			callback: function(r) {
				if (r.message && r.message.length > 0) {
					render_session_selector(r.message);
				} else {
					page.set_primary_action(__('Aucune session ouverte'), function() {}, 'calendar');
					frappe.msgprint(__('Aucune session de réinscription n\'est actuellement ouverte.'));
				}
			}
		});
	}

	function render_session_selector(sessions) {
		var session_field = page.add_field({
			fieldtype: 'Select',
			label: 'Session de réinscription',
			fieldname: 'reinscription_session',
			options: sessions.map(function(s) { return s.name; }).join('\n'),
			change: function() {
				selected_session = this.get_value();
				render_semestre_selector();
			}
		});

		var semestre_field = page.add_field({
			fieldtype: 'Select',
			label: 'Semestre',
			fieldname: 'semestre',
			options: [
				{value: 'Semestre 1', label: 'Semestre 1'},
				{value: 'Semestre 2', label: 'Semestre 2'},
				{value: 'Les deux', label: 'Les deux'}
			],
			change: function() {
				selected_semestre = this.get_value();
			}
		});

		page.set_primary_action(__('Valider la réinscription'), function() {
			if (!selected_session) {
				frappe.msgprint(__('Veuillez sélectionner une session.'));
				return;
			}
			if (!selected_semestre) {
				frappe.msgprint(__('Veuillez sélectionner un semestre.'));
				return;
			}
			submit_reinscription();
		}, 'check');
	}

	function render_semestre_selector() {
		// Semestre field already added, just ensure it's visible
	}

	function submit_reinscription() {
		frappe.call({
			method: 'udshed.api.reregistration.submit_reinscription',
			args: {
				matricule: student_matricule,
				reinscription_session: selected_session,
				semestre: selected_semestre
			},
			callback: function(r) {
				if (r.message && r.message.status) {
					reregistration_name = r.message.name;
					frappe.show_alert({message: __('Réinscription soumise avec succès !'), indicator: 'green'});
					render_download_button();
				} else {
					frappe.msgprint(__('Erreur: ') + (r.message ? r.message.message : 'Inconnue'));
				}
			},
			error: function(r) {
				frappe.msgprint(__('Erreur lors de la soumission: ') + (r.message || ''));
			}
		});
	}

	function render_download_button() {
		// Clear existing fields and actions
		page.clear_actions();
		page.clear_fields();

		frappe.call({
			method: 'udshed.api.reregistration.get_reregistration_summary',
			args: {
				student: student_matricule,
				academic_year: frappe.db.get_value('Session Reinscription', selected_session, 'academic_year')
			},
			callback: function(r) {
				if (r.message) {
					var summary = r.message;
					page.add_field({
						fieldtype: 'Data',
						label: 'Session',
						fieldname: 'reinscription_session_display',
						read_only: 1,
						default: selected_session
					});
					page.add_field({
						fieldtype: 'Data',
						label: 'Année académique',
						fieldname: 'academic_year_display',
						read_only: 1,
						default: summary.academic_year
					});
					page.add_field({
						fieldtype: 'Data',
						label: 'Niveau',
						fieldname: 'niveau_display',
						read_only: 1,
						default: summary.niveau
					});
					page.add_field({
						fieldtype: 'Data',
						label: 'Filière',
						fieldname: 'filiere_display',
						read_only: 1,
						default: summary.filiere
					});
					page.add_field({
						fieldtype: 'Data',
						label: 'Semestre',
						fieldname: 'semestre_display',
						read_only: 1,
						default: summary.semestre
					});
					page.add_field({
						fieldtype: 'Data',
						label: 'Statut',
						fieldname: 'statut_display',
						read_only: 1,
						default: summary.statut
					});

					page.set_primary_action(__('Télécharger la fiche de réinscription'), function() {
						download_fiche();
					}, 'download');
				}
			}
		});
	}

	function download_fiche() {
		if (!reregistration_name) {
			frappe.msgprint(__('Aucune réinscription trouvée.'));
			return;
		}
		frappe.call({
			method: 'udshed.api.reregistration.telecharger_fiche_reinscription',
			args: { reregistration_name: reregistration_name },
			callback: function(r) {
				// The API sets frappe.local.response for file download
				if (r.message) {
					// Handle response if needed
				}
			}
		});
	}
}