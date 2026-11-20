window.Udshed = window.Udshed || {};
window.Udshed.Utils = {
    refresh_filter(filters, field, page, levelMap)
    {
        const clear_field = (name) => {
            const control = page && page.fields_dict && page.fields_dict[name];
            if (!control) return;
            filters[name] = null;
            if (control.get_value && control.get_value()) control.set_value(null);
            if (control.df && control.df.fieldtype === "Select") control.df.options = [];
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
                clear_field("semestre");
                clear_level_map();
            } else if (field === "faculty") {
                clear_field("filiere");
                clear_field("niveau");
                clear_field("semestre");
                clear_level_map();
            } else if (field === "filiere") {
                clear_field("niveau");
                clear_field("semestre");
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
        const byTeacher = Boolean(filter.teacher);
        const byClass = Boolean(filter.filiere && filter.niveau);
        return byTeacher !== byClass;
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