window.Udshed = window.Udshed || {};
window.Udshed.Insight = window.Udshed.Insight || {};
window.Udshed.Insight.Finance = window.Udshed.Insight.Finance || {};
window.Udshed.Insight.Finance.FieldOfStudy = {
    showFinanceFieldOfStudyInsights(page,filters,page_section,data) {
       const overview = data.global;
       const container = page_section.container;
    
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
                        icon:"fa fa-check-circle",
                        label:"Taux horaire moyen",
                        value:`${Udshed.Utils.formatCurrency(overview.rate_moyenne,overview.default_currency)}`
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
                            <div class="program-card" onclick="navigateToFaculty('${l.level.name}')">
                                <div class="d-flex justify-content-between align-items-center mb-2">
                                    <h6 class="mb-0">${l.level.level}</h6>
                                    <span class="badge bg-light">${l.count_teaching_unit} cours ·</span>
                                </div>
                                <div class="row g-2 mb-2">
                                    <div class="col-6">
                                        <div class="small text-muted">Heures</div>
                                        <div class="font-weight-bold">${l.done_hours} h</div>
                                    </div>
                                    <div class="col-6">
                                        <div class="small text-muted">Montant</div>
                                        <div class="font-weight-bold amount-positive">${Udshed.Utils.formatCurrency(l.consume_price,overview.default_currency)} </div>
                                    </div>
                                </div>
                                <div class="progress progress-sm">
                                    <div class="progress-bar bg-primary" style="width: ${l.completion_finance}%"></div>
                                </div>
                                <div class="small text-muted mt-1">${l.sessions} sessions ·</div>
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