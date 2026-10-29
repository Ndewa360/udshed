window.Udshed = window.Udshed || {};
window.Udshed.Utils = {
    refresh_filter(filters, field,page,levelMap)
    {
        if(field === "academic_year") {
            filters.faculty = null;
            filters.filiere = null;
            filters.niveau = null;

            page.fields_dict.faculty.set_value(null);
            page.fields_dict.filiere.set_value(null);
            page.fields_dict.niveau.set_value(null);
            if(page.fields_dict.semestre) {
                filters.semestre=null
                page.fields_dict.semestre.set_value(null)
            }
			if (levelMap && typeof levelMap === 'object') {
				Object.keys(levelMap).forEach((key) => delete levelMap[key]);
			}
			return;
		}

		if(field === "faculty") {
			filters.filiere = null;
			filters.niveau = null;

			page.fields_dict.filiere.set_value(null);
			page.fields_dict.niveau.set_value(null);

			if(page.fields_dict.semestre) {
				filters.semestre=null
				page.fields_dict.semestre.set_value(null)
			}
			if (levelMap && typeof levelMap === 'object') {
				Object.keys(levelMap).forEach((key) => delete levelMap[key]);
			}
            return;
        }

        if(field === "filiere") {
			filters.niveau = null;
			page.fields_dict.niveau.set_value(null);
			if(page.fields_dict.semestre) {
				filters.semestre=null
				page.fields_dict.semestre.set_value(null)
			}
			if (levelMap && typeof levelMap === 'object') {
				Object.keys(levelMap).forEach((key) => delete levelMap[key]);
			}
            return;
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
        return ((filter.academic_year && filter.teacher) || (filter.academic_year && filter.filiere && filter.niveau))
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