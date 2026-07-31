frappe.ready(function() {
    const form = frappe.web_form;
    let studentVerified = false;
    let studentData = null;
    let gradesData = null;
    let coursesData = [];
    let selectedCourses = new Set();
    let previousResults = [];

    $(document).ready(function() {
        setupForm();
    });

    function setupForm() {
        hideAdvancedFields();

        $('input[data-fieldname="student"]').on('blur', function() {
            const matricule = $(this).val();
            if (matricule) {
                verifyStudent(matricule);
            }
        });

        $('input[data-fieldname="academic_year"]').on('change', function() {
            if (studentData) {
                checkExistingReregistration();
                loadPreviousResults();
            }
        });

        $('select[data-fieldname="semestre"]').on('change', function() {
            if (studentData && $(this).val()) {
                loadCoursesForSemester();
            } else {
                $('#courses-section').remove();
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
        if (data.filiere) {
            $('input[data-fieldname="filiere"]').val(data.filiere).trigger('change');
        }
        let niveau_a_afficher = data.niveau_suivant || data.niveau;
        if (niveau_a_afficher) {
            $('input[data-fieldname="niveau"]').val(niveau_a_afficher).trigger('change');
        }
        if (data.semestre) {
            $('select[data-fieldname="semestre"]').val(data.semestre).trigger('change');
        }
    }

    function showStudentInfo(data) {
        $('#student-info-card').remove();
        const infoHtml = `
            <div id="student-info-card" style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <h5>Informations de l'étudiant</h5>
                <p><strong>Nom:</strong> ${data.student_name}</p>
                <p><strong>Matricule:</strong> ${data.matricule}</p>
                <p><strong>Email:</strong> ${data.email}</p>
                <p><strong>Filière:</strong> ${data.filiere || 'Non définie'}</p>
                <p><strong>Niveau actuel:</strong> ${data.niveau || 'Non défini'}</p>
                ${data.niveau_suivant ? `<p><strong>Niveau suivant suggéré:</strong> <span class="text-primary">${data.niveau_suivant}</span></p>` : ''}
            </div>
        `;
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

    function loadPreviousResults() {
        const filiere = $('input[data-fieldname="filiere"]').val();
        const niveau = $('input[data-fieldname="niveau"]').val();
        const academic_year = $('input[data-fieldname="academic_year"]').val();
        if (!studentData || !filiere || !niveau || !academic_year) return;

        frappe.call({
            method: 'udshed.api.reregistration_web.get_student_grades_and_debts',
            args: {
                matricule: studentData.matricule,
                academic_year: academic_year,
                filiere: filiere,
                niveau: niveau,
                semestre: null
            },
            callback: function(r) {
                if (r.message) {
                    gradesData = r.message;
                    displayPreviousResults(gradesData);
                }
            }
        });
    }

    function displayPreviousResults(data) {
        $('#previous-results-section').remove();

        let total = (data.matieres_validees || []).length + (data.matieres_dettes || []).length;
        if (total === 0) return;

        let validees = data.matieres_validees || [];
        let dettes = data.matieres_dettes || [];
        let validees_count = validees.length;
        let dettes_count = dettes.length;

        let rows = '';
        validees.forEach(function(m) {
            rows += `<tr class="table-success">
                <td><span class="badge badge-success">Validée</span></td>
                <td>${m.intitule || m.teaching_unit}</td>
                <td>${m.semestre || '—'}</td>
                <td>${m.note || 0}/20</td>
            </tr>`;
        });
        dettes.forEach(function(m) {
            let note = m.note || 0;
            let badge = note === 0 ? 'badge-warning' : 'badge-danger';
            let label = note === 0 ? 'Non évalué' : 'Dette';
            rows += `<tr class="${note === 0 ? 'table-warning' : 'table-danger'}">
                <td><span class="badge ${badge}">${label}</span></td>
                <td>${m.intitule || m.teaching_unit}</td>
                <td>${m.semestre || '—'}</td>
                <td>${note}/20</td>
            </tr>`;
        });

        let html = `
            <div id="previous-results-section" style="margin: 20px 0;">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="mb-0">Résultats de l'année précédente</h5>
                        <div>
                            <span class="badge badge-success mr-1">${validees_count} validée(s)</span>
                            <span class="badge badge-danger">${dettes_count} dette(s)</span>
                        </div>
                    </div>
                    <div class="card-body p-0">
                        <table class="table table-hover mb-0">
                            <thead class="thead-light">
                                <tr>
                                    <th style="width: 100px;">Statut</th>
                                    <th>Matière</th>
                                    <th style="width: 100px;">Semestre</th>
                                    <th style="width: 100px;">Note</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${rows || '<tr><td colspan="4" class="text-center text-muted">Aucun résultat trouvé</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>`;

        $('select[data-fieldname="semestre"]').closest('.frappe-control').after(html);
    }

    function loadCoursesForSemester() {
        const filiere = $('input[data-fieldname="filiere"]').val();
        const niveau = $('input[data-fieldname="niveau"]').val();
        const academic_year = $('input[data-fieldname="academic_year"]').val();
        const semestre = $('select[data-fieldname="semestre"]').val();

        if (!filiere || !niveau || !academic_year || !semestre) return;

        frappe.call({
            method: 'udshed.api.reregistration_web.get_courses_for_semester',
            args: {
                filiere: filiere,
                niveau_label: niveau,
                academic_year: academic_year,
                semestre: semestre
            },
            callback: function(r) {
                coursesData = r.message || [];
                selectedCourses = new Set(coursesData.map(c => c.name));
                displayCourses(coursesData);
            }
        });
    }

    function displayCourses(courses) {
        $('#courses-section').remove();
        if (!courses.length) {
            $('button[type="submit"]').before(`
                <div id="courses-section" class="alert alert-warning" style="margin: 20px 0;">
                    Aucune matière trouvée pour ce semestre. Veuillez contacter l'administration.
                </div>`);
            return;
        }

        let rows = courses.map(function(c) {
            let dettes = gradesData ? (gradesData.matieres_dettes || []).filter(d => d.teaching_unit === c.name) : [];
            let validees = gradesData ? (gradesData.matieres_validees || []).filter(d => d.teaching_unit === c.name) : [];
            let is_debt = dettes.length > 0;
            let is_validated = validees.length > 0;

            let rowClass = is_debt ? 'table-danger' : (is_validated ? 'table-success' : '');
            let badge = is_debt ? '<span class="badge badge-danger">Reporté</span>'
                : (is_validated ? '<span class="badge badge-success">Dispensé</span>'
                    : '<span class="badge badge-info">Inscrit</span>');
            let note = is_debt ? dettes[0].note : (is_validated ? validees[0].note : '—');

            let disabled = is_validated ? 'disabled' : '';
            let checked = !is_validated ? 'checked' : '';

            return `<tr class="${rowClass}">
                <td>
                    <input type="checkbox" class="course-checkbox"
                        data-course="${c.name}" value="${c.name}"
                        ${checked} ${disabled}>
                </td>
                <td>${c.intitule_cours || c.name}</td>
                <td>${badge}</td>
                <td>${c.semestre || '—'}</td>
                <td>${note}</td>
            </tr>`;
        }).join('');

        let semesterLabel = $('select[data-fieldname="semestre"]').val();
        let html = `
            <div id="courses-section" style="margin: 20px 0;">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <div>
                            <h5 class="mb-0">Matières à inscrire</h5>
                            <small class="text-muted">
                                Choisissez les matières auxquelles vous inscrire pour ${semesterLabel}
                                <br>
                                <span class="badge badge-info">Inscrit</span> Nouvelle matière
                                <span class="badge badge-success">Dispensé</span> Déjà validé
                                <span class="badge badge-danger">Reporté</span> Échec, à reprendre
                            </small>
                        </div>
                    </div>
                    <div class="card-body p-0">
                        <table class="table table-hover mb-0">
                            <thead class="thead-light">
                                <tr>
                                    <th style="width: 40px;">
                                        <input type="checkbox" id="select-all-courses" checked>
                                    </th>
                                    <th>Matière</th>
                                    <th style="width: 100px;">Statut</th>
                                    <th style="width: 100px;">Semestre</th>
                                    <th style="width: 80px;">Note ant.</th>
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>
                    </div>
                    <div class="card-footer d-flex justify-content-between">
                        <span class="text-muted">
                            <span id="selected-count">${courses.length}</span> / ${courses.length} matière(s) sélectionnée(s)
                        </span>
                        <span class="text-muted">
                            ${(gradesData ? (gradesData.matieres_dettes || []).length : 0)} dette(s) à reprendre
                        </span>
                    </div>
                </div>
            </div>`;

        $('button[type="submit"]').before(html);

        $('#select-all-courses').on('change', function() {
            const checked = $(this).prop('checked');
            $('.course-checkbox:not(:disabled)').prop('checked', checked).trigger('change');
        });

        $('.course-checkbox').on('change', function() {
            const courseName = $(this).data('course');
            if ($(this).prop('checked')) {
                selectedCourses.add(courseName);
            } else {
                selectedCourses.delete(courseName);
            }
            $('#selected-count').text(selectedCourses.size);
            let total = courses.length;
            $('#select-all-courses').prop('checked',
                selectedCourses.size === total);
        });
    }

    const originalSubmit = form.submit;
    form.submit = function() {
        const semestre = $('select[data-fieldname="semestre"]').val();
        if (!semestre) {
            frappe.msgprint('Veuillez sélectionner un semestre.');
            return false;
        }

        const filiere = $('input[data-fieldname="filiere"]').val();
        const niveau = $('input[data-fieldname="niveau"]').val();
        const academicYear = $('input[data-fieldname="academic_year"]').val();

        if (!semestre || coursesData.length === 0) {
            return originalSubmit.apply(form, arguments);
        }

        const selected = Array.from(selectedCourses);
        if (selected.length === 0) {
            frappe.msgprint('Veuillez sélectionner au moins une matière.');
            return false;
        }

        const docData = {
            student: studentData.matricule,
            academic_year: academicYear,
            reinscription_session: form.get_value('reinscription_session'),
            filiere: filiere,
            niveau: niveau,
            semestre: semestre,
            statut: 'En attente'
        };

        frappe.call({
            method: 'udshed.api.reregistration_web.create_reregistration',
            args: {
                doc_data: docData,
                courses: selected
            },
            callback: function(r) {
                if (r.message && r.message.status) {
                    frappe.msgprint({
                        title: 'Succès',
                        indicator: 'green',
                        message: r.message.message
                    });
                    form.reset();
                }
            },
            error: function(r) {
                frappe.msgprint({
                    title: 'Erreur',
                    indicator: 'red',
                    message: r.message || 'Erreur lors de la création de la réinscription.'
                });
            }
        });

        return false;
    };
});
