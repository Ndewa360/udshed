window.Udshed = window.Udshed || {};

window.Udshed.UI = {
    _escape(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    },

    _format_hours(value) {
        const number = Number(value) || 0;
        return Number.isInteger(number) ? String(number) : String(Number(number.toFixed(2))).replace(".", ",");
    },

    _progress_html(item) {
        if (!item || !item.progress_label) return "";
        const pct = Math.max(0, Math.min(100, Number(item.progress_pct) || 0));
        let badge = "";
        if (item.progress_state === "depassement") {
            badge = `<span class="planning-item-badge over">Dépassement +${this._escape(this._format_hours(item.progress_extra_hours))}h</span>`;
        } else if (item.progress_is_last) {
            badge = `<span class="planning-item-badge done">Séance de fin</span>`;
        }
        const state = item.progress_state === "depassement" ? " over" : (item.progress_is_last ? " done" : "");
        return `
            <div class="planning-item-progress${state}">
                <div class="planning-progress-track"><div class="planning-progress-fill" style="width:${pct}%"></div></div>
                <div class="planning-progress-row"><span>${this._escape(item.progress_label)}</span>${badge}</div>
            </div>`;
    },

    get_grid_calendar_item(items, filter, coursePeriod) {
        const grid = Udshed.Utils.initDataPeriodForUi(coursePeriod);
        items.forEach((item) => {
            const date = new Date(item.date);
            const dayOfWeek = date.toLocaleDateString("en-US", { weekday: "long" });
            if (!grid[dayOfWeek]) return;
            const cell = grid[dayOfWeek].get(item.period);
            if (!cell) {
                grid[dayOfWeek].set(item.period, {
                    level: item.niveau_label || (filter && filter.niveau) || "",
                    items: [item],
                    teachers: [...(item.teachers || [])]
                });
            } else {
                cell.items.push(item);
                (item.teachers || []).forEach((teacher) => {
                    if (!cell.teachers.includes(teacher)) cell.teachers.push(teacher);
                });
            }
        });
        return grid;
    },

    show_calendar_hearder() {
        return `
            <div class="planning-calendar" id="planning_calendar">
                <div class="planning-nav">
                    <div class="planning-nav-left">
                        <button class="btn btn-default btn-sm" id="prev-week">◀</button>
                        <button class="btn btn-default btn-sm" id="today-week">Aujourd’hui</button>
                        <button class="btn btn-default btn-sm" id="next-week">▶</button>
                    </div>
                    <div class="planning-nav-center"><span id="week-label"></span></div>
                    <div class="planning-nav-right">
                        <select id="month-picker" class="form-control input-sm"></select>
                        <select id="week-select" class="form-control input-sm"></select>
                    </div>
                </div>
                <div class="planning-grid"></div>
            </div>
        `;
    },

    show_calendar(calendar_zone, grid_data, coursePeriod, forTeacher = false, filter = null, userContext = null) {
        if (!calendar_zone) return;
        calendar_zone.empty();
        const plan = new Map();
        coursePeriod.forEach((period) => {
            plan.set(period.name, {
                libelle: period.libelle,
                items: [],
                fuseau_horaire: period.fuseau_horaire,
                heure_de_debut: period.heure_de_debut,
                heure_de_fin: period.heure_de_fin
            });
        });

        const canEdit = Udshed.Perms && filter && Udshed.Perms.user_can_edit_planning_cell(filter, userContext);
        const classByType = {
            "Cours Magistral (CM)": "cm",
            "Cours": "cm",
            "Traveaux Pratiques (TP)": "tp",
            "Travaux Pratique (TP)": "tp",
            "Traveaux Dirigés (TD)": "td",
            "Travaux Dirigés (TD)": "td",
            "Controlle Continue (CC)": "cc",
            "Examen de session normal": "exam",
            "Examen de rattrapage": "exam"
        };

        for (const day of ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]) {
            for (const period of coursePeriod) {
                const periodItem = grid_data && grid_data[day] ? grid_data[day].get(period.name) : null;
                let periodCell = "";
                if (periodItem && periodItem.items && periodItem.items.length) {
                    const cards = periodItem.items.map((item) => {
                        const css = classByType[item.type] || "cm";
                        const title = item.intitule_label || item.course_label || item.cours;
                        const teacherInfo = forTeacher
                            ? `${item.filiere || ""} ${item.niveau_label || ""}`.trim()
                            : (item.teachers || []).join(" • ");
                        const location = item.mode === "En ligne"
                            ? "En ligne"
                            : [item.batiment, item.salle].filter(Boolean).join(" / ") || "—";
                        const modeBadge = (item.mode && item.mode !== "En présentiel"
                            ? `<span class="planning-item-mode">${this._escape(item.mode)}</span>`
                            : "") + (item.cours_lie
                            // Cours lié : séance commune planifiée via la grille d'une autre classe.
                            ? `<span class="planning-item-mode" title="${this._escape(__("Séance commune avec « {0} »", [item.cours_planifie_label || item.cours]))}">🔗 ${__("commun")}</span>`
                            : "");
                        const courseData = this._escape(JSON.stringify({ item: item }));
                        return `
                            <div class="planning-item ${css}" data-course="${courseData}">
                                <div class="planning-item-head">
                                    <span class="planning-item-kind">${this._escape(item.type || "")}</span>
                                    ${modeBadge}
                                </div>
                                <div class="planning-item-title">${this._escape(title)}</div>
                                <div class="planning-item-details">
                                    <span>${this._escape(location)}</span>
                                    <span>${this._escape(teacherInfo || "—")}</span>
                                </div>
                                ${this._progress_html(item)}
                            </div>`;
                    }).join("");
                    const cellData = this._escape(JSON.stringify({ item: periodItem.items[0] }));
                    periodCell = `
                        <div class="planning-cell ${canEdit ? "" : "readonly"}" data-day="${day}" data-half-libelle="${this._escape(period.libelle)}" data-half="${this._escape(period.name)}" data-course="${cellData}">
                            ${cards}
                        </div>`;
                } else {
                    periodCell = `
                        <div class="planning-cell ${canEdit ? "" : "readonly"} empty" data-day="${day}" data-half="${this._escape(period.name)}">
                            <div class="no-course">Pas cours</div>
                        </div>`;
                }
                plan.get(period.name).items.push(periodCell);
            }
        }

        let calendarHTML = `
            <div></div>
            <div class="planning-header">Lundi</div>
            <div class="planning-header">Mardi</div>
            <div class="planning-header">Mercredi</div>
            <div class="planning-header">Jeudi</div>
            <div class="planning-header">Vendredi</div>
            <div class="planning-header">Samedi</div>`;
        for (const period of plan.keys()) {
            const info = plan.get(period);
            const start = String(info.heure_de_debut || "").split(":");
            const end = String(info.heure_de_fin || "").split(":");
            calendarHTML += `
                <div class="planning-time-label">
                    ${info.libelle ? `<span>${this._escape(info.libelle)}</span>` : ""}
                    <div class="planning-time-range">${start[0] || ""}:${start[1] || ""} - ${end[0] || ""}:${end[1] || ""}</div>
                    <div class="planning-time-fuseau">${this._escape(info.fuseau_horaire)}</div>
                </div>
                ${info.items.join("")}`;
        }
        calendar_zone.html(calendarHTML);
    },

    update_page_actions(filter, btnExportPDF, btnEnvoiMail) {
        const valid = Udshed.Utils.isValidFecthDataFilter(filter);
        if (valid) {
            btnExportPDF.show();
            btnEnvoiMail.show();
        } else {
            btnExportPDF.hide();
            btnEnvoiMail.hide();
        }
    }
};
