window.Udshed = window.Udshed || {};
window.Udshed.Insight = window.Udshed.Insight || {};
window.Udshed.Insight.Finance = window.Udshed.Insight.Finance || {};
window.Udshed.Insight.Finance.Year = {
    showFinanceYearInsights(page,filters,page_section,data) {
        const container = page_section.container
        const evolutionChart = page_section.evolutionChart
        const overview = data.global;
        console.log("Frappe ",document,frappe.doc)
        let html = `
                <!-- KPIs -->
            <div class="row mb-4"> 
                <div class="col-md-4">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#007bff",
                        iconColor:"#007bff",
                        icon:"fa fa-clock-o",
                        label:"Heures effectuées",
                        value:`${overview.done_hours} h`
                    })}
                </div>
                <div class="col-md-4">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#28a745",
                        iconColor:"#28a745",
                        icon:"fa fa-money",
                        label:"Total à payé",
                        value:`${Udshed.Utils.formatCurrency(overview.consume_price,overview.default_currency)}`,
                    })}
                </div>
                <div class="col-md-4">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#ffc107",
                        iconColor:"#ffc107",
                        icon:"fa fa-percent",
                        label:"Taux horaire moyen",
                        value:`${Udshed.Utils.formatCurrency(overview.rate_moyenne,overview.default_currency)}`
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
                                                <span class="badge bg-light">${f.filiere} programmes ·.</span>
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
                <div class="col-md-4">
                    <div class="frappe-card p-3">
                        <h5 class="mb-3">Détail par grade</h5>
                        <table class="table table-sm">
                            <thead>
                                <tr>
                                    <th>Grade</th>
                                    <th class="text-right">Montant /heure</th>
                                </tr>
                            </thead>
                            <tbody>`
                            Object.entries(overview.default_finance_by_grade).sort((a,b)=>b[1] - a[1]).forEach(g => {
                            price = g[1]
                            grade = g[0]
                            html += `
                                <tr>
                                    <td><span class="grade-badge grade-${grade.replace(' ', '-')}">${grade}</span></td>
                                    <td class="currency-cell">${Udshed.Utils.formatCurrency(price,overview.default_currency)}</td>
                                </tr>
                            `;
                        });
                        html+=    `</tbody>
                        </table>                       
                    </div>
                </div>
            </div>
        `;
    
        
        container.html(html);
        
        // Initialiser les graphiques
        // this.initGlobalCharts(data);
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