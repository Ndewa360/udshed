frappe.pages['grille-denseignement'].on_page_load = function(wrapper) {
	frappe.require([
		'/assets/udshed/css/planning_academique.css',
		'/assets/udshed/js/utils/utils.js',
		'/assets/udshed/js/utils/utils_queries.js',
		'/assets/udshed/js/utils/permission.js',
		'/assets/udshed/js/teaching_grid/teaching_grid_utilui.js',
		'/assets/udshed/js/teaching_grid/teaching_grid_query.js',
		'/assets/udshed/js/teaching_grid/teaching_grid_dialog.js',
		'/assets/udshed/js/teaching_grid/teaching_grid.js',
	]).then(async () => {
        const rawUserContext = await Udshed.UtilsQueries.get_data_of_user();
        const userContext = Udshed.Perms.normalizeUserContext(rawUserContext);
        const canManageGrid = userContext.can_plan;

        var page = frappe.ui.make_app_page({
            parent: wrapper,
            title: 'Grilles d\'enseignements',
            single_column: true
        });

        let filters = {
            academic_year: userContext.default_academic_year || null,
            faculty: userContext.faculty.length === 1 ? userContext.faculty[0] : null,
            filiere: userContext.filiere.length === 1 ? userContext.filiere[0] : null,
            niveau: userContext.niveau.length === 1 ? userContext.niveau[0] : null,
            semestre: null,
        };
        let levelMap = {};

        let teaching_grid = new Udshed.TeachingGrid.DataGrid(wrapper, canManageGrid);

        const btnImporter = page.set_primary_action(__('Importer'), function() {
            Udshed.TeachingGrid.Dialog.show_import_dialog(filters,()=>teaching_grid.refresh());
        }, 'upload');

        const btnExporter = page.set_secondary_action(__('Exporter'), function() {
            Udshed.TeachingGrid.UtilsQueries.export_grid(filters,()=>teaching_grid.refresh());
        }, 'download');
        Udshed.TeachingGrid.UtilsUi.update_page_actions(filters, btnExporter, btnImporter, canManageGrid);

        // Édition : ajout / retrait de cours (le contenu se modifie dans le tableau).
        const grilleChoisie = () => {
            if (Udshed.TeachingGrid.UtilsUi.isValideFilterForGrid(filters)) return true;
            Udshed.Messages.validation(__("Sélectionnez l'année, la faculté, la filière, le niveau et le semestre."));
            return false;
        };
        if (canManageGrid) {
            page.add_inner_button(__("Ajouter un cours"), () => {
                if (grilleChoisie()) Udshed.TeachingGrid.Dialog.open_add_course_dialog(filters, () => teaching_grid.refresh());
            });
            page.add_inner_button(__("Cours communs"), () => {
                if (grilleChoisie()) {
                    Udshed.TeachingGrid.Dialog.open_link_courses_dialog(filters, teaching_grid.courses_list(), () => teaching_grid.refresh());
                }
            });
            page.add_inner_button(__("Retirer un cours"), () => {
                if (grilleChoisie()) {
                    Udshed.TeachingGrid.Dialog.open_delete_course_dialog(filters, teaching_grid.courses_list(), () => teaching_grid.refresh());
                }
            });
        }

        function update_grid() {
            if (Udshed.TeachingGrid.UtilsUi.isValideFilterForGrid(filters)) {
                teaching_grid.load_data(filters);
            } else {
                teaching_grid.initData();
                teaching_grid.render_datatable();
            }
            Udshed.TeachingGrid.UtilsUi.update_page_actions(filters, btnExporter, btnImporter, canManageGrid);
        }

        function applyRestrictions() {
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
            if (!canManageGrid) {
                ["academic_year", "faculty", "filiere", "niveau"].forEach((name) => {
                    if (filters[name] && page.fields_dict[name]) page.fields_dict[name].$input.prop("disabled", true);
                });
            }
        }

        page.add_field({
            fieldtype: 'Link',
            label: 'Année académique',
            fieldname: 'academic_year',
            options: 'Academic Year',
            default: filters.academic_year,
            change(e) {
                filters.academic_year = this.get_value();
                Udshed.Utils.refresh_filter(filters,"academic_year",page,levelMap);
                update_grid();
            }
        });

        const faculty_field = page.add_field({
            fieldtype: 'Link',
            label: 'Faculté',
            fieldname: 'faculty',
            options: 'Faculty',
            default: filters.faculty,
            change(e) {
                filters.faculty = this.get_value();
                Udshed.Utils.refresh_filter(filters,"faculty",page,levelMap);
                update_grid();
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
                update_grid();
            }
        });

        const niveau_field = page.add_field({
            fieldtype: 'Select',
            label: 'Niveau',
            fieldname: 'niveau',
            change() {
                filters.niveau = this.get_value() || null;
                Udshed.Utils.refresh_filter(filters,"niveau",page,levelMap);
                update_grid();
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
                update_grid();
            }
        });

        if (filters.filiere) {
            const levels = await Udshed.UtilsQueries.loadLevels(filters.filiere, niveau_field);
            levelMap = (levels || []).reduce((acc, curr) => {
                acc[curr.level] = curr.name;
                return acc;
            }, {});
            niveau_field.df.options = (levels || []).map((value) => ({ value: value.name, label: value.level }));
            const initialLevel = (levels || []).find((level) => level.name === filters.niveau);
            if (initialLevel) niveau_field.set_value(initialLevel.name);
            niveau_field.refresh();
        }

        applyRestrictions();
    });
}
