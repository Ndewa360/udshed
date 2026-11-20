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

    get_grid_calendar_item(items, filter, coursePeriod) {
        const grid = Udshed.Utils.initDataPeriodForUi(coursePeriod);
        items.forEach((item) => {
            const date = new Date(item.date);
            const dayOfWeek = date.toLocaleDateString("en-US", { weekday: "long" });
            if (!grid[dayOfWeek]) return;
            if (!grid[dayOfWeek].has(item.period)) {
                grid[dayOfWeek].set(item.period, {
                    subject: item.course || item.cours_label,
                    level: filter && filter.niveau,
                    item: item,
                    teachers: item.teachers || []
                });
            } else {
                const cell = grid[dayOfWeek].get(item.period);
                cell.teachers = [...new Set([...(cell.teachers || []), ...(item.teachers || [])])];
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
                if (periodItem && periodItem.item) {
                    const item = periodItem.item;
                    const css = classByType[item.type] || "cm";
                    const teacherInfo = forTeacher
                        ? `<b>${this._escape(item.filiere)} ${this._escape(item.niveau_label)}</b>`
                        : (periodItem.teachers || []).map((teacher) => `<b>${this._escape(teacher)}</b>`).join("<br/> ");
                    const modeInfo = item.mode === "En ligne"
                        ? "En ligne <br/> - <br/>"
                        : `Batiment: ${this._escape(item.batiment || "")} <br/> Salle: ${this._escape(item.salle || "")}<br/> - <br/>`;
                    const courseData = this._escape(JSON.stringify(periodItem));
                    periodCell = `
                        <div class="planning-cell ${canEdit ? "" : "readonly"}" data-day="${day}" data-half-libelle="${this._escape(period.libelle)}" data-half="${this._escape(period.name)}" data-course="${courseData}">
                            <div class="planning-item ${css}">
                                <div class="planning-item-title">
                                    <span style="font-style:italic">${this._escape(periodItem.subject)}</span><br/>${this._escape(item.cours_label)}
                                </div>
                                <div class="planning-item-meta">${this._escape(item.type)} <br/> - <br/> ${this._escape(item.salle || "")}</div>
                                <div class="planning-item-meta">${modeInfo}</div>
                                <div class="planning-item-meta">${teacherInfo}</div>
                            </div>
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
