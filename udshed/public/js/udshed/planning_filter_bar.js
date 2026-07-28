window.Udshed = window.Udshed || {};
window.Udshed.PlanningFilterBar = {
    init({ page, filters, on_filter_change }) {
        let levelMap = {};

        const academic_field = page.add_field({
            fieldtype: 'Link',
            label: 'Année académique',
            fieldname: 'academic_year',
            options: 'Academic Year',
            change() {
                filters.academic_year = this.get_value();
                Udshed.Utils.refresh_filter(filters, 'academic_year', page, levelMap);
                on_filter_change(filters);
            }
        });

        const faculty_field = page.add_field({
            fieldtype: 'Link',
            label: 'Faculté',
            fieldname: 'faculty',
            options: 'Faculty',
            change() {
                filters.faculty = this.get_value();
                Udshed.Utils.refresh_filter(filters, 'faculty', page, levelMap);
                on_filter_change(filters);
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
                Udshed.Utils.refresh_filter(filters, 'filiere', page, levelMap);

                Udshed.UtilsQueries.loadLevels(this.get_value(), niveau_field, (levels) => {
                    levelMap = levels ? levels.reduce((acc, curr) => {
                        acc[curr.level] = curr.name;
                        return acc;
                    }, {}) : {};

                    niveau_field.df.options = levels
                        ? levels.map((value) => ({ value: value.level, name: value.name }))
                        : [];
                    niveau_field.refresh();
                });

                on_filter_change(filters);
            }
        });

        const niveau_field = page.add_field({
            fieldtype: 'Select',
            label: 'Niveau',
            fieldname: 'niveau',
            change() {
                filters.niveau = levelMap[this.get_value()];
                Udshed.Utils.refresh_filter(filters, 'niveau', page, levelMap);
                on_filter_change(filters);
            }
        });

        const teacher_field = page.add_field({
            fieldtype: 'Link',
            label: 'Teacher',
            fieldname: 'teacher',
            options: 'Teacher',
            change() {
                filters.teacher = this.get_value();
                Udshed.Utils.refresh_filter(filters, 'teacher', page, levelMap);
                on_filter_change(filters);
            }
        });

        return { academic_field, faculty_field, filiere_field, niveau_field, teacher_field };
    }
};
