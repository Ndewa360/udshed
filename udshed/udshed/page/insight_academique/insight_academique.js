frappe.pages['insight-academique'].on_page_load = function(wrapper) {

	frappe.require([
		'/assets/udshed/css/insight.css',
		'/assets/udshed/js/utils/utils.js', 
		'/assets/udshed/js/utils/utils_queries.js',
		'/assets/udshed/js/insight/academic/year_insight.js',
		'/assets/udshed/js/insight/academic/faculte_insight.js',
		'/assets/udshed/js/insight/academic/fieldofstudy_insight.js',
		'/assets/udshed/js/insight/academic/fieldofstudylevel_insight.js',
		'/assets/udshed/js/insight/academic/teacher_insight.js',
		'/assets/udshed/js/insight/academic/queries.js',
		'/assets/udshed/js/insight/ui/ui.js',
		'/assets/udshed/js/utils/permission.js'
	]).then(async () => {
		// frappe.workspace.show("Insight");
		frappe.set_route("insight-academique", {
			sidebar: "insight"
		})
	var page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __('Suivi des Cours'),
            single_column: true
        });
        
        let filters = {
			academic_year: null,
			faculty: null,
			filiere: null,
			niveau: null,
			semestre:null,
			teacher: null
		};

        let levelMap = {}; // label => name

        page.set_primary_action("Exporter Excel", () => {
			
		},'octicon octicon-plus');

        $(`
			<div id="academic-insight-page">
                <div id="loading" class="text-center py-5" style="display: none;">
                    <div class="spinner-border text-primary" role="status">
                        <span class="sr-only">${ __("Chargement...") }</span>
                    </div>
                </div>

                <!-- Dashboard Content -->
                <div id="dashboard-content">
                    <!-- Cette section sera dynamiquement remplie par JavaScript -->
                </div>
            </div>
		`).appendTo(wrapper);

        // Charger le contenu
        const content = $(wrapper).find('#dashboard-content');
        
        page.add_field({
			fieldtype: 'Link',
			label: 'Année académique',
			fieldname: 'academic_year',
			options: 'Academic Year',
			change(e) {
				filters.academic_year = this.get_value();
				Udshed.Utils.refresh_filter(filters,"academic_year",page,levelMap);
                if(!this.get_value()) return;
				show_dashboard(page,filters,{container:content})
			}
		});

		const faculty_field = page.add_field({
			fieldtype: 'Link',
			label: 'Faculté',
			fieldname: 'faculty',
			options: 'Faculty',
			change(e) {
				filters.faculty = this.get_value();
				Udshed.Utils.refresh_filter(filters,"faculty",page,levelMap);
                if(!this.get_value()) return;
				show_dashboard(page,filters,{container:content})
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
					niveau_field.df.options = levels ? levels.map((value)=>({value:value.name,label:value.level})) || [] : [];
					niveau_field.refresh();
				});
				// periods = [...defaultPeriods]
				if(!this.get_value()) return
				show_dashboard(page,filters,{container:content})
				// Udshed.UI.update_page_actions(filters, btnEporterPDF,btnEnvoiMail)
				
			}
		});        

        const niveau_field = page.add_field({
			fieldtype: 'Select',
			label: 'Niveau',
			fieldname: 'niveau',
			change() {
				filters.niveau = this.get_value() || null;
				if(!this.get_value()) return
				// periods = this.get_value()==null ? [...defaultPeriods]: await Udshed.Queries.loadCoursePeriod(filters.niveau)
				show_dashboard(page,filters,{container:content})
			}
		});
		const semestre_field = page.add_field({
			fieldtype: 'Select',
			label: 'Semestre',
			fieldname: 'semestre',
			options: [
				{value:'Semestre 1', label:'Semestre 1'},
				{value:'Semestre 2', label:'Semestre 2'},
			],
			change() {
				filters.semestre = this.get_value();
				if(!this.get_value()) return
				// periods = this.get_value()==null ? [...defaultPeriods]: await Udshed.Queries.loadCoursePeriod(filters.niveau)
				show_dashboard(page,filters,{container:content})
			}
		});
        const teacher_field = page.add_field({
			fieldtype: 'Link',
			label: 'Teacher',
			fieldname: 'teacher',
			options: 'Teacher',
			change() {
				filters.teacher = this.get_value();
				Udshed.Utils.refresh_filter(filters,"teacher",page,levelMap);
				show_dashboard(page,filters,{container:content})
			}
		});

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
			}

			if(userContext.default_academic_year) {
				page.fields_dict.academic_year.set_value(userContext.default_academic_year);
				filters.academic_year = userContext.default_academic_year;
			}
		})
        
    })
}

function initUI(page_section)
{
	page_section.empty()
}

function show_dashboard(page,filters,page_section)
{
    //{container,evolutionChart}
	initUI(page_section.container)
	if(filters.academic_year && !filters.faculty && !filters.filiere && !filters.niveau && !filters.teacher)
	{

        window.Udshed.Insight.Academic.Queries.getQueriesYearDashbord(filters,(data)=>{
            //show for year
		    Udshed.Insight.Academic.Year.showAcademicYearInsights(page,filters,page_section,data)
        })
		
	}
	else if(filters.academic_year && filters.teacher)
	{
		//show teacher
		window.Udshed.Insight.Academic.Queries.getQueriesTeacherDashbord(filters,(data)=>{
			Udshed.Insight.Academic.Teacher.showAcademicTeacherInsights(page,filters,page_section,data)

        })
	}
	else if(filters.academic_year && filters.faculty && !filters.filiere && !filters.niveau)
	{
		 window.Udshed.Insight.Academic.Queries.getQueriesFacultyDashbord(filters,(data)=>{
            //show for faculty
			Udshed.Insight.Academic.Faculty.showAcademicFacultyInsights(page,filters,page_section,data)
        })		
	}
	else if(filters.academic_year && filters.faculty && filters.filiere && !filters.niveau)
	{
		window.Udshed.Insight.Academic.Queries.getQueriesFieldOfStudyDashbord(filters,(data)=>{
            //show for filiere
			Udshed.Insight.Academic.FieldOfStudy.showAcademicFieldOfStudyInsights(page,filters,page_section,data)
        })	
	}
	else if(filters.academic_year && filters.faculty && filters.filiere && filters.niveau)
	{
		//show niveau
		window.Udshed.Insight.Academic.Queries.getQueriesFieldOfStudyLevelDashbord(filters,(data)=>{
			Udshed.Insight.Academic.FieldOfStudyLevel.showAcademicFieldOfStudyLevelInsights(page,filters,page_section,data)

        })
	}
	
}