frappe.pages['note-udshed'].on_page_load = function(wrapper) {

	frappe.require([
		'/assets/udshed/css/planning_academique.css',
		'/assets/udshed/js/planning_calendar/dialog_box.js',
		'/assets/udshed/js/planning_calendar/date_utils.js',
		'/assets/udshed/js/planning_calendar/ui.js',
		'/assets/udshed/js/planning_calendar/planning_queries.js',
		'/assets/udshed/js/utils/utils.js',
		'/assets/udshed/js/utils/utils_queries.js',
		'/assets/udshed/js/utils/permission.js',
		'/assets/udshed/js/planning_calendar/grade_entry_dialog.js'
	]).then(async () => {

		// 1. Creation de la page Frappe
		var page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __('Note Udshed — Gestion des Notes'),
			single_column: true
		});

		// 2. Objet filters — meme structure que Planning
		let filters = {
			academic_year: null,
			faculty: null,
			filiere: null,
			niveau: null,
			teacher: null
		};
		let levelMap = {};
		let currentWeekStart = Udshed.DateUtils.getMonday(new Date());
		let defaultPeriods = await Udshed.PlanningQueries.loadCourseDefaultPeriod();
		let periods = [...defaultPeriods];
		let calendar_zone = null;

		// 3. Zone de contenu principal
		let content_zone = $('<div id="note-udshed-content" style="padding: 20px;"></div>');
		let planning_container = $('<div id="note-udshed-planning" class="planning-calendar-wrapper"></div>');
		$(page.body).append(content_zone);
		$(page.body).append(planning_container);

		let monthPicker = null;
		let weekSelect = null;
		let planning_initialized = false;

		function show_empty_state() {
			content_zone.empty();
			planning_container.html(`
				<div class="text-center" style="padding: 60px 20px; color: #8d99a6;">
					<div style="font-size: 48px; margin-bottom: 16px;">📋</div>
					<h4>Selectionnez les filtres pour afficher le planning académique</h4>
					<p>Choisissez une année académique, une filière et un niveau, ou une année et un professeur.</p>
				</div>
			`);
		}

		function init_planning_ui() {
			if (planning_initialized) {
				return;
			}

			planning_container.html(Udshed.UI.show_calendar_hearder());
			calendar_zone = planning_container.find('#planning_calendar .planning-grid');
			monthPicker = document.getElementById('month-picker');
			weekSelect = document.getElementById('week-select');

			Udshed.DateUtils.initMonthPicker(monthPicker);
			Udshed.DateUtils.updateWeekSelect(new Date().getFullYear(), new Date().getMonth(), weekSelect);

			document.getElementById('prev-week').onclick = async () => {
				currentWeekStart.setDate(currentWeekStart.getDate() - 7);
				periods = filters.niveau
					? await Udshed.PlanningQueries.loadCoursePeriod(filters.niveau, currentWeekStart, filters.academic_year)
					: [...defaultPeriods];
				load_note_content(filters);
			};

			document.getElementById('next-week').onclick = async () => {
				currentWeekStart.setDate(currentWeekStart.getDate() + 7);
				periods = filters.niveau
					? await Udshed.PlanningQueries.loadCoursePeriod(filters.niveau, currentWeekStart, filters.academic_year)
					: [...defaultPeriods];
				load_note_content(filters);
			};

			document.getElementById('today-week').onclick = async () => {
				currentWeekStart = Udshed.DateUtils.getMonday(new Date());
				periods = filters.niveau
					? await Udshed.PlanningQueries.loadCoursePeriod(filters.niveau, currentWeekStart, filters.academic_year)
					: [...defaultPeriods];
				load_note_content(filters);
			};

			monthPicker.addEventListener('change', async function() {
				const [year, month] = this.value.split('-').map(Number);
				const weeks = Udshed.DateUtils.getWeeksOfMonth(year, month);
				currentWeekStart = Udshed.DateUtils.getFirstWeekInsideMonth(weeks, year, month);
				periods = filters.niveau
					? await Udshed.PlanningQueries.loadCoursePeriod(filters.niveau, currentWeekStart, filters.academic_year)
					: [...defaultPeriods];
				load_note_content(filters);
			});

			weekSelect.addEventListener('change', async (e) => {
				currentWeekStart = new Date(Number(e.currentTarget.value));
				periods = filters.niveau
					? await Udshed.PlanningQueries.loadCoursePeriod(filters.niveau, currentWeekStart, filters.academic_year)
					: [...defaultPeriods];
				load_note_content(filters);
			});

			planning_initialized = true;
		}

		async function load_note_content(filters) {
			if (!filters.academic_year || (!filters.teacher && (!filters.filiere || !filters.niveau))) {
				show_empty_state();
				return;
			}

			content_zone.empty();
			init_planning_ui();
			Udshed.DateUtils.updateWeekLabel(currentWeekStart);
			Udshed.DateUtils.syncSelectors(weekSelect, monthPicker, currentWeekStart);

			periods = filters.niveau
				? await Udshed.PlanningQueries.loadCoursePeriod(filters.niveau, currentWeekStart, filters.academic_year)
				: [...defaultPeriods];

			Udshed.PlanningQueries.fetchPlanningItems(filters, currentWeekStart, function(items) {
				Udshed.UI.show_calendar(calendar_zone, Udshed.UI.get_grid_calendar_item(items, filters, periods), periods, !!filters.teacher);
			});
		}

		// 4. Barre de filtres — identique a Planning Academique

		// Champ : Annee academique
		page.add_field({
			fieldtype: 'Link',
			label: 'Année académique',
			fieldname: 'academic_year',
			options: 'Academic Year',
			change() {
				filters.academic_year = this.get_value();
				Udshed.Utils.refresh_filter(filters, "academic_year", page, levelMap);
				load_note_content(filters);
			}
		});

		// Champ : Faculte
		const faculty_field = page.add_field({
			fieldtype: 'Link',
			label: 'Faculté',
			fieldname: 'faculty',
			options: 'Faculty',
			change() {
				filters.faculty = this.get_value();
				Udshed.Utils.refresh_filter(filters, "faculty", page, levelMap);
				load_note_content(filters);
			}
		});

		// Champ : Filiere (filtre par faculte selectionnee)
		const filiere_field = page.add_field({
			fieldtype: 'Link',
			label: 'Filière',
			fieldname: 'filiere',
			options: 'Field of study',
			get_query() {
				if (!faculty_field.get_value()) {
					return {};
				}
				return {
					filters: {
						faculte: faculty_field.get_value()
					}
				};
			},
			change() {
				filters.filiere = this.get_value();
				Udshed.Utils.refresh_filter(filters, "filiere", page, levelMap);

				Udshed.UtilsQueries.loadLevels(this.get_value(), niveau_field, (levels) => {
					levelMap = levels ? levels.reduce((acc, curr) => {
						acc[curr.level] = curr.name;
						return acc;
					}, {}) : {};
					niveau_field.df.options = levels
						? levels.map((value) => ({ value: value.level, label: value.level }))
						: [];
					niveau_field.refresh();
				});

			}
		});

		// Champ : Niveau (Select dynamique charge selon la filiere)
		const niveau_field = page.add_field({
			fieldtype: 'Select',
			label: 'Niveau',
			fieldname: 'niveau',
			change() {
				filters.niveau = levelMap[this.get_value()];
				Udshed.Utils.refresh_filter(filters, "niveau", page, levelMap);
				load_note_content(filters);
			}
		});

		// Champ : Professeur
		page.add_field({
			fieldtype: 'Link',
			label: 'Professeur',
			fieldname: 'teacher',
			options: 'Teacher',
			change() {
				filters.teacher = this.get_value();
				Udshed.Utils.refresh_filter(filters, "teacher", page, levelMap);
				load_note_content(filters);
			}
		});

		// 5. Affichage initial
		show_empty_state();

		// 6. Click handler for CC/Exam grade entry
		$(document).on("click", ".planning-cell", function () {
			const courseData = $(this).data("course");
			if (!courseData || !courseData.item) return;

			const itemType = courseData.item.type;
			const isGradeType = itemType && (
				itemType.includes("CC") ||
				itemType === "Controlle Continue (CC)" ||
				itemType.includes("Examen") ||
				itemType.includes("examen") ||
				itemType.includes("rattrapage")
			);

			if (isGradeType) {
				Udshed.GradeEntry.openGradeEntryDialog(courseData, () => {
					load_note_content(filters);
				});
			}
		});

		// 7. Application des permissions utilisateur
		let userContext = null;
		Udshed.UtilsQueries.get_data_of_user((data) => {
			userContext = Udshed.Perms.normalizeUserContext(data);

			if (Udshed.Perms.should_apply_filter(userContext)) {
				page.fields_dict.academic_year.get_query = () => ({
					filters: {
						name: ["in", userContext.academic_year]
					}
				});
			}

			if (userContext.default_academic_year) {
				page.fields_dict.academic_year.set_value(userContext.default_academic_year);
				filters.academic_year = userContext.default_academic_year;
			}

			if (userContext.faculty.length > 0) {
				page.fields_dict.faculty.set_value(userContext.faculty[0]);
				filters.faculty = userContext.faculty[0];
			}

			if (userContext.filiere.length > 0) {
				filters.filiere = userContext.filiere[0];
				page.fields_dict.filiere.set_value(userContext.filiere[0]);
				Udshed.UtilsQueries.loadLevels(filters.filiere, page.fields_dict.niveau, (levels) => {
					levelMap = levels ? levels.reduce((acc, curr) => {
						acc[curr.level] = curr.name;
						return acc;
					}, {}) : {};
					page.fields_dict.niveau.df.options = levels
						? levels.map((value) => ({ value: value.level, label: value.level }))
						: [];
					page.fields_dict.niveau.refresh();
				});
			}

			load_note_content(filters);
		});

	});
};
