window.Udshed = window.Udshed || {};

window.Udshed.PlanningQueries = {
    _show_error(err, title) {
        const message = (err && (err.message || err.exception || err._server_messages)) || __("Une erreur est survenue.");
        frappe.show_alert({ message: `${title} : ${message}`, indicator: "red" });
    },

    fetchPlanningItems(filter, currentWeekStart, callback_function) {
        if (!Udshed.Utils.isValidFecthDataFilter(filter)) {
            if (typeof callback_function === "function") callback_function([]);
            return Promise.resolve([]);
        }
        return new Promise((resolve) => {
            frappe.call({
                method: "udshed.api.planning_calendar.get_week_planning",
                freeze: true,
                freeze_message: __("Chargement du planning..."),
                args: {
                    academic_year: filter.academic_year,
                    faculty: filter.faculty || null,
                    filiere: filter.filiere || null,
                    niveau: filter.niveau || null,
                    teacher: filter.teacher || null,
                    week_start: frappe.datetime.obj_to_str(currentWeekStart)
                },
                callback: (response) => {
                    const items = response.message || [];
                    if (typeof callback_function === "function") callback_function(items);
                    resolve(items);
                },
                error: (err) => {
                    this._show_error(err, __("Chargement du planning"));
                    if (typeof callback_function === "function") callback_function([]);
                    resolve([]);
                }
            });
        });
    },

    getPlanningType(level, startDate, academic_year, callback_function) {
        return new Promise((resolve) => {
            frappe.call({
                method: "udshed.api.planning_calendar.get_planning_type",
                freeze: true,
                freeze_message: __("Récupération du type de planning..."),
                args: {
                    field_of_study_level: level,
                    week_start: frappe.datetime.obj_to_str(startDate),
                    academic_year: academic_year
                },
                callback: (response) => {
                    const value = response.message || "Cours";
                    if (typeof callback_function === "function") callback_function(value);
                    resolve(value);
                },
                error: (err) => {
                    this._show_error(err, __("Type de planning"));
                    resolve("Cours");
                }
            });
        });
    },

    deletePlanning(planning_name, callback_function) {
        return new Promise((resolve) => {
            frappe.call({
                method: "udshed.api.planning_calendar.delete_planning",
                freeze: true,
                freeze_message: __("Suppression du planning en cours..."),
                args: { planning_name: planning_name },
                callback: (response) => {
                    frappe.show_alert({ message: __("Planning supprimé avec succès."), indicator: "green" });
                    frappe.utils.play_sound("delete");
                    if (typeof callback_function === "function") callback_function(response.message);
                    resolve(response.message);
                },
                error: (err) => {
                    this._show_error(err, __("Suppression du planning"));
                    resolve(null);
                }
            });
        });
    },

    loadCoursePeriod(level, startDate, academic_year) {
        return new Promise((resolve) => {
            frappe.call({
                method: "udshed.api.planning_period.get_period",
                freeze: true,
                freeze_message: __("Chargement des périodes de cours..."),
                args: {
                    field_of_study_level: level,
                    week_start: frappe.datetime.obj_to_str(startDate),
                    academic_year: academic_year
                },
                callback: (response) => resolve(response.message || []),
                error: (err) => {
                    this._show_error(err, __("Périodes de cours"));
                    resolve([]);
                }
            });
        });
    },

    loadCourseDefaultPeriod() {
        return new Promise((resolve) => {
            frappe.call({
                method: "udshed.api.planning_period.get_default_period",
                freeze: true,
                freeze_message: __("Chargement de la période de cours par défaut..."),
                callback: (response) => resolve(response.message || []),
                error: (err) => {
                    this._show_error(err, __("Périodes par défaut"));
                    resolve([]);
                }
            });
        });
    },

    loadAcademicYearMonths(academic_year) {
        if (!academic_year) return Promise.resolve([]);
        return new Promise((resolve) => {
            frappe.call({
                method: "udshed.api.user_data.get_academic_year_months",
                args: { academic_year: academic_year },
                callback: (response) => resolve(response.message || []),
                error: (err) => {
                    this._show_error(err, __("Mois de l'année académique"));
                    resolve([]);
                }
            });
        });
    }
};
