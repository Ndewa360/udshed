window.Udshed = window.Udshed || {};
window.Udshed.Insight = window.Udshed.Insight || {};
window.Udshed.Insight.Finance = window.Udshed.Insight.Finance || {};
window.Udshed.Insight.Finance.Teacher = {
    showFinanceTeacherInsights(page,filters,page_section,data) {
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
                        icon:"fa fa-money",
                        label:"Montant",
                        value: Udshed.Utils.formatCurrency(overview.consume_price,overview.default_currency)
                    })}
                </div>
                <div class="col-md-3">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#28a745",
                        iconColor:"#28a745",
                        icon:"fa fa-check-circle",
                        label:"Taux complétion",
                        value:`${overview.completion_finance}%`
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
                                <div class="program-card" onclick="navigateToFaculty('${f.filiere.name}')">
                                    <div class="d-flex justify-content-between align-items-center mb-2">
                                        <h6 class="mb-0">${f.filiere.name} ${f.filiere.field_of_study_level.find((l)=>l.name==f.niveau).level}</h6>
                                    </div>
                                    <div class="row g-2 mb-2">
                                        <div class="col-6">
                                            <div class="small text-muted">Heures</div>
                                            <div class="font-weight-bold">${f.done_hours} h</div>
                                        </div>
                                        <div class="col-6">
                                            <div class="small text-muted">Montant</div>
                                            <div class="font-weight-bold amount-positive">${Udshed.Utils.formatCurrency(f.consume_price,overview.default_currency)} </div>
                                        </div>
                                    </div>
                                    <div class="progress progress-sm">
                                        <div class="progress-bar bg-primary" style="width: ${f.completion_finance}%"></div>
                                    </div>
                                    <div class="small text-muted mt-1">${f.sessions} sessions ·</div>
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
                                <th>A payer</th>
                            </tr>
                        </thead>
                        <tbody> `;    

                        data.teaching_unit.forEach(c => {
                            html += `
                                <tr class="cursor-pointer" onclick="navigateToCourse('${c.teaching_unit.name}')">
                                    <td><strong>${c.teaching_unit.course}</strong><br><small>${c.teaching_unit.intitule_cours}</small></td>
                                    <td>${c.teaching_unit.course_levels.map((level)=>this.getStringFieldOfStudyAndLevel(level,levels)).join(', ')}</td>
                                    <td class="text-center">${c.sessions}</td>
                                    <td>${c.done_hours}h <small class="text-muted">/${c.total_hours}h</small></td>
                                    <td class="currency-cell amount-positive">${Udshed.Utils.formatCurrency(c.consume_price,overview.default_currency)}</td>
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
    }
};