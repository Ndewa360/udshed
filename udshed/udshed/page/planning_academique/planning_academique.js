frappe.pages["planning-academique"].on_page_load = function (wrapper) {
    frappe.require([
        "/assets/udshed/css/planning_academique.css",
        "/assets/udshed/js/planning_calendar/dialog_box.js",
        "/assets/udshed/js/planning_calendar/date_utils.js",
        "/assets/udshed/js/utils/utils.js",
        "/assets/udshed/js/planning_calendar/planning_queries.js",
        "/assets/udshed/js/utils/utils_queries.js",
        "/assets/udshed/js/planning_calendar/ui.js",
        "/assets/udshed/js/utils/permission.js"
    ]).then(async () => {
        const rawUserContext = await Udshed.UtilsQueries.get_data_of_user();
        const userContext = Udshed.Perms.normalizeUserContext(rawUserContext);
        const canPlan = Udshed.Perms.user_can_edit_planning_cell(
            { academic_year: null, faculty: null, filiere: null, niveau: null },
            userContext
        );

        let currentWeekStart = Udshed.DateUtils.getMonday(new Date());
        const page = frappe.ui.make_app_page({
            parent: wrapper,
            title: "Planning",
            single_column: true
        });

        let filters = {
            academic_year: userContext.default_academic_year || null,
            faculty: userContext.faculty.length === 1 ? userContext.faculty[0] : null,
            filiere: userContext.filiere.length === 1 ? userContext.filiere[0] : null,
            niveau: userContext.niveau.length === 1 ? userContext.niveau[0] : null,
            teacher: null
        };
        if (!canPlan && userContext.teacher) filters.teacher = userContext.teacher;

        let levelMap = {};
        let initializing = true;
        const defaultPeriods = await Udshed.PlanningQueries.loadCourseDefaultPeriod();
        let periods = [...defaultPeriods];
        let loading = false;

        const grid_wrapper = $('<div id="planning-grid-wrapper"></div>');
        $(wrapper).append(grid_wrapper);
        grid_wrapper.html(Udshed.UI.show_calendar_hearder());
        const calendar_zone = grid_wrapper.find("#planning_calendar .planning-grid");
        const monthPicker = grid_wrapper.find("#month-picker")[0];
        const weekSelect = grid_wrapper.find("#week-select")[0];

        async function resolvePeriods() {
            if (filters.niveau && filters.academic_year) {
                const loaded = await Udshed.PlanningQueries.loadCoursePeriod(
                    filters.niveau, currentWeekStart, filters.academic_year
                );
                if (loaded && loaded.length) return loaded;
            }
            return [...defaultPeriods];
        }

        async function loadPlanning() {
            if (loading) return;
            loading = true;
            try {
                periods = await resolvePeriods();
                Udshed.DateUtils.updateWeekLabel(currentWeekStart);
                Udshed.DateUtils.syncSelectors(weekSelect, monthPicker, currentWeekStart);
                const items = await Udshed.PlanningQueries.fetchPlanningItems(filters, currentWeekStart);
                const grid = Udshed.UI.get_grid_calendar_item(items, filters, periods);
                Udshed.UI.show_calendar(calendar_zone, grid, periods, Boolean(filters.teacher), filters, userContext);
            } finally {
                loading = false;
            }
        }

        async function updateExamLabel() {
            if (!filters.niveau || !filters.academic_year) {
                page.clear_indicator();
                return;
            }
            const planningType = await Udshed.PlanningQueries.getPlanningType(
                filters.niveau, currentWeekStart, filters.academic_year
            );
            if (planningType === "Examen") page.set_indicator("Session d'examen", "orange");
            else page.clear_indicator();
        }

        async function refreshAll() {
            if (initializing) return;
            Udshed.UI.update_page_actions(filters, btnExportPDF, btnEnvoiMail);
            await loadPlanning();
            await updateExamLabel();
        }

        function applyUserRestrictions() {
            if (Udshed.Perms.is_admin(userContext)) return;
            if (userContext.academic_year.length) {
                page.fields_dict.academic_year.get_query = () => ({ filters: { name: ["in", userContext.academic_year] } });
            }
            if (userContext.faculty.length) {
                page.fields_dict.faculty.get_query = () => ({ filters: { name: ["in", userContext.faculty] } });
            }
            if (userContext.filiere.length) {
                page.fields_dict.filiere.get_query = () => ({ filters: { name: ["in", userContext.filiere] } });
            }
            if (userContext.teacher && !canPlan) {
                page.fields_dict.teacher.set_value(userContext.teacher);
                page.fields_dict.teacher.$input.prop("disabled", true);
            }
            if (canPlan) {
                ["academic_year", "faculty", "filiere", "niveau"].forEach((name) => {
                    if (filters[name]) page.fields_dict[name].$input.prop("disabled", true);
                });
            }
        }

        let btnExportPDF = page.set_primary_action("Exporter en PDF", () => {
            if (!Udshed.Utils.isValidFecthDataFilter(filters)) return;
            const params = encodeURIComponent(JSON.stringify({
                ...filters,
                week_start: frappe.datetime.obj_to_str(currentWeekStart)
            }));
            window.open(`/api/method/udshed.www.planning_pdf.download_planning_pdf?filters=${params}`);
        });

        let btnEnvoiMail = page.set_secondary_action("Envoyer par mail", () => {
            Udshed.Dialogs.openSendPlanningDialog(
                { ...filters, week_start: frappe.datetime.obj_to_str(currentWeekStart) },
                userContext,
                () => {}
            );
        });

        page.add_field({
            fieldtype: "Link",
            label: "Année académique",
            fieldname: "academic_year",
            options: "Academic Year",
            default: filters.academic_year,
            change() {
                filters.academic_year = this.get_value();
                Udshed.Utils.refresh_filter(filters, "academic_year", page, levelMap);
                filters.faculty = null;
                filters.filiere = null;
                filters.niveau = null;
                refreshAll();
            }
        });

        const faculty_field = page.add_field({
            fieldtype: "Link",
            label: "Faculté",
            fieldname: "faculty",
            options: "Faculty",
            default: filters.faculty,
            change() {
                filters.faculty = this.get_value();
                Udshed.Utils.refresh_filter(filters, "faculty", page, levelMap);
                filters.filiere = null;
                filters.niveau = null;
                refreshAll();
            }
        });

        const filiere_field = page.add_field({
            fieldtype: "Link",
            label: "Filière",
            fieldname: "filiere",
            options: "Field of study",
            default: filters.filiere,
            get_query() {
                if (!faculty_field.get_value()) return {};
                return { filters: { faculte: faculty_field.get_value() } };
            },
            async change() {
                filters.filiere = this.get_value();
                Udshed.Utils.refresh_filter(filters, "filiere", page, levelMap);
                filters.niveau = null;
                const levels = await Udshed.UtilsQueries.loadLevels(filters.filiere, niveau_field);
                levelMap = (levels || []).reduce((acc, curr) => {
                    acc[curr.level] = curr.name;
                    return acc;
                }, {});
                niveau_field.df.options = (levels || []).map((level) => ({ value: level.name, name: level.level }));
                niveau_field.refresh();
                refreshAll();
            }
        });

        const niveau_field = page.add_field({
            fieldtype: "Select",
            label: "Niveau",
            fieldname: "niveau",
            async change() {
                filters.niveau = this.get_value() || null;
                refreshAll();
            }
        });

        page.add_field({
            fieldtype: "Link",
            label: "Enseignant",
            fieldname: "teacher",
            options: "Teacher",
            default: filters.teacher,
            change() {
                filters.teacher = this.get_value() || null;
                refreshAll();
            }
        });

        if (filters.filiere) {
            const levels = await Udshed.UtilsQueries.loadLevels(filters.filiere, niveau_field);
            levelMap = (levels || []).reduce((acc, curr) => {
                acc[curr.level] = curr.name;
                return acc;
            }, {});
            niveau_field.df.options = (levels || []).map((level) => ({ value: level.name, name: level.level }));
            if (filters.niveau) niveau_field.set_value(filters.niveau);
            niveau_field.refresh();
        }

        applyUserRestrictions();
        Udshed.DateUtils.initMonthPicker(monthPicker);
        Udshed.DateUtils.syncSelectors(weekSelect, monthPicker, currentWeekStart);
        initializing = false;
        await refreshAll();

        grid_wrapper.on("click", "#prev-week", async () => {
            currentWeekStart.setDate(currentWeekStart.getDate() - 7);
            await refreshAll();
        });
        grid_wrapper.on("click", "#next-week", async () => {
            currentWeekStart.setDate(currentWeekStart.getDate() + 7);
            await refreshAll();
        });
        grid_wrapper.on("click", "#today-week", async () => {
            currentWeekStart = Udshed.DateUtils.getMonday(new Date());
            await refreshAll();
        });
        grid_wrapper.on("change", "#month-picker", async function () {
            const [year, month] = this.value.split("-").map(Number);
            const weeks = Udshed.DateUtils.getWeeksOfMonth(year, month);
            currentWeekStart = Udshed.DateUtils.getFirstWeekInsideMonth(weeks, year, month);
            await refreshAll();
        });
        grid_wrapper.on("change", "#week-select", async function () {
            const value = Number(this.value);
            if (Number.isFinite(value)) currentWeekStart = new Date(value);
            await refreshAll();
        });
        grid_wrapper.on("click", ".planning-cell", function (event) {
            if (!Udshed.Perms.user_can_edit_planning_cell(filters, userContext)) {
                frappe.show_alert({ message: __("Vous n'avez pas le droit de modifier ce créneau."), indicator: "red" });
                return;
            }
            const day = { Monday: 0, Tuesday: 1, Wednesday: 2, Thursday: 3, Friday: 4, Saturday: 5 }[$(this).data("day")];
            const cellDate = new Date(currentWeekStart);
            cellDate.setDate(cellDate.getDate() + day);
            const half = $(this).data("half");
            const halfLibelle = $(this).data("half-libelle");
            const selectedItem = $(event.target).closest(".planning-item");
            const courseData = selectedItem.length ? selectedItem.data("course") : $(this).data("course");
            if (courseData && courseData.item && courseData.item.name) {
                Udshed.Dialogs.openEditPlanningDialog(filters, cellDate, half, halfLibelle, courseData, userContext, refreshAll);
            } else {
                Udshed.Dialogs.openCreatePlanningDialog(filters, cellDate, half, halfLibelle, userContext, refreshAll);
            }
        });
    });
};
