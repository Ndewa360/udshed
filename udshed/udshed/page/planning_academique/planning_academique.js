
frappe.pages['planning-academique'].on_page_load = function(wrapper) {
	
	frappe.require([
		'/assets/udshed/css/planning_academique.css',
		'/assets/udshed/js/planning_calendar/dialog_box.js',
		'/assets/udshed/js/planning_calendar/date_utils.js',
		'/assets/udshed/js/utils/utils.js', 
		'/assets/udshed/js/planning_calendar/planning_queries.js',
		'/assets/udshed/js/utils/utils_queries.js',
		'/assets/udshed/js/planning_calendar/ui.js',
		'/assets/udshed/js/utils/permission.js',
		'/assets/udshed/js/planning_calendar/grade_entry_dialog.js'
	]).then(async () => {


		var currentWeekStart = Udshed.DateUtils.getMonday(new Date());
		let page = frappe.ui.make_app_page({
			parent: wrapper,
			title: 'Planning',
			single_column: true
		});

		async function loadPlanning(weekSelect,monthPicker,filters,calendar_zone,periods) {
			Udshed.DateUtils.updateWeekLabel(currentWeekStart);
			Udshed.DateUtils.syncSelectors(weekSelect,monthPicker,currentWeekStart);
			
			Udshed.PlanningQueries.fetchPlanningItems(filters,currentWeekStart,function (items){
				Udshed.UI.show_calendar(calendar_zone, Udshed.UI.get_grid_calendar_item(items,filters,periods),periods,filters.teacher?true:false)
			});
		}

		function update_exam_label(currentWeekStart,filters,page)
		{
			if(!filters.niveau || !filters.academic_year) return;
			Udshed.PlanningQueries.getPlanningType(filters.niveau,currentWeekStart,filters.academic_year,(planning_type)=>{
				if(planning_type=="Examen") {
					page.set_indicator('Session d\'examen', 'orange')
				} 
				else
				{
					page.clear_indicator()
				}
			})
		}

		let filters = {
			academic_year: null,
			faculty: null,
			filiere: null,
			niveau: null,
			teacher: null
		};

		let levelMap = {}; // label => name

		let defaultPeriods = await Udshed.PlanningQueries.loadCourseDefaultPeriod()
		let periods = [...defaultPeriods]


		let grid_wrapper = $('<div id="planning-grid-wrapper"></div>');
		$(wrapper).append(grid_wrapper);

		// afficher la grille vide au chargement
		grid_wrapper.html(Udshed.UI.show_calendar_hearder());
		calendar_zone = grid_wrapper.find("#planning_calendar .planning-grid");
		Udshed.UI.show_calendar(calendar_zone,Udshed.Utils.initDataPeriodForUi(periods),periods);

		const monthPicker = document.getElementById("month-picker");
		const weekSelect = document.getElementById("week-select");
		
		let btnEporterPDF =  page.set_primary_action('Exporter en PDF', () => {
			if(Udshed.Utils.isValidFecthDataFilter(filters))
			{
				let url = `/api/method/udshed.www.planning_pdf.download_planning_pdf?filters=${encodeURIComponent(JSON.stringify({...filters,week_start:frappe.datetime.obj_to_str(currentWeekStart)}))}`;
				window.open(url);
			}
		});

		let btnEnvoiMail =  page.set_secondary_action("Envoyer par mail", () => {
			Udshed.Dialogs.openSendPlanningDialog({...filters,week_start:frappe.datetime.obj_to_str(currentWeekStart)},null,()=>{})
			
		}); 

		// get_data_of_user();

		page.add_field({
			fieldtype: 'Link',
			label: 'Année académique',
			fieldname: 'academic_year',
			options: 'Academic Year',
			change() {
				filters.academic_year = this.get_value();
				Udshed.Utils.refresh_filter(filters,"academic_year",page,levelMap);
				Udshed.UI.update_page_actions(filters, btnEporterPDF,btnEnvoiMail)
				periods = [...defaultPeriods]
				// show_calendar(filters);
			}
		});

		const faculty_field = page.add_field({
			fieldtype: 'Link',
			label: 'Faculté',
			fieldname: 'faculty',
			options: 'Faculty',
			change() {				
				filters.faculty = this.get_value();
				Udshed.Utils.refresh_filter(filters,"faculty",page,levelMap);
				periods = [...defaultPeriods]
				Udshed.UI.update_page_actions(filters, btnEporterPDF,btnEnvoiMail)
			}
		});

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
				Udshed.Utils.refresh_filter(filters,"filiere",page,levelMap);

				Udshed.UtilsQueries.loadLevels(this.get_value(),niveau_field,(levels)=>{
					levelMap = levels ? levels.reduce((acc, curr) => {
						acc[curr.level] = curr.name;
						return acc;
					}, {}) : {};
					niveau_field.df.options = levels ? levels.map((value)=>({value:value.level,name:value.name})) || [] : [];
					niveau_field.refresh();
				});
				periods = [...defaultPeriods]
				Udshed.UI.update_page_actions(filters, btnEporterPDF,btnEnvoiMail)
				
			}
		});

		const niveau_field = page.add_field({
			fieldtype: 'Select',
			label: 'Niveau',
			fieldname: 'niveau',
			async change() {
				filters.niveau = levelMap[this.get_value()];
				periods = this.get_value()==null ? [...defaultPeriods]: await Udshed.PlanningQueries.loadCoursePeriod(filters.niveau,currentWeekStart,filters.academic_year)
				loadPlanning(weekSelect,monthPicker,filters,calendar_zone,periods);
				update_exam_label(currentWeekStart,filters,page)
				Udshed.UI.update_page_actions(filters, btnEporterPDF,btnEnvoiMail)
			}
		});
		const teacher_field = page.add_field({
			fieldtype: 'Link',
			label: 'Teacher',
			fieldname: 'teacher',
			options: 'Teacher',
			change() {
				console.log("Teacher changed", this.get_value())
				if(!this.get_value()) return

				filters.teacher = this.get_value()
				loadPlanning(weekSelect,monthPicker,filters,calendar_zone,periods);
				update_exam_label(currentWeekStart,filters,page)
				Udshed.UI.update_page_actions(filters, btnEporterPDF,btnEnvoiMail)
			}
		});

		document.getElementById("prev-week").onclick = async () => {
			console.log("Niveau selected:", niveau_field.get_value());
			currentWeekStart.setDate(currentWeekStart.getDate() - 7);
			periods = niveau_field.get_value()==null ? [...defaultPeriods]: await Udshed.PlanningQueries.loadCoursePeriod(filters.niveau,currentWeekStart,filters.academic_year)
			loadPlanning(weekSelect,monthPicker,filters,calendar_zone,periods);
			update_exam_label(currentWeekStart,filters,page)
		};

		document.getElementById("next-week").onclick = async () => {
			currentWeekStart.setDate(currentWeekStart.getDate() + 7);
			periods = niveau_field.get_value()==null ? [...defaultPeriods]: await Udshed.PlanningQueries.loadCoursePeriod(filters.niveau,currentWeekStart,filters.academic_year)
			loadPlanning(weekSelect,monthPicker,filters,calendar_zone,periods);
			update_exam_label(currentWeekStart,filters,page)
		};

		document.getElementById("today-week").onclick = async () => {
			currentWeekStart = Udshed.DateUtils.getMonday(new Date());
			periods = niveau_field.get_value()==null ? [...defaultPeriods]: await Udshed.PlanningQueries.loadCoursePeriod(filters.niveau,currentWeekStart,filters.academic_year)
			loadPlanning(weekSelect,monthPicker,filters,calendar_zone,periods);
			update_exam_label(currentWeekStart,filters,page)
		};

	
		monthPicker.addEventListener("change", async function () {
			const [year, month] = this.value.split("-").map(Number);
			Udshed.DateUtils.updateWeekSelect(year, month,weekSelect);

			// 🔑 On force la 1ère semaine visible du mois
			const weeks = Udshed.DateUtils.getWeeksOfMonth(year, month);
			currentWeekStart = Udshed.DateUtils.getFirstWeekInsideMonth(weeks, year, month);
			periods = niveau_field.get_value()==null ? [...defaultPeriods]: await Udshed.PlanningQueries.loadCoursePeriod(filters.niveau,currentWeekStart,filters.academic_year)
			
			loadPlanning(weekSelect,monthPicker,filters,calendar_zone,periods);
			update_exam_label(currentWeekStart,filters,page)
		});

		weekSelect.addEventListener("change", async (e) => {
			currentWeekStart = new Date(Number(e.currentTarget.value));
			periods = niveau_field.get_value()==null ? [...defaultPeriods]: await Udshed.PlanningQueries.loadCoursePeriod(filters.niveau,currentWeekStart,filters.academic_year)
			loadPlanning(weekSelect,monthPicker,filters,calendar_zone,periods);
			update_exam_label(currentWeekStart,filters,page)
		});


		Udshed.DateUtils.initMonthPicker(monthPicker);
		Udshed.DateUtils.updateWeekSelect(new Date().getFullYear(), new Date().getMonth(),weekSelect);
		
		loadPlanning(weekSelect,monthPicker,filters,calendar_zone,periods);
		Udshed.Utils.refresh_filter(filters,null,page,levelMap);
		Udshed.UI.update_page_actions(filters, btnEporterPDF,btnEnvoiMail)

		let userContext = null;
		Udshed.UtilsQueries.get_data_of_user((data) => {
			userContext = Udshed.Perms.normalizeUserContext(data);
			
			if(Udshed.Perms.should_apply_filter(userContext))
			{
				//Apply filters
				//academic_year
				page.fields_dict.academic_year.get_query = () => ({
					filters: {
						name: ["in", userContext.academic_year]
					}
				});
				
				
				//faculty
				// page.fields_dict.faculty.get_query = () => ({
				// 	filters: {
				// 		name: ["in", userContext.faculty]
				// 	}
				// });

				//filiere
				// page.fields_dict.filiere.get_query = () => {
				// 	let f = faculty_field.get_value();
				// 	return {
				// 		filters: {
				// 			name: ["in", userContext.filiere],
				// 			...(f ? { faculte: f } : {})
				// 		}
				// 	};
				// };


				// const allowedNiveau = new Set(userContext.niveau);

				// niveau_field.df.options = niveau_field.df.options.filter(o =>
				// 	allowedNiveau.has(levelMap[o.value])
				// );
				// niveau_field.refresh();
			}
			
			//Apply default value
			if(userContext.default_academic_year) {
				page.fields_dict.academic_year.set_value(userContext.default_academic_year);
				filters.academic_year = userContext.default_academic_year;
			}

			if(userContext.faculty.length > 0) {
				page.fields_dict.faculty.set_value(userContext.faculty[0])
				filters.faculty = userContext.faculty[0];
			}
			// if (userContext.locks.faculty ) page.fields_dict.faculty.$input.prop("disabled", true);


			
			if(userContext.filiere.length > 0) {
				filters.filiere = userContext.filiere[0]
				page.fields_dict.filiere.set_value(userContext.filiere[0])
			}
			// if (userContext.locks.fileire ) page.fields_dict.filiere.$input.prop("disabled", true);
			
		});

		// Evenement sur les celuules de planning
		

		$(document).on("click", ".planning-cell", function () {

			//on se rassure qu'il a les droits de motifications
			if(!Udshed.Perms.user_can_edit_planning_cell(filters,userContext)) {
				frappe.utils.play_sound("click");
				return
			};

			currentDay = new Date(parseInt(weekSelect.value)); // Récupérer la date de la semaine sélectionnée
			let day ={ "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4,"Saturday": 5}
			currentDay.setDate(currentDay.getDate() + day[($(this).data("day"))]);
			const half = $(this).data("half");
			const halfLibelle = $(this).data("half-libelle");
			const courseData = $(this).data("course");

			if (courseData) {
				const itemType = courseData.item && courseData.item.type;
				const isGradeType = itemType && (
					itemType.includes("CC") || 
					itemType === "Controlle Continue (CC)" ||
					itemType.includes("Examen") || 
					itemType.includes("examen") ||
					itemType.includes("rattrapage")
				);

				if (isGradeType) {
					Udshed.GradeEntry.openGradeEntryDialog(courseData, () => {
						loadPlanning(weekSelect,monthPicker,filters,calendar_zone,periods)
					});
				} else {
					Udshed.Dialogs.openEditPlanningDialog(filters,currentDay,half,halfLibelle,courseData,userContext,() => {
						loadPlanning(weekSelect,monthPicker,filters,calendar_zone,periods)
					});
				}
			} else {
				Udshed.Dialogs.openCreatePlanningDialog(filters,currentDay,half,halfLibelle,userContext, () => {
					loadPlanning(weekSelect,monthPicker,filters,calendar_zone,periods)
				});
			}
		});	
	})

};








