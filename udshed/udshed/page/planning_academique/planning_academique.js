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
        const canPlan = Udshed.Perms.user_can_plan(userContext);
        const defaultScope = Udshed.Perms.default_planning_scope(userContext);

        let currentWeekStart = Udshed.DateUtils.getMonday(new Date());
        const page = frappe.ui.make_app_page({
            parent: wrapper,
            title: "Planning",
            single_column: true
        });

        let filters = {
            academic_year: defaultScope.academic_year || null,
            faculty: defaultScope.faculty || null,
            filiere: defaultScope.filiere || null,
            niveau: defaultScope.niveau || null,
            teacher: defaultScope.teacher || null
        };
        if (!canPlan && !filters.teacher && userContext.teacher) filters.teacher = userContext.teacher;

        let levelMap = {};
        let academicYearMonths = [];
        let initializing = true;
        let filterRequest = 0;
        const defaultPeriods = await Udshed.PlanningQueries.loadCourseDefaultPeriod();
        let periods = [...defaultPeriods];

        const grid_wrapper = $('<div id="planning-grid-wrapper"></div>');
        $(wrapper).append(grid_wrapper);
        grid_wrapper.html(Udshed.UI.show_calendar_hearder());
        $('<div id="planning-filter-hint" class="planning-filter-hint"></div>').prependTo(grid_wrapper);
        const filterHint = grid_wrapper.find("#planning-filter-hint");
        const calendar_zone = grid_wrapper.find("#planning_calendar .planning-grid");
        const monthPicker = grid_wrapper.find("#month-picker")[0];
        const weekSelect = grid_wrapper.find("#week-select")[0];

        function set_control_value(name, value) {
            const control = page.fields_dict[name];
            if (!control) return;
            filters[name] = value || null;
            if (control.get_value && control.get_value() !== filters[name]) control.set_value(filters[name]);
        }

        function clear_control_options(name) {
            const control = page.fields_dict[name];
            if (!control || !control.df) return;
            control.df.options = [];
            if (control.refresh) control.refresh();
        }

        function clear_class_filters() {
            const previous = page._planning_filter_sync;
            page._planning_filter_sync = true;
            try {
                set_control_value("filiere", null);
                set_control_value("niveau", null);
                clear_control_options("niveau");
                levelMap = {};
            } finally {
                page._planning_filter_sync = previous;
            }
        }

        function clear_teacher_filter() {
            const previous = page._planning_filter_sync;
            page._planning_filter_sync = true;
            try {
                set_control_value("teacher", null);
            } finally {
                page._planning_filter_sync = previous;
            }
        }

        function apply_level_options(levels) {
            const allowed = canPlan
                ? Udshed.Perms.allowed_levels_for_filiere(userContext, filters.filiere)
                : userContext.niveau;
            const visible = allowed.length
                ? (levels || []).filter((level) => allowed.includes(String(level.name)))
                : (levels || []);
            levelMap = visible.reduce((acc, curr) => {
                acc[curr.level] = curr.name;
                return acc;
            }, {});
            clear_control_options("niveau");
            page.fields_dict.niveau.df.options = visible.map((level) => ({ value: level.name, label: level.level }));
            if (filters.niveau && !visible.some((level) => String(level.name) === String(filters.niveau))) {
                filters.niveau = null;
            }
            page.fields_dict.niveau.refresh();
            if (filters.niveau) page.fields_dict.niveau.set_value(filters.niveau);
        }

        async function resolvePeriods() {
            if (filters.niveau && filters.academic_year) {
                const loaded = await Udshed.PlanningQueries.loadCoursePeriod(
                    filters.niveau, currentWeekStart, filters.academic_year
                );
                if (loaded && loaded.length) return loaded;
            }
            return [...defaultPeriods];
        }

        async function loadPlanning(request) {
            periods = await resolvePeriods();
            if (request !== filterRequest) return;
            currentWeekStart = Udshed.DateUtils.syncSelectors(weekSelect, monthPicker, currentWeekStart, academicYearMonths);
            Udshed.DateUtils.updateWeekLabel(currentWeekStart);
            const items = await Udshed.PlanningQueries.fetchPlanningItems(filters, currentWeekStart);
            if (request !== filterRequest) return;
            Udshed.UI.show_calendar(calendar_zone, Udshed.UI.get_grid_calendar_item(items, filters, periods), periods, Boolean(filters.teacher), filters, userContext);
        }

        async function updateExamLabel(request) {
            if (!filters.niveau || !filters.academic_year) {
                page.clear_indicator();
                return;
            }
            const planningType = await Udshed.PlanningQueries.getPlanningType(
                filters.niveau, currentWeekStart, filters.academic_year
            );
            if (request !== filterRequest) return;
            if (planningType === "Examen") page.set_indicator("Session d'examen", "orange");
            else page.clear_indicator();
        }

        function updateFilterHint() {
            if (Udshed.Utils.isValidFecthDataFilter(filters)) {
                filterHint.empty();
                return;
            }
            const message = canPlan
                ? "Sélectionnez une filière et un niveau, ou un enseignant, pour afficher le planning."
                : "Sélectionnez un enseignant pour afficher votre planning.";
            filterHint.html(`<div class="planning-filter-hint-text">${message}</div>`);
        }

        async function updateAcademicYearMonths() {
            academicYearMonths = await Udshed.PlanningQueries.loadAcademicYearMonths(filters.academic_year);
            Udshed.DateUtils.initMonthPicker(monthPicker, academicYearMonths);
            currentWeekStart = Udshed.DateUtils.clampWeekStart(currentWeekStart, academicYearMonths);
            Udshed.DateUtils.syncSelectors(weekSelect, monthPicker, currentWeekStart, academicYearMonths);
        }

        async function refreshAll() {
            if (initializing) return;
            const request = ++filterRequest;
            updateFilterHint();
            Udshed.UI.update_page_actions(filters, btnExportPDF, btnEnvoiMail);
            await loadPlanning(request);
            await updateExamLabel(request);
        }

        function applyUserRestrictions() {
            if (Udshed.Perms.is_admin(userContext)) return;
            const academicYearQuery = userContext.academic_year.length
                ? () => ({ filters: { name: ["in", userContext.academic_year] } })
                : undefined;
            const facultyQuery = userContext.faculty.length
                ? () => ({ filters: { name: ["in", userContext.faculty] } })
                : undefined;
            const filiereQuery = () => {
                const scoped = { name: ["in", userContext.filiere] };
                const faculty = faculty_field.get_value();
                if (faculty) scoped.faculte = faculty;
                return { filters: scoped };
            };
            page.fields_dict.academic_year.get_query = Udshed.Perms.combine_get_query(page.fields_dict.academic_year.get_query, academicYearQuery);
            page.fields_dict.faculty.get_query = Udshed.Perms.combine_get_query(page.fields_dict.faculty.get_query, facultyQuery);
            page.fields_dict.filiere.get_query = Udshed.Perms.combine_get_query(page.fields_dict.filiere.get_query, filiereQuery);
            if (!canPlan && userContext.teacher) page.fields_dict.teacher.$input.prop("disabled", true);
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
            if (!Udshed.Utils.isValidFecthDataFilter(filters)) return;
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
            async change() {
                if (page._planning_filter_sync) return;
                filters.academic_year = this.get_value() || null;
                Udshed.Utils.refresh_filter(filters, "academic_year", page, levelMap);
                await updateAcademicYearMonths();
                await refreshAll();
            }
        });

        const faculty_field = page.add_field({
            fieldtype: "Link",
            label: "Faculté",
            fieldname: "faculty",
            options: "Faculty",
            default: filters.faculty,
            change() {
                if (page._planning_filter_sync) return;
                filters.faculty = this.get_value() || null;
                Udshed.Utils.refresh_filter(filters, "faculty", page, levelMap);
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
                if (page._planning_filter_sync) return;
                filters.filiere = this.get_value() || null;
                Udshed.Utils.refresh_filter(filters, "filiere", page, levelMap);
                clear_teacher_filter();
                if (!filters.filiere) {
                    apply_level_options([]);
                    refreshAll();
                    return;
                }
                const levels = await Udshed.UtilsQueries.loadLevels(filters.filiere, niveau_field);
                apply_level_options(levels);
                refreshAll();
            }
        });

        const niveau_field = page.add_field({
            fieldtype: "Select",
            label: "Niveau",
            fieldname: "niveau",
            change() {
                if (page._planning_filter_sync) return;
                filters.niveau = this.get_value() || null;
                if (filters.niveau) clear_teacher_filter();
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
                if (page._planning_filter_sync) return;
                filters.teacher = this.get_value() || null;
                if (filters.teacher) clear_class_filters();
                refreshAll();
            }
        });

        if (filters.filiere) {
            const levels = await Udshed.UtilsQueries.loadLevels(filters.filiere, niveau_field);
            apply_level_options(levels);
        } else {
            apply_level_options([]);
        }

        applyUserRestrictions();
        await updateAcademicYearMonths();
        initializing = false;
        await refreshAll();

        grid_wrapper.on("click", "#prev-week", async () => {
            currentWeekStart = Udshed.DateUtils.clampWeekStart(
                Udshed.DateUtils.addDays(currentWeekStart, -7),
                academicYearMonths
            );
            await refreshAll();
        });
        grid_wrapper.on("click", "#next-week", async () => {
            currentWeekStart = Udshed.DateUtils.clampWeekStart(
                Udshed.DateUtils.addDays(currentWeekStart, 7),
                academicYearMonths
            );
            await refreshAll();
        });
        grid_wrapper.on("click", "#today-week", async () => {
            currentWeekStart = Udshed.DateUtils.clampWeekStart(
                Udshed.DateUtils.getMonday(new Date()),
                academicYearMonths
            );
            await refreshAll();
        });
        grid_wrapper.on("change", "#month-picker", async function () {
            const selectedMonth = Udshed.DateUtils.parseMonthValue(this.value);
            if (!selectedMonth) return;
            currentWeekStart = Udshed.DateUtils.getFirstWeekInsideMonth(selectedMonth.year, selectedMonth.month);
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
