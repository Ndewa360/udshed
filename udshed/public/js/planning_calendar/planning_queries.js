window.Udshed = window.Udshed || {};

window.Udshed.PlanningQueries = {
    _show_error(err, title) {
        Udshed.Messages.error(err, title);
    },

    fetchPlanningItems(filter, currentWeekStart, callback_function) {
        if (!Udshed.Utils.isValidFecthDataFilter(filter)) {
            if (typeof callback_function === "function") callback_function([]);
            return Promise.resolve([]);
        }
        return new Promise((resolve) => {
            Udshed.Loading.call({
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
            Udshed.Loading.call({
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
            Udshed.Loading.call({
                method: "udshed.api.planning_calendar.delete_planning",
                freeze: true,
                freeze_message: __("Suppression du planning en cours..."),
                args: { planning_name: planning_name },
                callback: (response) => {
                    Udshed.Messages.success(__("Planning supprimé avec succès."));
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
            Udshed.Loading.call({
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
            Udshed.Loading.call({
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
            Udshed.Loading.call({
                method: "udshed.api.user_data.get_academic_year_months",
                loading_message: __("Chargement des mois de l'année académique..."),
                args: { academic_year: academic_year },
                callback: (response) => resolve(response.message || []),
                error: (err) => {
                    this._show_error(err, __("Mois de l'année académique"));
                    resolve([]);
                }
            });
        });
    },

    loadAvailableRooms(date, period, building) {
        if (!date || !period) return Promise.resolve(null);
        return new Promise((resolve) => {
            Udshed.Loading.call({
                method: "udshed.api.building.get_available_rooms",
                loading_message: __("Chargement des salles disponibles..."),
                args: { date: date, period: period, building: building || null },
                callback: (response) => resolve(response.message || null),
                error: (err) => {
                    this._show_error(err, __("Salles disponibles"));
                    resolve(null);
                }
            });
        });
    }
};
