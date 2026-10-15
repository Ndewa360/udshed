window.Udshed = window.Udshed || {};
window.Udshed.Insight = window.Udshed.Insight || {};
window.Udshed.Insight.Academic = window.Udshed.Insight.Academic || {};
window.Udshed.Insight.Academic.Teacher = {
    showAcademicTeacherInsights(page,filters,page_section,data) {
        const overview = data.global;
        const container = page_section.container
        const levels = data.niveau_filiere.map((f)=>f.filiere.field_of_study_level).reduce((arr,curr)=>[...arr,...curr],[])
        let html = `
            <!-- KPIs -->
            <div class="row mb-4">
                <div class="col-md-3">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#007bff",
                        iconColor:"#007bff",
                        icon:"fa fa-calendar-check-o",
                        label:"Total Sessions",
                        value:`${overview.sessions}`
                    })}
                </div>
                <div class="col-md-3">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#28a745",
                        iconColor:"#28a745",
                        icon:"fa fa-check-circle",
                        label:"Taux complétion",
                        value:`${overview.completion}%`
                    })}
                </div>
                <div class="col-md-3">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#17a2b8",
                        iconColor:"#17a2b8",
                        icon:"fa fa-clock-o",
                        label:"Heures effectuées",
                        value:`${overview.done_hours} h`,
                        comment: `/${overview.total_hours} h`
                    })}
                </div>
                <div class="col-md-3">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#ffc107",
                        iconColor:"#ffc107",
                        icon:"fa fa-graduation-cap",
                        label:"Cours",
                        value:`${data.teaching_unit.length}`
                    })}
                </div>
            </div>
            

            <!-- Graphiques -->
            <div class="row mb-4">
                <div class="col-md-12">
                    <!-- Résumé par faculté -->
                    <div class="frappe-card p-3 mb-4">
                        <h5 class="mb-3">Résumé par classe</h5>
                        <div class="row">`                    
                            data.niveau_filiere.forEach(f => {
                                html += `
                                    <div class="col-md-4 mb-3">
                                        <div class="program-card" onclick="navigateToFaculty('${f.filiere.code}')">
                                            <div class="d-flex justify-content-between align-items-center mb-2">
                                                <h6 class="mb-0">${f.filiere.name} ${f.filiere.field_of_study_level.find((l)=>l.name==f.niveau).level}</h6>
                                                <span class="badge badge-${f.completion_color}">${f.completion}%</span>
                                            </div>
                                            <div class="small text-muted mb-2 d-flex justify-content-between">
                                                <span><i class="fa fa-book mr-1"></i> ${f.teaching_units.length} cours</span> 
                                                <span><i class="fa fa-clock-o mr-1"></i> ${f.sessions} sessions</span>
                                            </div>
                                            <div class="progress progress-sm">
                                                <div class="progress-bar bg-${f.completion_color}" style="width: ${f.completion}%"></div>
                                            </div>
                                            <div class="d-flex justify-content-between mt-2 small">
                                                <span>${f.done_hours} h effectuées</span>
                                                <span>/${f.total_hours} h</span>
                                            </div>
                                        </div>
                                    </div>
                                `;
                            });             
                    
                            html +=`
                        </div>
                    </div>
                </div>
            </div>
            <!-- Cours du niveau -->
            <div class="frappe-card p-3 mb-4">
                <h5 class="mb-3">Progression des cours</h5>
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>Cours</th>
                                <th>Classes</th>
                                <th>Sessions</th>
                                <th>Heures</th>
                                <th>Complétion</th>
                                <th>CM</th>
                                <th>TD</th>
                                <th>TP</th>
                                <th>CC</th>
                                <th>Examen</th>
                                <th>Rattrapage</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody> `;    

                        data.teaching_unit.forEach(c => {
                            html += `
                                <tr class="cursor-pointer">
                                    <td><strong>${c.teaching_unit.course}</strong><br><small>${c.teaching_unit.intitule_cours}</small></td>
                                    <td>${c.teaching_unit.course_levels.map((level)=>this.getStringFieldOfStudyAndLevel(level,levels)).join(', ')}</td>
                                    <td class="text-center">${c.sessions}</td>
                                    <td>${c.done_hours}h <small class="text-muted">/${c.total_hours}h</small></td>
                                    <td>
                                        <div class="d-flex align-items-center">
                                            <div class="progress flex-grow-1 me-2" style="height: 6px; width: 60px;">
                                                <div class="progress-bar bg-${c.completion_color}" style="width: ${c.completion}%"></div>
                                            </div>
                                            <small>${c.completion}%</small>
                                        </div>
                                    </td>
                                    <td class="text-center">${c.sessions_map["Cours Magistral (CM)"]}</td>
                                    <td class="text-center">${c.sessions_map["Traveaux Dirigés (TD)"]}</td>
                                    <td class="text-center">${c.sessions_map["Traveaux Pratiques (TP)"]}</td>
                                    <td class="text-center">${c.sessions_map["Controlle Continue (CC)"]}</td>
                                    <td class="text-center">${c.sessions_map["Examen de session normal"]}</td>
                                    <td class="text-center">${c.sessions_map["Examen de rattrapage"]}</td>
                                    <td> 
                                        <button onclick="Udshed.Insight.Academic.Teacher.downloadProgressionCours('${c.teaching_unit.name}','${filters.teacher}',${c.done_hours},${c.total_hours})" class="btn btn-secondary btn-sm primary-action" data-label="Fiche progression de cours">
                                            <svg class="icon  icon-xs" style="" aria-hidden="true"><use class="" href="#icon-download"></use></svg> 
                                            <span class="hidden-xs" data-label="Fiche progression"> Fiche de progression</span>
                                        </button>
                                    </td>
                                </tr>
                            `
                        });
                        html += `
                        </tbody>
                    </table>
                </div>
            </div>
            
        `;
        container.html(html);
        
        // Graphique des niveaux
        // Udshed.Insight.UI.initLevelChart(data.by_level);
    },
    getStringFieldOfStudyAndLevel(level,levels)
    {
        return `${level.filiere} ${levels.find((l)=>l.name == level.niveau).level}`
    },
    downloadProgressionCours(teachingUnitName,teacher,nbre_heure,total_heure)
    {
        frappe.call({
            method: "udshed.api.generate_teacher_doc.download_progression_cours",
            args: {
                teaching_unit:teachingUnitName,
                teacher,
                nbre_heure,
                total_heure
            },
            freeze: true,
            freeze_message: __("Génération de la fiche de progression..."),
            callback: function(r) {
                Udshed.Utils.make_download_file_word(r.message,"fiche_de_progression")
            },
            error: function(r) {
                frappe.msgprint(__("Erreur lors du Génération de la fiche de progression"));
            }
        })
    }
};