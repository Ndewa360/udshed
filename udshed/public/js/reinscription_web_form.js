// Web Form: Réinscription Étudiant
// Gère les étapes 2-5 du workflow de réinscription

frappe.ready(function() {
    const form = frappe.web_form;
    let studentVerified = false;
    let studentData = null;
    let gradesData = null;

    // Initialisation
    $(document).ready(function() {
        setupForm();
    });

    function setupForm() {
        // Cacher les champs avancés au départ
        hideAdvancedFields();

        // Événement sur le champ matricule
        $('input[data-fieldname="student"]').on('blur', function() {
            const matricule = $(this).val();
            if (matricule) {
                verifyStudent(matricule);
            }
        });

        // Événement sur le champ année académique
        $('input[data-fieldname="academic_year"]').on('change', function() {
            if (studentData) {
                checkExistingReregistration();
            }
        });
    }

    function hideAdvancedFields() {
        $('[data-fieldname="fliere"]').closest('.frappe-control').hide();
        $('[data-fieldname="niveau"]').closest('.frappe-control').hide();
        $('[data-fieldname="semestre"]').closest('.frappe-control').hide();
    }

    function showAdvancedFields() {
        $('[data-fieldname="fliere"]').closest('.frappe-control').show();
        $('[data-fieldname="niveau"]').closest('.frappe-control').show();
        $('[data-fieldname="semestre"]').closest('.frappe-control').show();
    }

    function verifyStudent(matricule) {
        frappe.call({
            method: 'udshed.api.reregistration_web.verify_student',
            args: { matricule: matricule },
            callback: function(r) {
                if (r.message && r.message.exists) {
                    studentData = r.message;
                    studentVerified = true;
                    prefillForm(studentData);
                    showAdvancedFields();
                    showStudentInfo(studentData);
                } else {
                    frappe.msgprint('Étudiant non trouvé. Vérifiez votre matricule.');
                }
            },
            error: function(r) {
                frappe.msgprint('Erreur lors de la vérification du matricule.');
            }
        });
    }

    function prefillForm(data) {
        // Pré-remplir les champs
        if (data.filiere) {
            $('input[data-fieldname="filiere"]').val(data.filiere).trigger('change');
        }
        if (data.niveau) {
            $('input[data-fieldname="niveau"]').val(data.niveau).trigger('change');
        }
        if (data.semestre) {
            $('select[data-fieldname="semestre"]').val(data.semestre).trigger('change');
        }
    }

    function showStudentInfo(data) {
        // Afficher les informations de l'étudiant
        const infoHtml = `
            <div class="student-info-card" style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <h5>Informations de l'étudiant</h5>
                <p><strong>Nom:</strong> ${data.student_name}</p>
                <p><strong>Matricule:</strong> ${data.matricule}</p>
                <p><strong>Email:</strong> ${data.email}</p>
                <p><strong>Filière:</strong> ${data.filiere || 'Non définie'}</p>
                <p><strong>Niveau:</strong> ${data.niveau || 'Non défini'}</p>
            </div>
        `;

        // Insérer après le champ matricule
        $('input[data-fieldname="student"]').closest('.frappe-control').after(infoHtml);
    }

    function checkExistingReregistration() {
        if (!studentData || !$('input[data-fieldname="academic_year"]').val()) return;

        frappe.call({
            method: 'udshed.api.reregistration_web.get_reregistration_status',
            args: {
                matricule: studentData.matricule,
                academic_year: $('input[data-fieldname="academic_year"]').val()
            },
            callback: function(r) {
                if (r.message && r.message.has_reregistration) {
                    const reg = r.message.reregistration;
                    frappe.msgprint({
                        title: 'Réinscription existante',
                        indicator: 'orange',
                        message: `Vous avez déjà une réinscription (${reg.name}) avec le statut: ${reg.statut}`
                    });
                }
            }
        });
    }

    // Fonction pour afficher les notes et dettes
    function showGradesAndDebts(matricule, academicYear, filiere, niveau) {
        frappe.call({
            method: 'udshed.api.reregistration_web.get_student_grades_and_debts',
            args: {
                matricule: matricule,
                academic_year: academicYear,
                filiere: filiere,
                niveau: niveau
            },
            callback: function(r) {
                if (r.message) {
                    gradesData = r.message;
                    displayGrades(gradesData);
                }
            }
        });
    }

    function displayGrades(data) {
        let html = '<div class="grades-section" style="margin: 20px 0;">';

        if (data.total_dettes > 0) {
            html += `
                <div class="alert alert-warning">
                    <strong>Attention!</strong> Vous avez ${data.total_dettes} matière(s) en dette académique.
                    Ces matières seront à reprendre.
                </div>
            `;
        }

        // Matières validées
        if (data.matieres_validees.length > 0) {
            html += '<h5>Matières validées</h5>';
            html += '<table class="table table-bordered"><thead><tr><th>Matière</th><th>Note</th><th>Semestre</th></tr></thead><tbody>';
            data.matieres_validees.forEach(function(m) {
                html += `<tr><td>${m.intitule}</td><td>${m.note}</td><td>${m.semestre}</td></tr>`;
            });
            html += '</tbody></table>';
        }

        // Matières en dette
        if (data.matieres_dettes.length > 0) {
            html += '<h5>Matières en dette (à reprendre)</h5>';
            html += '<table class="table table-bordered table-danger"><thead><tr><th>Matière</th><th>Note</th><th>Semestre</th></tr></thead><tbody>';
            data.matieres_dettes.forEach(function(m) {
                html += `<tr class="table-danger"><td>${m.intitule}</td><td>${m.note}</td><td>${m.semestre}</td></tr>`;
            });
            html += '</tbody></table>';
        }

        html += '</div>';

        // Insérer avant le bouton de soumission
        $('button[type="submit"]').before(html);
    }
