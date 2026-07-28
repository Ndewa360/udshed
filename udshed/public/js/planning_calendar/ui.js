window.Udshed = window.Udshed || {};

window.Udshed.UI = {
    
    get_grid_calendar_item(items,filter,coursePeriod) {
        
        let grid = Udshed.Utils.initDataPeriodForUi(coursePeriod) 
        
        
        items.forEach(item => {

            let dayOfWeek = new Date(item.date).toLocaleDateString('en-US', { weekday: 'long' }); // ex: "Monday"
            // let halfDay = item.period === "Morning" ? "Morning" : "Afternoon"; // ou selon comment tu définis ça dans ton backend

            if (grid[dayOfWeek]) {

                if(grid[dayOfWeek].get(item.period)== null) {
                    grid[dayOfWeek].set(item.period, {
                        subject: item.course, 
                        level:filter.niveau, 
                        item:item,
                        teachers: item.teachers 	
                    });			
                } else {
                    grid[dayOfWeek].get(item.period).teachers.push(item.enseignant);
                }
                
            } else {
                console.warn(`Jour de la semaine non reconnu: ${dayOfWeek}`);
            }
        });
        return grid;
    },

    show_calendar_hearder() {
        return  `
            <div class="planning-calendar" id="planning_calendar">

                <div class="planning-nav">
                    <div class="planning-nav-left">
                        <button class="btn btn-default btn-sm" id="prev-week">
                        ◀
                        </button>

                        <button class="btn btn-default btn-sm" id="today-week">
                        Aujourd’hui
                        </button>

                        <button class="btn btn-default btn-sm" id="next-week">
                        ▶
                        </button>
                    </div>

                    <div class="planning-nav-center">
                        <span id="week-label"></span>
                    </div>

                    <div class="planning-nav-right">
                        <select id="month-picker" class="form-control input-sm"></select>
                        <select id="week-select" class="form-control input-sm"></select>
                    </div>
                </div>
                <div class="planning-grid"></div>
            </div>
        `

    },

    show_calendar(calendar_zone,grid_data,coursePeriod,forTeacher=false)
    {
        calendar_zone.empty();
        let plan = new Map();
        coursePeriod.forEach((period)=>{
            plan.set(period.name,{libelle:period.libelle,items:[],fuseauHoraire : period.fuseau_horaire, heure_de_debut:period.heure_de_debut, heure_de_fin:period.heure_de_fin})
        })

        // Construire les lignes du matin et de l'après-midi
        for (let day of ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]) {
            for(let period of coursePeriod)
            {
                periodItem = grid_data[day].get(period.name)

                let period_cours_type_class = "cm";
                switch(periodItem?.item?.type) {
                    case "Cours":
                        period_cours_type_class = "cm";
                        break;
                    case "Traveaux Pratiques (TP)":
                        period_cours_type_class = "tp";
                        break;
                    case "Traveaux Dirigés (TD)":
                        period_cours_type_class = "td";
                        break;
                    case "Controlle Continue (CC)":
                        period_cours_type_class = "cc";
                        break;
                    case "Examen de session normal":
                        period_cours_type_class = "exam";
                        break;
                    case "Examen de rattrapage":
                        period_cours_type_class = "exam";
                        break;
                }
                if(periodItem)
                {
                    let periodTeacherOrRoomInfos = forTeacher ? `<b>${periodItem.item.filiere} ${periodItem.item.niveau_label}</b>` : periodItem.teachers.map(t => `<b>${t}</b>`).join('<br/> ');
                    periodCellCourseMode = periodItem.item.mode=="En ligne"? "En ligne <br/> - <br/>":
                        `Batiment: ${periodItem.item.batiment?periodItem.item.batiment:""}  <br/> Salle: ${periodItem.item.salle?periodItem.item.salle:""}<br/> - <br/>`
                    periodCell = `
                        <div class="planning-cell" data-day="${day}" data-half-libelle="${period.libelle}" data-half="${periodItem.half_day}" data-course='${JSON.stringify(periodItem)}'>
                            <div class="planning-item ${period_cours_type_class}">
                                <div class="planning-item-title">
                                    <span style="font-style:italic">${periodItem.subject}</span><br/>${periodItem.item.cours_label}
                                </div>
                                <div class="planning-item-meta">
                                    ${periodItem.item.type} <br/> - <br/> ${periodItem.room?periodItem.room:""}
                                </div>
                                <div class="planning-item-meta">
                                    ${periodCellCourseMode}
                                </div>
                                <div class="planning-item-meta">
                                    ${periodTeacherOrRoomInfos}
                                </div>
                            </div>
                        </div>`
                }
                else 
                {
                    periodCell = `
                        <div class="planning-cell empty" data-day="${day}" data-half="${period.name}">
                            <div class="no-course">Pas cours</div>
                        </div>`
                }

                plan.get(period.name).items.push(periodCell);
            }

        }

        let calendarHTML = `
            <div></div>
            <div class="planning-header">Lundi</div>
            <div class="planning-header">Mardi</div>
            <div class="planning-header">Mercredi</div>
            <div class="planning-header">Jeudi</div>
            <div class="planning-header">Vendredi</div>
            <div class="planning-header">Samedi</div>`

        for(let period of plan.keys())
        {   
            calendarHTML += `<div class="planning-time-label">`
            if(plan.get(period).libelle)
            {
                calendarHTML+= `<span>${plan.get(period).libelle}</span>`
            }
            let startPeriod = plan.get(period).heure_de_debut.split(":"), endPeriod = plan.get(period).heure_de_fin.split(":");
            calendarHTML +=`                    
                    <div class="planning-time-range">${startPeriod[0]}:${startPeriod[1]} - ${endPeriod[0]}:${endPeriod[1]}</div>
                    <div class="planning-time-fuseau">${plan.get(period).fuseauHoraire}</div>
                </div>
                ${plan.get(period).items.join('')}
            `
        }
        calendar_zone.html(calendarHTML);
        
    } ,
    update_page_actions(filter,btnEporterPDF,btnEnvoiMail) 
    {
        if(Udshed.Utils.isValidFecthDataFilter(filter))
        {
            btnEporterPDF.show();
            btnEnvoiMail.show();
        } else {
            btnEporterPDF.hide();
            btnEnvoiMail.hide();
        }
    }
};