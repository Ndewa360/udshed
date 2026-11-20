window.Udshed = window.Udshed || {};
window.Udshed.Utils = {
    refresh_filter(filters, field, page, levelMap)
    {
        const clear_field = (name, clear_options = true) => {
            const control = page && page.fields_dict && page.fields_dict[name];
            if (!control) return;
            filters[name] = null;
            if (control.get_value && control.get_value()) control.set_value(null);
            if (clear_options && control.df && control.df.fieldtype === "Select") control.df.options = [];
            if (control.refresh) control.refresh();
        };
        const clear_level_map = () => {
            if (levelMap && typeof levelMap === "object") Object.keys(levelMap).forEach((key) => delete levelMap[key]);
        };
        const previous_sync = page && page._planning_filter_sync;
        if (page) page._planning_filter_sync = true;
        try {
            if (field === "academic_year") {
                clear_field("faculty");
                clear_field("filiere");
                clear_field("niveau");
                clear_field("semestre", false);
                clear_level_map();
            } else if (field === "faculty") {
                clear_field("filiere");
                clear_field("niveau");
                clear_field("semestre", false);
                clear_level_map();
            } else if (field === "filiere") {
                clear_field("niveau");
                clear_field("semestre", false);
                clear_level_map();
            }
        } finally {
            if (page) page._planning_filter_sync = previous_sync;
        }
    },

    mergeDataByKey(arr1,arr2,key)
    {
        const map = new Map();
        [...arr1,...arr2].forEach((item)=>
        {
            map.set(item[key], {...map.get(item[key]),...item})
        })
    },
    isValidFecthDataFilter(filter)
    {
        if (!filter || !filter.academic_year) return false;
        return Boolean(filter.teacher || (filter.filiere && filter.niveau));
    },
    
    is_valide_filter(filter)
    {
        return filter.academic_year && filter.faculty && filter.filiere && filter.niveau;
    },

    initDataPeriodForUi(coursePeriod)
    {
        let grid = {};

        for(let day of ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"])
        {
            let mapDay = new Map()
            coursePeriod.forEach((period)=>{
                mapDay.set(period.name,null)
            })
            grid[day] = mapDay;
        }
        return grid;
    },
    formatCurrency(amount,currency) {
        return new Intl.NumberFormat('fr-FR', { 
            style: 'currency', 
            currency: currency,
        }).format(amount);
    },
    make_download_file_word(data,filename="contract_to_signed")
    {
        const byteCharacters = atob(data);
        const byteNumbers = new Array(byteCharacters.length);

        for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }

        const byteArray = new Uint8Array(byteNumbers);

        const blob = new Blob([byteArray], {
            type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        });

        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `${filename}.docx`;
        link.click();
    }
}

