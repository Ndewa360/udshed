window.Udshed = window.Udshed || {};
window.Udshed.Insight = window.Udshed.Insight || {};
window.Udshed.Insight.Academic = window.Udshed.Insight.Academic || {};
window.Udshed.Insight.Academic.Faculty = {
    showAcademicFacultyInsights(page,filters,page_section,data) {
        const overview = data.global;
        const container = page_section.container
        let html = `
            <!-- KPIs -->
            <div class="row mb-4">
                <div class="col-md-4">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#007bff",
                        iconColor:"#007bff",
                        icon:"fa fa-calendar-check-o",
                        label:"Total Sessions",
                        value:`${overview.sessions}`
                    })}
                </div>
                <div class="col-md-4">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#28a745",
                        iconColor:"#28a745",
                        icon:"fa fa-clock-o",
                        label:"Taux complétion",
                        value:`${overview.completion}%`
                    })}
                </div>
                <div class="col-md-4">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#ffc107",
                        iconColor:"#ffc107",
                        icon:"fa fa-graduation-cap",
                        label:"Filières",
                        value:`${overview.programs_count}`
                    })}
                </div>
            </div>
            
            <!-- Programmes -->
            <div class="frappe-card p-3 mb-4">
                <h5 class="mb-3">Programmes de la faculté</h5>
                <div class="row">
        `;
    
        data.filiere.forEach(p => {
            html += `
                <div class="col-md-6 mb-3">
                    <div class="program-card" onclick="navigateToProgram('${p.filiere.name}')">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <h6 class="mb-0">${p.filiere.name_of_field}</h6>
                            <span class="badge badge-${p.completion_color}">${p.completion}%</span>
                        </div>
                        <div class="small text-muted mb-2">
                            <i class="fa fa-layer-group mr-1"></i> Niveaux: ${p.filiere.field_of_study_level.map((f)=>f.level).sort().join(', ')} · 
                        </div>
                        <div class="progress progress-sm mb-2">
                            <div class="progress-bar bg-${p.completion_color}" style="width: ${p.completion}%"></div>
                        </div>
                        <div class="d-flex justify-content-between small">
                            <span>${p.done_hours}h effectuées</span>
                            <span class="text-muted">${p.sessions} sessions</span>
                        </div>
                    </div>
                </div>
            `;
        });
    
        html += `
                </div>
            </div>
        `;
    
        container.html(html);
        
        // Graphique des niveaux
        // Udshed.Insight.UI.initLevelChart(data.by_level);
    }
};