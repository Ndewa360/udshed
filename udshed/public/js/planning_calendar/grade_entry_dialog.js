window.Udshed = window.Udshed || {};
window.Udshed.GradeEntry = {

    openGradeEntryDialog(planningItemData, callback) {
        const self = this;
        let planning = planningItemData.item;

        frappe.call({
            method: "udshed.api.planning_grade_entry.get_students_for_grade_entry",
            freeze: true,
            freeze_message: __("Chargement des étudiants..."),
            args: {
                planning_item_name: planning.name,
            },
            callback: (r) => {
                if (!r.message || !r.message.students) {
                    frappe.msgprint(__("Aucun étudiant inscrit pour ce cours."));
                    return;
                }
                self._showGradeDialog(r.message, callback);
            },
            error: (err) => {
                frappe.msgprint({
                    title: __("Erreur"),
                    indicator: "red",
                    message: __("Impossible de charger les étudiants : ") + (err.message || ""),
                });
            },
        });
    },

    _showGradeDialog(data, callback) {
        const planning = data.planning;
        const students = data.students;
        const type = planning.type || "";
        const isCC = type.includes("CC") || type === "Controlle Continue (CC)";
        const isRattrapage = type.toLowerCase().includes("rattrapage");
        let noteLabel = __("Note Examen (sur 20)");
        if (isCC) noteLabel = __("Note CC (sur 20)");
        if (isRattrapage) noteLabel = __("Note Rattrapage (sur 20)");

        let dialog = new frappe.ui.Dialog({
            title: __("Saisie des notes — {0}", [planning.intitule_cours || planning.teaching_unit]),
            subtitle: `${planning.type} — ${planning.semestre} — ${planning.academic_year}`,
            size: "large",
            fields: [
                {
                    fieldtype: "HTML",
                    fieldname: "info",
                    options: `
                        <div class="frappe-card p-2 mb-2">
                            <span class="text-muted">
                                <strong>${__("Crédits")}:</strong> ${planning.credits || 0} &nbsp;|&nbsp;
                                <strong>${__("Étudiants")}:</strong> ${students.length} &nbsp;|&nbsp;
                                <strong>${__("Type")}:</strong> ${planning.type}
                            </span>
                        </div>
                    `,
                },
                {
                    fieldtype: "HTML",
                    fieldname: "grade_table",
                },
            ],
            primary_action_label: __("Enregistrer les notes"),
            primary_action(values) {
                self._saveGrades(planning, students, dialog, callback);
            },
        });

        dialog.show();

        let tableHtml = self._buildTable(students, isCC, isRattrapage, noteLabel);
        dialog.fields_dict.grade_table.$wrapper.html(tableHtml);

        self._setupTableEvents(dialog);
    },

    _buildTable(students, isCC, isRattrapage, noteLabel) {
        let rows = students.map((s, idx) => {
            let existingNote = isCC ? s.note_cc : (isRattrapage ? s.note_examen_rattrapage : s.note_examen);
            let val = existingNote != null ? existingNote : "";
            let noteBg = existingNote != null ? "style='background:#f0fff4;'" : "";

            return `
                <tr data-student="${s.student}" data-note-entry="${s.note_entry_name || ""}">
                    <td style="padding: 6px; border-bottom: 1px solid #e2e8f0; font-size: 13px;">
                        ${s.matricule || ""}
                    </td>
                    <td style="padding: 6px; border-bottom: 1px solid #e2e8f0; font-size: 13px;">
                        ${s.nom}
                    </td>
                    <td style="padding: 6px; border-bottom: 1px solid #e2e8f0; text-align: center; font-size: 13px;">
                        ${s.credits || 0}
                    </td>
                    <td style="padding: 6px; border-bottom: 1px solid #e2e8f0;">
                        <input type="number" step="0.25" min="0" max="20"
                            class="form-control grade-input"
                            value="${val}"
                            placeholder="0-20"
                            ${noteBg}
                            style="width: 110px; display: inline-block; font-size: 13px;">
                        <span class="note-status text-muted" style="margin-left: 6px; font-size: 11px;">
                            ${existingNote != null ? "✓ saisie" : ""}
                        </span>
                    </td>
                </tr>
            `;
        }).join("");

        return `
            <div style="max-height: 420px; overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 6px;">
                <table style="width: 100%; border-collapse: collapse;">
                    <thead style="background: #f7fafc; position: sticky; top: 0;">
                        <tr>
                            <th style="padding: 8px 6px; text-align: left; border-bottom: 2px solid #e2e8f0;
                                font-size: 12px; text-transform: uppercase; color: #4a5568;">
                                ${__("Matricule")}
                            </th>
                            <th style="padding: 8px 6px; text-align: left; border-bottom: 2px solid #e2e8f0;
                                font-size: 12px; text-transform: uppercase; color: #4a5568;">
                                ${__("Nom")}
                            </th>
                            <th style="padding: 8px 6px; text-align: center; border-bottom: 2px solid #e2e8f0;
                                font-size: 12px; text-transform: uppercase; color: #4a5568;">
                                ${__("Crédit")}
                            </th>
                            <th style="padding: 8px 6px; text-align: left; border-bottom: 2px solid #e2e8f0;
                                font-size: 12px; text-transform: uppercase; color: #4a5568;">
                                ${noteLabel}
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows || `<tr><td colspan="4" style="text-align:center;padding:30px;color:#a0aec0;">
                            ${__("Aucun étudiant")}</td></tr>`}
                    </tbody>
                </table>
            </div>
        `;
    },

    _setupTableEvents(dialog) {
        dialog.$wrapper.find(".grade-input").on("input", function () {
            const val = $(this).val();
            const statusEl = $(this).closest("td").find(".note-status");
            if (val !== "" && parseFloat(val) >= 0 && parseFloat(val) <= 20) {
                statusEl.text("✎ modification").removeClass("text-muted").addClass("text-warning");
            } else {
                statusEl.text("").removeClass("text-warning").addClass("text-muted");
            }
        });
    },

    _saveGrades(planning, students, dialog, callback) {
        const grades = [];
        const $rows = dialog.$wrapper.find("tbody tr");

        $rows.each(function () {
            const student = $(this).data("student");
            const existingName = $(this).data("note-entry") || null;
            const noteVal = $(this).find(".grade-input").val();

            if (noteVal !== undefined && noteVal !== null && noteVal !== "") {
                grades.push({
                    student: student,
                    note: parseFloat(noteVal),
                    note_entry_name: existingName,
                });
            }
        });

        if (grades.length === 0) {
            frappe.msgprint(__("Veuillez saisir au moins une note."));
            return;
        }

        frappe.call({
            method: "udshed.api.planning_grade_entry.save_bulk_grades",
            freeze: true,
            freeze_message: __("Enregistrement et calcul des notes..."),
            args: {
                planning_item_name: planning.name,
                grades: grades,
            },
            callback: (r) => {
                const result = r.message;
                if (result.status === "success" || result.status === "partial") {
                    let msg = __("{0} note(s) enregistrée(s)", [result.created_notes.length]);
                    if (result.errors && result.errors.length > 0) {
                        msg += "<br>" + __("Erreurs : ") + result.errors.join("<br>");
                        frappe.msgprint({
                            title: __("Enregistrement partiel"),
                            indicator: "orange",
                            message: msg,
                        });
                    } else {
                        frappe.show_alert({
                            message: msg,
                            indicator: "green",
                        });
                        frappe.utils.play_sound("submit");
                    }
                    dialog.hide();
                    if (callback) callback(result);
                } else {
                    frappe.msgprint({
                        title: __("Erreur"),
                        indicator: "red",
                        message: result.errors ? result.errors.join("<br>") : __("Échec de l'enregistrement"),
                    });
                }
            },
            error: (err) => {
                frappe.msgprint({
                    title: __("Erreur serveur"),
                    indicator: "red",
                    message: err.message || __("Une erreur est survenue"),
                });
            },
        });
    },
};
