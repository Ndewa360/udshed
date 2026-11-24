window.Udshed = window.Udshed || {};

window.Udshed.Dialogs = {
    _check_edit(filter, userContext) {
        if (!Udshed.Perms || !Udshed.Perms.user_can_edit_planning_cell) return true;
        return Udshed.Perms.user_can_edit_planning_cell(filter, userContext);
    },

    _error(err, title) {
        return Udshed.Messages.error(err, title);
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
            Udshed.Messages.warning(__("Vous n'avez pas le droit de modifier ce créneau."));
            return;
        }
        const missing = [
            ["academic_year", __("année académique")],
            ["faculty", __("faculté")],
            ["filiere", __("filière")],
            ["niveau", __("niveau")]
        ].find(([key]) => !filter[key]);
        if (missing) {
            Udshed.Messages.validation(
                __("Veuillez sélectionner une {0} avant de créer une planification.").format(missing[1]),
                __("Filtre requis")
            );
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
                        half_day: half_day,
                        filiere: filter.filiere,
                        niveau: filter.niveau
                    },
                    callback: () => {
                        dialog.hide();
                        Udshed.Messages.success(__("Planning créé."));
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
            Udshed.Messages.warning(__("Vous n'avez pas le droit de modifier ce créneau."));
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
                        half_day: half_day,
                        filiere: filter.filiere || null,
                        niveau: filter.niveau || null
                    },
                    callback: () => {
                        dialog.hide();
                        Udshed.Messages.success(__("Planning mis à jour."));
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
            Udshed.Messages.confirm(__("Voulez-vous vraiment supprimer ce planning ?"), () => {
                Udshed.PlanningQueries.deletePlanning(item.name, () => {
                    dialog.hide();
                    if (typeof callback === "function") callback();
                }, filter);
            });
        });
        dialog.show();
    },

    openDuplicateWeekDialog(filter, currentWeekStart, callback) {
        if (!filter.academic_year || !filter.filiere || !filter.niveau) {
            Udshed.Messages.validation(__("Sélectionnez l'année, la filière et le niveau de la classe à dupliquer."), __("Filtre requis"));
            return;
        }
        let d = null;
        const esc = (v) => frappe.utils.escape_html(v === null || v === undefined ? "" : String(v));
        const lundi = (date) => frappe.datetime.obj_to_str(Udshed.DateUtils.getMonday(date));
        const cible = new Date(currentWeekStart);
        const source = new Date(currentWeekStart);
        source.setDate(source.getDate() - 7);
        const ETATS = {
            libre: ["#e8f5e9", __("Libre")],
            occupe_commun: ["#e3f2fd", __("Tronc commun / cours lié")],
            occupe: ["#eceff1", __("Déjà occupé")],
            a_creer: ["#c8e6c9", __("Sera dupliqué")],
            sans_salle: ["#fff3e0", __("Dupliqué sans salle")],
        };
        const ACTIONS = {
            a_creer: ["green", __("À créer")],
            sans_salle: ["orange", __("Sans salle")],
            deja_planifiee: ["blue", __("Déjà planifiée (commun)")],
            conflit: ["red", __("Créneau occupé")],
            ignoree: ["gray", __("Ignorée")],
        };
        const args = () => ({
            academic_year: filter.academic_year,
            filiere: filter.filiere,
            niveau: filter.niveau,
            semaine_source: d.get_value("semaine_source"),
            semaine_cible: d.get_value("semaine_cible"),
            inclure_evaluations: d.get_value("inclure_evaluations") ? 1 : 0,
        });

        const rendre = (data) => {
            const s = data.stats;
            const legende = Object.values(ETATS).map(([c, l]) => `<span style="background:${c};padding:2px 8px;border-radius:4px;margin-right:6px">${l}</span>`).join("");
            const recap = `
                <table class="table table-bordered table-sm" style="font-size:12px">
                    <thead><tr><th></th>${data.jours.map((j) => `<th>${esc(j)}</th>`).join("")}</tr></thead>
                    <tbody>${data.recapitulatif.map((ligne) => `
                        <tr><th style="white-space:nowrap">${esc(ligne.libelle)}<br><small class="text-muted">${esc(ligne.heures)}</small></th>
                        ${ligne.jours.map((c) => {
                            const [couleur, label] = ETATS[c.etat] || ["#fff", c.etat];
                            return `<td style="background:${couleur}" title="${esc(label)}">${esc(c.texte) || `<span class="text-muted">${label}</span>`}</td>`;
                        }).join("")}</tr>`).join("")}
                    </tbody>
                </table>`;
            const seances = data.seances.length ? `
                <table class="table table-sm">
                    <thead><tr><th>${__("Séance")}</th><th>${__("Cible")}</th><th>${__("Action")}</th></tr></thead>
                    <tbody>${data.seances.map((e) => {
                        const [couleur, label] = ACTIONS[e.action] || ["gray", e.action];
                        return `<tr><td>${esc(e.intitule)} <small class="text-muted">${esc(e.type)}</small>${e.commun ? ` <span class="indicator-pill blue">${__("commun")}</span>` : ""}</td>
                            <td>${esc(e.jour)} ${esc(e.date)}</td>
                            <td><span class="indicator-pill ${couleur}">${label}</span>${e.motif ? `<div class="small text-muted">${esc(e.motif)}</div>` : ""}</td></tr>`;
                    }).join("")}</tbody>
                </table>` : `<div class="text-muted">${__("Aucune séance dans la semaine source.")}</div>`;
            return `
                <div class="alert alert-info small">
                    ${__("{0} séance(s) à créer, {1} sans salle, {2} déjà planifiée(s) en commun, {3} en conflit, {4} ignorée(s).",
                        [s.a_creer, s.sans_salle, s.deja_planifiees, s.conflits, s.ignorees])}<br>
                    ${__("Semaine cible : {0} créneau(x) libre(s), {1} occupé(s) par un tronc commun / cours lié, {2} occupé(s) par d'autres cours.",
                        [s.creneaux_libres, s.creneaux_tronc_commun, s.creneaux_occupes])}
                </div>
                <h6>${__("Récapitulatif de la semaine cible")}</h6><div class="mb-2">${legende}</div>${recap}
                <h6>${__("Séances de la semaine source")}</h6>${seances}`;
        };

        let analyse = null;
        const previsualiser = () => frappe.call({
            method: "udshed.api.planning_duplication.previsualiser_duplication",
            args: args(),
            freeze: true,
            freeze_message: __("Analyse des créneaux..."),
            callback: (r) => {
                analyse = r.message;
                d.fields_dict.apercu.$wrapper.html(rendre(analyse));
                const n = analyse.stats.a_creer + analyse.stats.sans_salle;
                d.set_primary_action(n ? __("Dupliquer {0} séance(s)", [n]) : __("Rien à dupliquer"), n ? dupliquer : () => {});
            },
            error: (err) => Udshed.Messages.error(err, __("Analyse impossible")),
        });
        const dupliquer = () => frappe.call({
            method: "udshed.api.planning_duplication.dupliquer_semaine",
            type: "POST",
            args: args(),
            freeze: true,
            freeze_message: __("Duplication en cours..."),
            callback: (r) => {
                const res = r.message || {};
                d.hide();
                if ((res.echecs || []).length) {
                    Udshed.Messages.warning(__("{0} séance(s) dupliquée(s), {1} non créée(s) (créneau pris entre-temps).", [res.creees, res.echecs.length]));
                } else {
                    Udshed.Messages.success(__("{0} séance(s) dupliquée(s).", [res.creees]));
                }
                if (typeof callback === "function") callback();
            },
            error: (err) => Udshed.Messages.error(err, __("Duplication impossible")),
        });

        const reinit = () => {
            if (!d) return; // change déclenché pendant la construction du dialogue
            analyse = null;
            d.fields_dict.apercu.$wrapper.empty();
            d.set_primary_action(__("Prévisualiser"), previsualiser);
        };
        d = new frappe.ui.Dialog({
            title: __("Dupliquer le planning d'une semaine"),
            size: "extra-large",
            fields: [
                { fieldtype: "Date", fieldname: "semaine_source", label: __("Semaine à copier (n'importe quel jour)"), reqd: 1, default: lundi(source), change: reinit },
                { fieldtype: "Column Break" },
                { fieldtype: "Date", fieldname: "semaine_cible", label: __("Semaine de destination"), reqd: 1, default: lundi(cible), change: reinit },
                { fieldtype: "Column Break" },
                { fieldtype: "Check", fieldname: "inclure_evaluations", label: __("Inclure CC et examens"), default: 0, change: reinit },
                { fieldtype: "Section Break" },
                { fieldtype: "HTML", fieldname: "apercu" },
            ],
            primary_action_label: __("Prévisualiser"),
            primary_action: previsualiser,
        });
        d.show();
    },

    openSendPlanningDialog(filter, userContext, callback) {
        if (!Udshed.Utils.isValidFecthDataFilter(filter)) {
            Udshed.Messages.warning(__("Sélectionnez une filière et un niveau, ou un enseignant, avant l'envoi."));
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
                        const sendMessage = __("Planning envoyé à {0} destinataire(s).").format(result.sent || 0);
                        if (result.failed) Udshed.Messages.warning(sendMessage);
                        else Udshed.Messages.success(sendMessage);
                        if (typeof callback === "function") callback();
                    },
                    error: (err) => window.Udshed.Dialogs._error(err, __("Échec de l'envoi"))
                });
            }
        });
        dialog.show();
    },

    openRoomsAvailabilityDialog(currentWeekStart, periods) {
        const dayOptions = [
            { value: "Monday", label: __("Lundi") },
            { value: "Tuesday", label: __("Mardi") },
            { value: "Wednesday", label: __("Mercredi") },
            { value: "Thursday", label: __("Jeudi") },
            { value: "Friday", label: __("Vendredi") },
            { value: "Saturday", label: __("Samedi") }
        ];
        const periodOptions = (periods || []).map((period) => ({
            value: period.name,
            label: period.libelle || [period.heure_de_debut, period.heure_de_fin].filter(Boolean).join(" - ") || period.name
        }));
        if (!periodOptions.length) {
            Udshed.Messages.warning(__("Aucun créneau horaire disponible."));
            return;
        }

        const escapeHtml = (value) => String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
        const dayOffsets = { Monday: 0, Tuesday: 1, Wednesday: 2, Thursday: 3, Friday: 4, Saturday: 5 };
        let availabilityDialog;

        const render = async () => {
            if (!availabilityDialog) return;
            const day = availabilityDialog.get_value("day");
            const period = availabilityDialog.get_value("period");
            const building = availabilityDialog.get_value("building");
            const date = new Date(currentWeekStart);
            date.setDate(date.getDate() + (dayOffsets[day] || 0));
            const wrapper = availabilityDialog.fields_dict.availability.$wrapper;
            wrapper.html(`<div class="rooms-loading">${__("Chargement des salles...")}</div>`);
            const data = await Udshed.PlanningQueries.loadAvailableRooms(
                frappe.datetime.obj_to_str(date),
                period,
                building
            );
            if (!data) {
                wrapper.html(`<div class="rooms-empty">${__("Impossible de charger les salles disponibles.")}</div>`);
                return;
            }
            const total = data.buildings.reduce((sum, item) => sum + item.total, 0);
            const available = data.buildings.reduce((sum, item) => sum + item.available_count, 0);
            const selectedPeriod = periodOptions.find((option) => option.value === period);
            const buildingsHtml = data.buildings.map((item) => {
                const rooms = item.rooms.map((room) => `
                    <div class="room-chip ${room.available ? "available" : "occupied"}">
                        <span class="room-name">${escapeHtml(room.label)}</span>
                        <span class="room-type">${escapeHtml(room.type || "")}</span>
                        <span class="room-state">${room.available ? __("Libre") : `${__("Occupée")} : ${escapeHtml(room.occupant || "")}`}</span>
                    </div>
                `).join("");
                return `
                    <div class="rooms-building">
                        <div class="rooms-building-head">
                            <strong>${escapeHtml(item.label)}</strong>
                            <span>${item.available_count}/${item.total} ${__("libres")}</span>
                        </div>
                        <div class="rooms-grid">${rooms || `<div class="rooms-empty">${__("Aucune salle configurée.")}</div>`}</div>
                    </div>
                `;
            }).join("");
            wrapper.html(`
                <div class="rooms-availability">
                    <div class="rooms-summary">${available}/${total} ${__("salles libres")} · ${escapeHtml(day)} · ${escapeHtml(selectedPeriod ? selectedPeriod.label : period)}</div>
                    ${buildingsHtml || `<div class="rooms-empty">${__("Aucun bâtiment disponible.")}</div>`}
                </div>
            `);
        };

        availabilityDialog = new frappe.ui.Dialog({
            title: __("Salles libres par bâtiment"),
            fields: [
                {
                    fieldtype: "Select",
                    fieldname: "day",
                    label: __("Jour"),
                    options: dayOptions,
                    default: "Monday",
                    reqd: 1,
                    change: render
                },
                {
                    fieldtype: "Select",
                    fieldname: "period",
                    label: __("Créneau"),
                    options: periodOptions,
                    default: periodOptions[0].value,
                    reqd: 1,
                    change: render
                },
                {
                    fieldtype: "Link",
                    fieldname: "building",
                    label: __("Bâtiment"),
                    options: "Building",
                    change: render
                },
                {
                    fieldtype: "HTML",
                    fieldname: "availability"
                }
            ],
            primary_action_label: __("Fermer"),
            primary_action: () => availabilityDialog.hide()
        });
        availabilityDialog.set_secondary_action_label(__("Actualiser"));
        availabilityDialog.set_secondary_action(render);
        availabilityDialog.show();
        render();
    }
};