window.Udshed.Messages = {
    _types: {
        success: { label: "Succès", icon: "✓" },
        error: { label: "Erreur", icon: "!" },
        warning: { label: "Attention", icon: "!" },
        info: { label: "Information", icon: "i" }
    },

    _escape(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    },

    _htmlToText(value) {
        return String(value || "")
            .replace(/<br\s*\/?>/gi, "\n")
            .replace(/<[^>]*>/g, "")
            .replace(/&nbsp;/g, " ")
            .replace(/&amp;/g, "&")
            .replace(/&lt;/g, "<")
            .replace(/&gt;/g, ">")
            .trim();
    },

    _parseError(err) {
        let raw = "";
        if (err && err._server_messages) {
            try {
                raw = JSON.parse(err._server_messages)
                    .map((entry) => {
                        try {
                            return JSON.parse(entry).message || entry;
                        } catch (e) {
                            return entry;
                        }
                    })
                    .join("\n");
            } catch (e) {
                raw = String(err._server_messages);
            }
        }
        if (!raw) raw = err && (err.message || err.exception || err.responseText || "");
        const message = this._htmlToText(raw) || __("Une erreur est survenue.");
        const details = err && err.exception && String(err.exception) !== message ? String(err.exception) : "";
        return { message, details };
    },

    toast(message, type = "info", title = null, duration = null) {
        let stack = $(".udshed-toast-stack");
        if (!stack.length) stack = $('<div class="udshed-toast-stack"></div>').appendTo("body");
        const config = this._types[type] || this._types.info;
        const toast = $(`
            <div class="udshed-toast ${type}">
                <span class="udshed-toast-icon">${config.icon}</span>
                <div class="udshed-toast-content">
                    <strong>${this._escape(title || config.label)}</strong>
                    <span>${this._escape(message)}</span>
                </div>
                <button class="udshed-toast-close" type="button" aria-label="Fermer">×</button>
            </div>
        `);
        stack.append(toast);
        const close = () => toast.addClass("is-leaving").delay(180).queue((next) => { toast.remove(); next(); });
        toast.find(".udshed-toast-close").on("click", close);
        const delay = duration === null ? (type === "error" || type === "warning" ? 7000 : 4000) : duration;
        if (delay > 0) setTimeout(close, delay);
        return toast;
    },

    success(message, title = null) {
        return this.toast(message, "success", title || __("Succès"));
    },

    info(message, title = null) {
        return this.toast(message, "info", title || __("Information"));
    },

    warning(message, title = null) {
        return this.toast(message, "warning", title || __("Attention"));
    },

    dialog({ title, message, type = "info", details = "", primaryLabel = null, onPrimary = null, secondaryLabel = null, onSecondary = null }) {
        const config = this._types[type] || this._types.info;
        const detailsHtml = details
            ? `<details class="udshed-message-details"><summary>${this._escape(__("Détails techniques"))}</summary><pre>${this._escape(details)}</pre></details>`
            : "";
        const secondaryHtml = secondaryLabel
            ? `<button class="btn btn-default udshed-message-secondary" type="button">${this._escape(secondaryLabel)}</button>`
            : "";
        const overlay = $(`
            <div class="udshed-message-overlay ${type}">
                <div class="udshed-message-card" role="dialog" aria-modal="true">
                    <div class="udshed-message-icon">${config.icon}</div>
                    <div class="udshed-message-body">
                        <h3>${this._escape(title || config.label)}</h3>
                        <p>${this._escape(message)}</p>
                        ${detailsHtml}
                    </div>
                    <div class="udshed-message-actions">
                        ${secondaryHtml}
                        <button class="btn btn-primary udshed-message-primary" type="button">${this._escape(primaryLabel || __("Fermer"))}</button>
                    </div>
                </div>
            </div>
        `).appendTo("body");
        const close = () => {
            overlay.removeClass("is-visible");
            setTimeout(() => overlay.remove(), 160);
        };
        overlay.find(".udshed-message-primary").on("click", () => {
            if (typeof onPrimary === "function" && onPrimary(close) === false) return;
            close();
        });
        overlay.find(".udshed-message-secondary").on("click", () => {
            if (typeof onSecondary === "function") onSecondary(close);
            close();
        });
        overlay.on("click", (event) => {
            if (event.target === overlay[0]) close();
        });
        setTimeout(() => overlay.addClass("is-visible"), 0);
        return overlay;
    },

    error(err, title = null) {
        const parsed = this._parseError(err);
        frappe.utils.play_sound("error");
        return this.dialog({
            title: title || __("Erreur"),
            message: parsed.message,
            details: parsed.details,
            type: "error"
        });
    },

    validation(message, title = null) {
        return this.dialog({
            title: title || __("Information requise"),
            message: message,
            type: "warning"
        });
    },

    confirm(message, onConfirm, onCancel, title = null) {
        return this.dialog({
            title: title || __("Confirmation"),
            message: message,
            type: "warning",
            primaryLabel: __("Confirmer"),
            onPrimary: onConfirm,
            secondaryLabel: __("Annuler"),
            onSecondary: onCancel
        });
    }
};
