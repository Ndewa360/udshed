window.Udshed = window.Udshed || {};

window.Udshed.PlanningQueries  = {
    fetchPlanningItems(filter,currentWeekStart,callback_function) {
        if(!Udshed.Utils.isValidFecthDataFilter(filter))
        {
           console.warn("Missing filters, cannot fetch planning items")
            callback_function([]);
            return; 
        }
        // ex:

        frappe.call({
            method: "udshed.api.planning_calendar.get_week_planning",
            freeze: true,
            freeze_message: __("Chargement du planning..."),
            args: { 
                // academic_year: filter.academic_year,
                // filiere: filter.filiere,
                // niveau: filter.niveau,
                ...filter,
                week_start: frappe.datetime.obj_to_str(currentWeekStart)// format YYYY-MM-DD
            },
            callback: (res) => {
                if(!res.message) return callback_function([])
                const items = res.message;
                return callback_function(items);
            }
        });
    },
    getPlanningType(level,startDate,academic_year,callback_function=()=>{})
    {
        console.log("Getting planning type for level ",level," week starting on ",startDate," and academic year ",academic_year)
        frappe.call({
            method: "udshed.api.planning_calendar.get_planning_type",
            freeze: true,
            freeze_message: __("Récupération du type de planning..."),
            args: { 
                field_of_study_level: level,
                week_start: frappe.datetime.obj_to_str(startDate),
                academic_year: academic_year
             },
            callback: (r) => {
                return callback_function(r.message);
            }
        });
    },

    deletePlanning(planning_name,callback_function=()=>{})
    {
        frappe.call({
            method: "udshed.api.planning_calendar.delete_planning",
            freeze: true,
            freeze_message: __("Suppression du planning en cours..."),
            args: { planning_name:planning_name },
            callback: (r) => {
                frappe.show_alert({ message:__('Planning supprimé avec succés.'), indicator:'green' });
                frappe.utils.play_sound("delete");
                callback_function(r.message);                
            }
        });
    },

    loadCoursePeriod(level,startDate,academic_year)
    {
        return new Promise((resolve, reject) => {
            frappe.call({
                method: "udshed.api.planning_period.get_period",
                freeze: true,
                freeze_message: __("Chargement des périodes de cours..."),
                args: { 
                    field_of_study_level: level,
                    week_start: frappe.datetime.obj_to_str(startDate),
                    academic_year: academic_year
                },
                callback: (r) => {
                    resolve(r.message);
                }
            });
        })
    },

    loadCourseDefaultPeriod()
    {
        return new Promise((resolve, reject) => {
            frappe.call({
                method: "udshed.api.planning_period.get_default_period",
                freeze: true,
                freeze_message: __("Chargement de la période de cours par défaut..."),
                callback: (r) => {
                    resolve(r.message);
                }
            });
        })
    }
    
}