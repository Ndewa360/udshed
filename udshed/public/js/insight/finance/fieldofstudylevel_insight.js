window.Udshed = window.Udshed || {};
window.Udshed.Insight = window.Udshed.Insight || {};
window.Udshed.Insight.Finance = window.Udshed.Insight.Finance || {};
window.Udshed.Insight.Finance.FieldOfStudyLevel = {
    showFinanceFieldOfStudyLevelInsights(page,filters,page_section,data) {
        const overview = data.global;
        const container = page_section.container
    
        let html = `
            <!-- KPIs -->
            <div class="row mb-4">
                <div class="col-md-3">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#007bff",
                        iconColor:"#007bff",
                        icon:"fa fa-clock-o",
                        label:"Heures",
                        value:`${overview.done_hours}h`,
                        comment:`/${overview.total_hours}h`
                    })}
                </div>
                <div class="col-md-3">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#28a745",
                        iconColor:"#28a745",
                        icon:"fa fa-money",
                        label:"Total à payé",
                        value:`${Udshed.Utils.formatCurrency(overview.consume_price,overview.default_currency)}`
                    })}
                </div>
                <div class="col-md-3">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#ffc107",
                        iconColor:"#ffc107",
                        icon:"fa fa-graduation-cap",
                        label:"Cours",
                        value:`${data.teaching_unit.length}`,
                    })}
                </div>
                <div class="col-md-3">
                    ${window.Udshed.Insight.UI.render_kpi_with_icon({
                        bgColor:"#17a2b8",
                        iconColor:"#17a2b8",
                        icon:"fa fa-book",
                        label:"Cours",
                        value:`${data.teaching_unit.length}`
                    })}
                </div>
            </div>
            
            <!-- Cours du niveau -->
            <div class="frappe-card p-3 mb-4">
                <h5 class="mb-3">Cours ${overview.level}</h5>
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>Cours</th>
                                <th>Enseignant</th>
                                <th>Sessions</th>
                                <th>Heures</th>
                                <th>A payer</th>
                            </tr>
                        </thead>
                        <tbody>
        `;
    
        data.teaching_unit.forEach(c => {
            html += `
                <tr class="cursor-pointer" onclick="navigateToCourse('${c.teaching_unit.name}')">
                    <td><strong>${c.teaching_unit.course}</strong><br><small>${c.teaching_unit.intitule_cours}</small></td>
                    <td>${c.teaching_unit.table_enseignant.map((ens)=>ens.enseignant).join(', ')}</td>
                    <td class="text-center">${c.sessions}</td>
                    <td>${c.done_hours}h <small class="text-muted">/${c.total_hours}h</small></td>

                    <td class="currency-cell amount-positive">${Udshed.Utils.formatCurrency(c.consume_price,overview.default_currency)}</td>
                </tr>
            `;
        });
    
        html += `
                        </tbody>
                    </table>
                </div>
            </div>
            
        `;
            
        container.html(html);
    }
};