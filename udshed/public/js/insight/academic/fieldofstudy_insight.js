window.Udshed = window.Udshed || {};
window.Udshed.Insight = window.Udshed.Insight || {};
window.Udshed.Insight.Academic = window.Udshed.Insight.Academic || {};
window.Udshed.Insight.Academic.FieldOfStudy = {
    showAcademicFieldOfStudyInsights(page,filters,page_section,data) {
       const overview = data.global;
       const container = page_section.container;
    
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
                        label:"Heures",
                        value:`${overview.done_hours}h`,
                        comment:`/${overview.total_hours}h`
                    })}
                </div>
                <div class="col-md-4">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#ffc107",
                        iconColor:"#ffc107",
                        icon:"fa fa-check-circle",
                        label:"Complétion",
                        value:`${overview.completion}%`
                    })}
                </div>
            </div>
            
            <!-- Niveaux -->
            <div class="frappe-card p-3 mb-4">
                <h5 class="mb-3">Niveaux</h5>
                <div class="row">
        `;
    
        data.level.forEach(l => {
            html += `
                <div class="col-md-4 mb-3">
                    <div class="program-card" onclick="navigateToLevel('${l.level.name}')">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <h6 class="mb-0">Niveau ${l.level.level}</h6>
                            <span class="badge badge-${l.completion_color}">${l.completion}%</span>
                        </div>
                        <div class="small text-muted mb-2">
                            <i class="fa fa-book mr-1"></i> ${l.count_teaching_unit} cours · 
                        </div>
                        <div class="progress progress-sm mb-2">
                            <div class="progress-bar bg-${l.completion_color}" style="width: ${l.completion}%"></div>
                        </div>
                        <div class="d-flex justify-content-between small">
                            <span>${l.done_hours}h effectuées</span>
                            <span class="text-muted">${l.sessions} sessions</span>
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
        
    }
};