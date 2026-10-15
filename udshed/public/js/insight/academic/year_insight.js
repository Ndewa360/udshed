window.Udshed = window.Udshed || {};
window.Udshed.Insight = window.Udshed.Insight || {};
window.Udshed.Insight.Academic = window.Udshed.Insight.Academic || {};
window.Udshed.Insight.Academic.Year = {
    showAcademicYearInsights(page,filters,page_section,data) {
        const container = page_section.container
        const evolutionChart = page_section.evolutionChart
        const overview = data.global;
    
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
                        label:"Heures effectuées",
                        value:`${overview.done_hours} h`,
                        comment: `/${overview.total_hours} h`
                    })}
                </div>
                <div class="col-md-4">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#ffc107",
                        iconColor:"#ffc107",
                        icon:"fa fa-check-circle",
                        label:"Taux complétion",
                        value:`${Math.floor(overview.completion)}%`,
                        comment: `${overview.end_course} terminés`
                    })}
                </div>
                
            </div>
            
            <!-- Graphiques -->
            <div class="row mb-4">
                <div class="col-md-8">
                    <!-- Résumé par faculté -->
                    <div class="frappe-card p-3 mb-4">
                        <h5 class="mb-3">Résumé par faculté</h5>
                        <div class="row">`                    
                            data.faculte.forEach(f => {
                                html += `
                                    <div class="col-md-4 mb-3">
                                        <div class="program-card" onclick="navigateToFaculty('${f.faculty.faculty_name}')">
                                            <div class="d-flex justify-content-between align-items-center mb-2">
                                                <h6 class="mb-0">${f.faculty.faculty_name}</h6>
                                                <span class="badge badge-${f.completion_color}">${f.completion}%</span>
                                            </div>
                                            <div class="small text-muted mb-2">
                                                <i class="fa fa-book mr-1"></i> ${f.filiere} programmes · 
                                                <i class="fa fa-clock-o mr-1"></i> ${f.sessions} sessions
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
                <div class="col-md-4">
                    <div class="frappe-card p-3">
                        <h5 class="mb-3">Répartition par statut</h5>
                        <div id="status-chart" style="height: 300px;"></div>
                    </div>
                </div>
            </div>
        `;
    
        
        container.html(html);
        
        // Initialiser les graphiques
        this.initGlobalCharts(data);
    },
    initGlobalCharts(data) {
        // Graphique des statuts
        new frappe.Chart("#status-chart", {
            data: {
                labels: data.global.sessions_map.map(s => s.type),
                datasets: [
                    {
                        name: "Sessions",
                        values: data.global.sessions_map.map(s => s.value),
                        chartType: 'pie'
                    }
                ]
            },
            type: 'pie',
            height: 280,
            colors: ['#ffc107', '#17a2b8', '#28a745', '#dc3545', '#fd7e14']
        });
    },
};