window.Udshed = window.Udshed || {};

window.Udshed.UtilsQueries = {
    get_data_of_user(callback) {
        return new Promise((resolve) => {
            frappe.call({
                method: "udshed.api.user_data.get_user_context",
                callback: (response) => {
                    const data = response.message || [];
                    if (typeof callback === "function") callback(data);
                    resolve(data);
                },
                error: () => {
                    frappe.show_alert({
                        message: __("Impossible de charger votre contexte utilisateur."),
                        indicator: "red"
                    });
                    resolve([]);
                }
            });
        });
    },

    loadLevels(filiere, niveau_field, callback_function) {
        niveau_field.df.options = [];
        niveau_field.refresh();
        if (!filiere) {
            if (typeof callback_function === "function") callback_function([]);
            return Promise.resolve([]);
        }
        return new Promise((resolve) => {
            frappe.call({
                method: "udshed.api.course.get_levels_for_field",
                freeze: true,
                freeze_message: __("Chargement des niveaux académique..."),
                args: { field_of_study: filiere },
                callback: (response) => {
                    const levels = response.message || [];
                    if (typeof callback_function === "function") callback_function(levels);
                    resolve(levels);
                },
                error: () => resolve([])
            });
        });
    },

    loadRooms(batiment, salle_field, callback_function) {
        salle_field.df.options = [];
        salle_field.refresh();
        if (!batiment) {
            if (typeof callback_function === "function") callback_function([]);
            return Promise.resolve([]);
        }
        return new Promise((resolve) => {
            frappe.call({
                method: "udshed.api.building.get_room_by_building",
                freeze: true,
                freeze_message: __("Chargement des salles..."),
                args: { building: batiment },
                callback: (response) => {
                    const rooms = response.message || [];
                    if (typeof callback_function === "function") callback_function(rooms);
                    resolve(rooms);
                },
                error: () => resolve([])
            });
        });
    }
};
