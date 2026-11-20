window.Udshed = window.Udshed || {};

window.Udshed.Dialogs = {
    _check_edit(filter, userContext) {
        if (!Udshed.Perms || !Udshed.Perms.user_can_edit_planning_cell) return true;
        return Udshed.Perms.user_can_edit_planning_cell(filter, userContext);
    },

    _error(err, title) {
        const serverMessages = err && err._server_messages;
        let message = err && (err.message || err.exception || "");
        if (!message && serverMessages) {
            try {
                message = JSON.parse(serverMessages).map((entry) => JSON.parse(entry).message).join("<br/>");
            } catch (e) {
                message = String(serverMessages);
            }
        }
        frappe.msgprint({
            title: title || __("Erreur"),
            indicator: "red",
            message: message || __("Une erreur est survenue.")
        });
        frappe.utils.play_sound("error");
    },

    _type_options() {
        return [
            __("Cours Magistral (CM)"),
            __("Traveaux Pratiques (TP)"),
            __("Traveaux Dirigés (TD)"),
            __("Controlle Continue (CC)"),
            __("Examen de session normal"),
            __("Examen de rattrapage")
        ];
    },

    _mode_options() {
        return ["En présentiel", "En ligne", "Hybride"];
    },

    _room_field(defaultValue) {
        return {
            fieldtype: "Select",
            label: __("Salle"),
            fieldname: "salle",
            default: defaultValue || null,
            depends_on: 'eval:doc.mode!="En ligne"'
        };
    },

    _building_field(defaultValue, salleFieldName) {
        return {
            fieldtype: "Link",
            label: __("Batiment"),
            fieldname: "batiment",
            options: "Building",
            default: defaultValue || null,
            depends_on: 'eval:doc.mode!="En ligne"',
            change() {
                const dialog = cur_dialog;
                Udshed.UtilsQueries.loadRooms(this.get_value(), dialog.fields_dict[salleFieldName], (rooms) => {
                    dialog.fields_dict[salleFieldName].df.options = rooms || [];
                    dialog.fields_dict[salleFieldName].refresh();
                });
            }
        };
    },

    openCreatePlanningDialog(filter, day, half_day, halfLibelle, userContext, callback) {
        if (!this._check_edit(filter, userContext)) {
            frappe.show_alert({ message: __("Vous n'avez pas le droit de modifier ce créneau."), indicator: "red" });
            return;
        }
        const missing = [
            ["academic_year", __("année académique")],
            ["faculty", __("faculté")],
            ["filiere", __("filière")],
            ["niveau", __("niveau")]
        ].find(([key]) => !filter[key]);
        if (missing) {
            frappe.msgprint({
                title: __("Filtre requis"),
                indicator: "red",
                message: __("Veuillez sélectionner une {0} avant de créer une planification.").format(missing[1])
            });
            return;
        }

        const periodLabel = halfLibelle ? `(${halfLibelle})` : "";
        const dialog = new frappe.ui.Dialog({
            title: __(`Nouvelle planification du ${day.toLocaleDateString("fr-FR", { weekday: "long", day: "2-digit", month: "long" })} ${periodLabel}`),
            fields: [
                {
                    fieldtype: "Link",
                    label: __("Cours"),
                    fieldname: "cours",
                    options: "Teaching Unit",
                    get_query() {
                        return {
                            query: "udshed.api.course.get_teaching_unit_by_level",
                            freeze: true,
                            freeze_message: __("Chargement des cours..."),
                            filters: { ...filter }
                        };
                    },
                    reqd: 1
                },
                {
                    fieldtype: "Select",
                    label: __("Type"),
                    fieldname: "course_type",
                    options: this._type_options(),
                    reqd: 1
                },
                {
                    fieldtype: "Select",
                    label: __("Mode"),
                    fieldname: "mode",
                    options: this._mode_options(),
                    default: "En présentiel",
                    reqd: 1,
                    change() { dialog.refresh(); }
                },
                this._building_field(null, "salle"),
                this._room_field(null)
            ],
            primary_action_label: __("Créer"),
            primary_action(values) {
                frappe.call({
                    method: "udshed.api.planning_calendar.create_planning",
                    freeze: true,
                    freeze_message: __("Nouvelle planification en cours..."),
                    args: {
                        academic_year: filter.academic_year,
                        cours: values.cours,
                        course_type: values.course_type,
                        mode: values.mode,
                        batiment: values.batiment || null,
                        salle: values.salle || null,
                        day_of_week: frappe.datetime.obj_to_str(day),
                        half_day: half_day
                    },
                    callback: () => {
                        dialog.hide();
                        frappe.show_alert({ message: __("Planning créé."), indicator: "green" });
                        frappe.utils.play_sound("submit");
                        if (typeof callback === "function") callback();
                    },
                    error: (err) => window.Udshed.Dialogs._error(err, __("Échec de planification"))
                });
            }
        });
        dialog.show();
    },

    openEditPlanningDialog(filter, day, half_day, halfLibelle, course, userContext, callback) {
        if (!this._check_edit(filter, userContext)) {
            frappe.show_alert({ message: __("Vous n'avez pas le droit de modifier ce créneau."), indicator: "red" });
            return;
        }
        const item = course.item || {};
        const dialog = new frappe.ui.Dialog({
            title: __("Modifier la planification"),
            fields: [
                {
                    fieldtype: "Link",
                    label: __("Cours"),
                    fieldname: "cours",
                    options: "Teaching Unit",
                    get_query() {
                        return {
                            query: "udshed.api.course.get_teaching_unit_by_level",
                            freeze: true,
                            freeze_message: __("Chargement des cours..."),
                            filters: { ...filter }
                        };
                    },
                    reqd: 1,
                    default: item.cours
                },
                {
                    fieldtype: "Select",
                    label: __("Type"),
                    fieldname: "course_type",
                    options: this._type_options(),
                    default: item.type,
                    reqd: 1
                },
                {
                    fieldtype: "Select",
                    label: __("Mode"),
                    fieldname: "mode",
                    options: this._mode_options(),
                    default: item.mode || "En présentiel",
                    reqd: 1,
                    change() { dialog.refresh(); }
                },
                this._building_field(item.batiment_name || item.batiment, "salle"),
                this._room_field(item.salle_name || item.salle)
            ],
            primary_action_label: __("Mettre à jour"),
            primary_action(values) {
                frappe.call({
                    method: "udshed.api.planning_calendar.update_planning",
                    freeze: true,
                    freeze_message: __("Mise à jour du planning en cours..."),
                    args: {
                        planning_item_name: item.name,
                        academic_year: filter.academic_year,
                        cours: values.cours,
                        course_type: values.course_type,
                        mode: values.mode,
                        batiment: values.batiment || null,
                        salle: values.salle || null,
                        day_of_week: frappe.datetime.obj_to_str(day),
                        half_day: half_day
                    },
                    callback: () => {
                        dialog.hide();
                        frappe.show_alert({ message: __("Planning mis à jour."), indicator: "green" });
                        frappe.utils.play_sound("submit");
                        if (typeof callback === "function") callback();
                    },
                    error: (err) => window.Udshed.Dialogs._error(err, __("Échec de modification"))
                });
            }
        });
        dialog.$wrapper.find(".modal-footer").prepend(`
            <button class="btn btn-danger btn-delete-planning">
                <i class="fa fa-trash"></i> Supprimer
            </button>
        `);
        dialog.$wrapper.find(".btn-delete-planning").on("click", () => {
            frappe.confirm(__("Voulez-vous vraiment supprimer ce planning ?"), () => {
                Udshed.PlanningQueries.deletePlanning(item.name, () => {
                    dialog.hide();
                    if (typeof callback === "function") callback();
                });
            });
        });
        dialog.show();
    },

    openSendPlanningDialog(filter, userContext, callback) {
        if (!Udshed.Utils.isValidFecthDataFilter(filter)) {
            frappe.show_alert({ message: __("Sélectionnez une filière et un niveau, ou un enseignant, avant l'envoi."), indicator: "orange" });
            return;
        }
        const dialog = new frappe.ui.Dialog({
            title: __("Envoi du planning par mail"),
            fields: [
                {
                    fieldtype: "Check",
                    label: __("Envoyer à tous les enseignants"),
                    fieldname: "to_all_teacher",
                    depends_on: () => filter.niveau ? 1 : 0,
                    default: 0
                },
                {
                    fieldtype: "Check",
                    label: __("Envoyer à l'enseignant sélectionné"),
                    fieldname: "to_teacher",
                    depends_on: () => filter.teacher ? 1 : 0,
                    default: 0
                },
                {
                    fieldtype: "Check",
                    label: __("Recevoir le planning"),
                    fieldname: "to_me",
                    default: 0
                }
            ],
            primary_action_label: __("Envoyer le planning"),
            primary_action(values) {
                frappe.call({
                    method: "udshed.api.planning_calendar_email.send_planning_to_mail",
                    freeze: true,
                    freeze_message: __("Envoi du planning en cours..."),
                    args: {
                        filters: { ...filter },
                        to_all_teacher: values.to_all_teacher,
                        to_teacher: values.to_teacher,
                        to_me: values.to_me
                    },
                    callback: (response) => {
                        dialog.hide();
                        const result = response.message || {};
                        frappe.show_alert({
                            message: __("Planning envoyé à {0} destinataire(s).").format(result.sent || 0),
                            indicator: result.failed ? "orange" : "green"
                        });
                        if (typeof callback === "function") callback();
                    },
                    error: (err) => window.Udshed.Dialogs._error(err, __("Échec de l'envoi"))
                });
            }
        });
        dialog.show();
    }
};
