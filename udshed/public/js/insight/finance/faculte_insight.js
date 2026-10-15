window.Udshed = window.Udshed || {};
window.Udshed.Insight = window.Udshed.Insight || {};
window.Udshed.Insight.Finance = window.Udshed.Insight.Finance || {};
window.Udshed.Insight.Finance.Faculty = {
    showFinanceFacultyInsights(page,filters,page_section,data) {
        const overview = data.global;
        const container = page_section.container
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
                        value:`${Udshed.Utils.formatCurrency(overview.consume_price,overview.default_currency)}`
                    })}
                </div>
                <div class="col-md-4">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#ffc107",
                        iconColor:"#ffc107",
                        icon:"fa fa-graduation-cap",
                        label:"Taux horaire moyen",
                        value:`${Udshed.Utils.formatCurrency(overview.rate_moyenne,overview.default_currency)}`
                    })}
                </div>
            </div>
            
            <!-- Programmes -->
            <div class="frappe-card p-3 mb-4">
                <h5 class="mb-3">Programmes de la faculté</h5>
                <div class="row">
        `;
                    data.filiere.forEach(f => {
                        html += `
                            <div class="col-md-4 mb-3">
                                <div class="program-card" onclick="navigateToFaculty('${f.filiere.name}')">
                                    <div class="d-flex justify-content-between align-items-center mb-2">
                                        <h6 class="mb-0">${f.filiere.name_of_field}</h6>
                                        <span class="badge bg-light">${f.niveau_count} niveaux.</span>
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
    
        html += `
                </div>
            </div>
        `;
    
        container.html(html);
        
        // Graphique des niveaux
        // Udshed.Insight.UI.initLevelChart(data.by_level);
    }
};