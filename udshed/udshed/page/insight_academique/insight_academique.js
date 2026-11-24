// Insight académique : avancement des cours (planifié, effectué, pointé, retard).
// Calculs : udshed.insight (moteur unique) ; affichage : insight_dashboard.js.
frappe.pages["insight-academique"].on_page_load = function (wrapper) {
	frappe.require(["/assets/udshed/css/insight.css", "/assets/udshed/js/utils/utils.js", "/assets/udshed/js/insight/insight_dashboard.js"]).then(() => {
		wrapper.insight = new Udshed.Insight.Dashboard(wrapper, "academique");
	});
};
