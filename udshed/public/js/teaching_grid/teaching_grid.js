window.Udshed = window.Udshed || {};
window.Udshed.TeachingGrid = window.Udshed.TeachingGrid || {};

window.Udshed.TeachingGrid.DataGrid = class TeachingGrid {
    constructor(wrapper, canEdit = true) {
        this.wrapper = wrapper;
        this.page = wrapper.page;
        this.canEdit = Boolean(canEdit);
        this.datatable = null;
        this.initData()
        this.filters = {};

        this.make();        
    }

    initData(){
        this.data = [];
        this.stat = {
            total_credits: 0,
            total_hours: 0,
            course_count: 0,
            ue_count: 0
        }
        $('#stat-ue').text(0);
        $('#stat-courses').text(0);
        $('#stat-credits').text(0);
        $('#stat-hours').text(0);
        this.update_title()
        this.update_totals([]);
    }
    
    refresh() {
        this.load_data(this.filters);
    }
    
    
    load_data(filters) {
        var me = this;
        this.filters = filters
        this.update_title()
        
        // $('#semester-title').text(this.filters.semester);
        $('.table-area').html('<div class="text-center text-muted loading"><i class="fa fa-spinner fa-spin"></i> Chargement...</div>');
        
        Udshed.TeachingGrid.UtilsQueries.load_data(me.filters,(data)=>{
            if (data) {
                    me.data = data.grid
                    me.stat = data.stats
                    $('#stat-ue').text(data.stats.ue_count || 0);
                    $('#stat-courses').text(data.stats.course_count || 0);
                    $('#stat-credits').text(data.stats.total_credits || 0);
                    $('#stat-hours').text(data.stats.total_hours || 0);
                    me.render_datatable(true);
                    me.update_totals(data);
                } else {
                    $('.table-area').html('<div class="text-center text-muted">Aucune donnée disponible</div>');
                }
        });
    }
    update_title()
    {
        const title = $('.panel-title');
        if (this.filters?.semestre) {
            title.html(`Grille d'enseignement - Semestre <span id="semester-title">${this.filters.semestre.split(" ")[1]}</span>`);
        } else {
            title.text("Grille d'enseignement");
        }
    }

    getUeByCourseCode(courseCode)
    {
        let courseIndex = -1;
        let ueIndex = this.data.findIndex((value)=>{
           courseIndex =value.courses.findIndex((course)=> course.code == courseCode)
           return courseIndex>-1
        })
        return {courseIndex,ueIndex}
    }
    
    render_datatable(is_new=false) {
        var me = this;
        var data = this.data;
        
        // Préparer les données pour le DataTable
        var rows = [];
        var columns = [
            { name: 'Code UE', editable: false },
            { name: 'Code Cours', editable: false },
            { name: 'Intitulés', editable: me.canEdit, fieldtype: 'Data' },
            { name: 'Crédits', editable: me.canEdit, fieldtype: 'Float' },
            { name: 'Type', editable: false },
            { name: 'CM', editable: me.canEdit, fieldtype: 'Int' },
            { name: 'TD', editable: me.canEdit, fieldtype: 'Int' },
            { name: 'TP', editable: me.canEdit, fieldtype: 'Int' },
            { name: 'TPE', editable: me.canEdit, fieldtype: 'Int' },
            { name: 'Total', editable: false, fieldtype: 'Int' },
            { name: 'Enseignant', editable: me.canEdit, fieldtype: 'Link',options:"Teacher", with:180,
                format: function(data) {

                    if(!data) return data
                    
                    let value = JSON.parse(data)

                    let teachers = value.map((v)=>v.teacher)
                    var displayText = teachers.join(', ');
                    if (teachers.length > 2) {
                        displayText = teachers[0] + ' + ' + (teachers.length - 1) + ' autres';
                    }
                    else if( teachers.length==1) displayText = teachers[0]
                    return `<span class="multiple-teachers" title="${teachers.join('\n')}">
                                 ${displayText}
                               
                            </span>`;
                            //  <span class="teacher-count-badge">${teachers.length}</span>
                }
             },
            { name: 'Remarques', editable: false, width: 160,
                format: function(value) {
                    if (!value) return '';
                    const info = JSON.parse(value);
                    const esc = frappe.utils.escape_html;
                    let html = '';
                    if (info.partage) {
                        const classes = (info.partage_classes || []).map((c) => `• ${c}`).join('\n');
                        const bulle = __('Tronc commun : même cours, intitulé et heures communs.') + '\n'
                            + __('Aussi suivi par :') + (classes ? '\n' + classes : ` ${info.partage}`);
                        html += `<span class="indicator-pill blue" title="${esc(bulle)}">${__('Tronc commun')} +${info.partage}</span> `;
                    }
                    if (info.lies) {
                        // Info-bulle : chaque cours lié (autre grille) avec les classes qui le suivent.
                        const details = (info.lies_details || []).map((c) =>
                            `• ${c.code}${c.intitule ? ' — ' + c.intitule : ''}\n    ${__('Classes')} : ${(c.classes || []).join(', ') || '—'}`
                        ).join('\n');
                        const bulle = __('Lié à (planifié comme un cours commun) :') + '\n' + details;
                        html += `<span class="indicator-pill purple" title="${esc(bulle)}" style="cursor:help">🔗 ${__('Lié')} +${info.lies}</span> `;
                    }
                    if (info.avertissement) {
                        html += `<span class="indicator-pill orange" title="${esc(info.avertissement)}">⚠ ${__('Crédits/heures')}</span>`;
                    }
                    return html;
                }
            },
        ];
        
        // Construire les lignes
        data.forEach(function(ue) {
            // Ligne UE
            if(ue.ue_code!="UNKNOW")
            {
                rows.push([
                    ue.ue_code,
                    '',
                    ue.ue_title,
                    {content:ue.ue_credits,editable:false},
                    'UE',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                ]);
            }
            
            // Lignes cours
            ue.courses.forEach(function(course) {
                rows.push([
                    '',
                    course.code,
                    course.title,
                    course.credits,
                    course.type,
                    course.nombre_dheure_cm,
                    course.nombre_dheure_td,
                    course.nombre_dheure_tp,
                    course.nombre_dheure_tpe,
                    course.total_hours,
                    JSON.stringify(course.teacher),
                    (course.classes_partagees || course.avertissement || course.cours_lies)
                        ? JSON.stringify({
                            partage: course.classes_partagees || 0,
                            partage_classes: course.classes_partagees_libelles || [],
                            lies: course.cours_lies || 0,
                            lies_details: course.cours_lies_details || [],
                            avertissement: course.avertissement || ''
                        })
                        : '',
                ]);
            });
        });
        
        // Initialiser ou mettre à jour le DataTable
        if (me.datatable && !is_new) {
            me.datatable.refresh(rows, columns);
        } else {			
            me.datatable = new frappe.DataTable($('.table-area')[0],{
                columns: columns,
                data: rows,
                layout: 'fluid',
                cellHeight: 35,
                serialNoColumn: false,
                checkboxColumn: false,
                inlineFilters: true,
                language: frappe.boot.lang,
                getEditor: function(colIndex, rowIndex, value, column, row) {

                    if (!me.canEdit || !row.editable) return;
                    // Ligne UE : seul l'intitulé est modifiable (le code ne l'est jamais).
                    const ligne = me.datatable.datamanager.data[rowIndex] || [];
                    if (ligne[4] === 'UE' && colIndex !== 2) return;

                    if(colIndex==10 && row.fieldtype== "Link")
					{
						return me.create_teacher_editor(colIndex, rowIndex, value, column, row)
					}
					return me.create_standad_editor(colIndex, rowIndex, value, column, row)
                    
                },
                on_update: function(data) {
                    me.update_totals();
                }
            });
        }

        me.datatable.datamanager.data.forEach((row, index) => {
            if (row[4] === 'UE') {
                var $row = $(me.datatable.wrapper).find(`[data-row-index="${index}"]`);
                $row.css({
                    'background-color': "#aac1d4",
                    'font-weight': '600',
                    'border-bottom': '2px solid #aac1d4'
                });
            }
        });
    }

    // Gestionnaire de clic sur la cellule Enseignant
    handleTeacherCellClick(rowIndex, colIndex) {
        var me = this;
        if (!me.canEdit) {
            Udshed.Messages.warning(__('Vous n\'avez pas le droit de modifier cette grille.'));
            return;
        }
        
        // Récupérer le code du cours (colonne 1)
        var courseCode = me.datatable.datamanager.data[rowIndex][1];
        if (!courseCode) {
            Udshed.Messages.validation(__('Cette ligne ne correspond pas à un cours'));
            return;
        }

        let {ueIndex,courseIndex } = me.getUeByCourseCode(courseCode)

        let teachingUnit = me.data[ueIndex]["courses"][courseIndex]["teaching_unit"]
        
        
        // Trouver le document Course correspondant
        // Udshed.TeachingGrid.UtilsQueries.load_doctype_list(
        //     {
        //         doctype: 'Course Teacher Item', // Votre doctype existant
        //         filters: {
        //             'parent': teachingUnit,
        //         },
        //         fieldname: ['name']
        //     },(data)=>{
        //         if(data && data.name)
        //         {
        //             Udshed.TeachingGrid.Dialog.open_teacher_assignment_dialog(data.name, courseCode,teachingUnit, rowIndex, colIndex,this.filters);
        //         }
        //         else 
        //         {
        //             frappe.msgprint(__('Cours non trouvé dans la base de données'));
        //         }
        //     }
        // )

        Udshed.TeachingGrid.Dialog.open_teacher_assignment_dialog(courseCode,teachingUnit, rowIndex, colIndex,this.filters,()=>{
            me.refresh()
        });

    }
	create_teacher_editor(colIndex, rowIndex, data, column, row)
	{
        var me = this;
    
        var container = document.createElement('div');
        container.style.width = '100%';
        container.style.padding = '4px';
        
        // Afficher la valeur formatée
        var displayDiv = document.createElement('div');
        displayDiv.className = 'teacher-display';
		if(data)
        {
            let value = JSON.parse(data)

            let teachers = value.map((v)=>v.teacher)
            var displayText = teachers.join(', ');
            if (teachers.length > 2) {
                displayText = teachers[0] + ' + ' + (teachers.length - 1) + ' autres';
            }
            else if( teachers.length==1) displayText = teachers[0]
            displayDiv.innerHTML = `<span class="multiple-teachers" title="${teachers.join('\n')}">
                            ${displayText}
                        <span class="teacher-count-badge">${teachers.length}</span>
                    </span>`;
        }
        else {
            displayDiv.innerHTML ='<span class="text-muted">Cliquez pour assigner</span>';
        }
                
        displayDiv.style.cursor = 'pointer';
        displayDiv.style.padding = '4px';
        
        container.appendChild(displayDiv);
        $(displayDiv).on('click', function() {
            var courseCode = me.datatable.datamanager.data[rowIndex][1];
            if (courseCode) {
                me.handleTeacherCellClick(rowIndex, colIndex);
            }
        });

           return {
                initValue: function() {
                    $(column).empty().append(container);
                },
                getValue: function() {
                    return data;
                },
                setValue: function(val) {
                    // Mettre à jour l'affichage
                    if(data)
                    {
                        let value = JSON.parse(data)

                        let teachers = value.map((v)=>v.teacher)
                        var displayText = teachers.join(', ');
                        if (teachers.length > 2) {
                            displayText = teachers[0] + ' + ' + (teachers.length - 1) + ' autres';
                        }
                        else if( teachers.length==1) displayText = teachers[0]
                        displayDiv.innerHTML = `<span class="multiple-teachers" title="${teachers.join('\n')}">
                                        ${displayText}
                                    <span class="teacher-count-badge">${teachers.length}</span>
                                </span>`;
                    }
                    else {
                        displayDiv.innerHTML = '<span class="text-muted">Cliquez pour assigner</span>';
                    }
                }
            };
        
		
	}
    create_standad_editor(colIndex, rowIndex, value, column, row) 
	{
		let me = this;
		var fieldtype = column.fieldtype || 'Data';
		var input = document.createElement('input');
		input.type = 'text';
		input.className = 'form-control input-sm';
		input.value = value;
		
		if (fieldtype === 'Int') {
			input.type = 'number';
			input.step = '1';
			input.min = '0';
		} else if (fieldtype === 'Float') {
			input.type = 'number';
			input.step = '0.5';
			input.min = '0';
		}
		
		return {
			initValue: function() {
				$(column).empty().append(input);
				$(input).focus();
			},
			getValue: function() {
				return input.value;
			},
			setValue: function(value) {
				if (fieldtype === 'Int' && value) value = parseInt(value);
				me.updateCell(rowIndex, colIndex, value);
				input.value = value;
			}
		};
	}

	updateCell(rowIndex,colIndex,value){
		let me = this;
        let ligne = me.datatable.datamanager.data[rowIndex];
        if (ligne[4] === 'UE') {
            if (colIndex === 2 && value !== ligne[2]) me.save_ue(ligne[0], value);
            return;
        }
        let codeCours = ligne[1]
        let {courseIndex,ueIndex}= me.getUeByCourseCode(codeCours)
        if (ueIndex < 0 || courseIndex < 0) return;
        const cours = this.data[ueIndex].courses[courseIndex];
        const heures = { 5: "nombre_dheure_cm", 6: "nombre_dheure_td", 7: "nombre_dheure_tp", 8: "nombre_dheure_tpe" };
        let valeurs = null;

		if (colIndex==2)
		{
            if (!String(value || "").trim() || value === cours.title) return;
            valeurs = { intitule_cours: String(value).trim() };
            cours.title = valeurs.intitule_cours;
		}
		else if (colIndex==3)
		{
            const credits = parseFloat(String(value).replace(",", ".")) || 0;
            this.recalculateCredit(credits, this.data[ueIndex], codeCours)
            valeurs = { credits };
		}
		else if (heures[colIndex])
		{
            const nombre = parseInt(value) || 0;
            this.recalcultateTime(nombre, cours, heures[colIndex])
            valeurs = { [heures[colIndex]]: nombre };
		}
        this.render_datatable(false)
        if (valeurs) me.save_course(cours, valeurs);
	}

    save_course(cours, valeurs) {
        const me = this;
        const commun = Object.keys(valeurs).some((k) => k !== "credits");
        const envoyer = (confirme) => frappe.call({
            method: "udshed.api.teaching_grid.modifier_cours",
            args: { teaching_unit: cours.teaching_unit, ...me.filters, valeurs, appliquer_au_tronc_commun: confirme ? 1 : 0 },
            callback: (r) => {
                const res = r.message || {};
                if (res.avertissement) Udshed.Messages.warning(res.avertissement);
                else Udshed.Messages.success(__("Grille enregistrée."));
                me.refresh();
            },
            error: (err) => {
                Udshed.Messages.error(err, __("Modification refusée"));
                me.refresh();
            }
        });
        if (commun && cours.classes_partagees) {
            frappe.confirm(
                __("Ce cours est partagé avec {0} autre(s) classe(s) (tronc commun). L'intitulé et les heures seront modifiés pour toutes ces classes. Continuer ?", [cours.classes_partagees]),
                () => envoyer(true),
                () => me.refresh()
            );
            return;
        }
        envoyer(false);
    }

    save_ue(ue_code, intitule) {
        const me = this;
        if (!String(intitule || "").trim()) return me.refresh();
        frappe.call({
            method: "udshed.api.teaching_grid.modifier_ue",
            args: { ue_code, intitule: String(intitule).trim(), ...me.filters },
            callback: () => { Udshed.Messages.success(__("UE renommée.")); me.refresh(); },
            error: (err) => { Udshed.Messages.error(err, __("Modification refusée")); me.refresh(); }
        });
    }

    courses_list() {
        return (this.data || []).flatMap((ue) => ue.courses.map((c) => ({ ...c, ue_code: ue.ue_code })));
    }
    recalcultateTime(value,cours,typeTime)
    {
        cours.nombre_dheure_cm = typeTime=="nombre_dheure_cm"? value:cours.nombre_dheure_cm
        cours.nombre_dheure_td = typeTime=="nombre_dheure_td"? value:cours.nombre_dheure_td
        cours.nombre_dheure_tp = typeTime=="nombre_dheure_tp"? value:cours.nombre_dheure_tp
        cours.nombre_dheure_tpe = typeTime=="nombre_dheure_tpe"? value:cours.nombre_dheure_tpe
        cours.total_hours = cours.nombre_dheure_cm + cours.nombre_dheure_td + cours.nombre_dheure_tp + cours.nombre_dheure_tpe
        // Recalculer les totaux globaux
        this.update_totals();
    }

    recalculateCredit(value,ue,coursCode)
    {
        let totalCredit = 0;
        for(let i=0; i<ue.courses.length; i++)
        {
            if (ue.courses[i].code == coursCode)
            {
                ue.courses[i].credits = value;
            }
            totalCredit += Number(ue.courses[i].credits) || 0;
        }
        ue.ue_credits = totalCredit;

    }
   
    update_totals() {
        var totals = { cm: 0, td: 0, tp: 0, tpe: 0, total: 0 };
        
        this.data.forEach(function(ue) {
            ue.courses.forEach(function(course) {
                totals.cm += course.nombre_dheure_cm || 0;
                totals.td += course.nombre_dheure_td || 0;
                totals.tp += course.nombre_dheure_tp || 0;
                totals.tpe += course.nombre_dheure_tpe || 0;
                totals.total += course.total_hours || 0;
            });
        });
        
        $('#total-cm').text(totals.cm);
        $('#total-td').text(totals.td);
        $('#total-tp').text(totals.tp);
        $('#total-tpe').text(totals.tpe);
        $('#total-hours').text(totals.total);
        $('.totals-row').show();
    }
    

	make() {
        var me = this;
        
        // Container pour les statistiques
        $(this.wrapper).find('.page-content').append(`
            <div class="teaching-grid-container">
                <div class="stats-container">
                    <div class="stat-card">
                        <div class="stat-value" id="stat-ue">0</div>
                        <div class="stat-label">UE</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="stat-courses">0</div>
                        <div class="stat-label">Cours</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="stat-credits">0</div>
                        <div class="stat-label">Crédits</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="stat-hours">0</div>
                        <div class="stat-label">Heures</div>
                    </div>
                </div>
                
                <div class="panel panel-default">
                    <div class="panel-heading">
                        <div class="panel-title">
                            Grille d'enseignement 
                        </div>
                    </div>
                    <div class="panel-body">
                        <div class="table-area" style="min-height: 300px;">
                            <div class="text-center text-muted">Aucune donnée disponible! Veuillez selectionnez les filtres appropriés</div>
                        </div>
                    </div>
                </div>
                
                <div class="totals-row" style="display: none;">
                    <span><strong>Total CM:</strong> <span id="total-cm">0</span>h</span>
                    <span><strong>Total TD:</strong> <span id="total-td">0</span>h</span>
                    <span><strong>Total TP:</strong> <span id="total-tp">0</span>h</span>
                    <span><strong>Total TPE:</strong> <span id="total-tpe">0</span>h</span>
                    <span><strong>Total heures:</strong> <span id="total-hours">0</span>h</span>
                </div>
            </div>
			<style>
.teaching-grid-container {
    padding: 15px;
}

.stats-container {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 15px;
    margin-bottom: 20px;
}

.stat-card {
    background: white;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 15px;
    text-align: center;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.stat-value {
    font-size: 24px;
    font-weight: bold;
    color: var(--primary-color);
    line-height: 1.2;
}

.stat-label {
    font-size: 13px;
    color: #8a99aa;
    margin-top: 5px;
}

.panel {
    border-radius: 8px;
    overflow: hidden;
}

.panel-heading {
    padding: 12px 15px;
    background-color: #f5f7fa;
    border-bottom: 1px solid var(--border-color);
}

.panel-title {
    font-weight: 600;
    color: #334455;
}

.table-area {
    min-height: 300px;
}

.totals-row {
    margin-top: 15px;
    padding: 10px 15px;
    background: white;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    display: flex;
    flex-direction:row;
    justify-content: space-around;

}

.loading {
    padding: 50px;
    font-size: 14px;
}

/* Style pour les lignes UE */
[data-row-index]:has(td:first-child:not(:empty)) {
    background-color: #f0f4f9 !important;
    font-weight: 600;
}

[data-row-index]:has(td:first-child:not(:empty)) td {
    border-bottom: 2px solid #d1d9e6;
}

/* Style pour les cellules éditables */
.dt-cell--editable {
    cursor: pointer;
}

.dt-cell--editable:hover {
    background-color: #f0f7ff;
}

/* Responsive */
@media (max-width: 768px) {
    .stats-container {
        grid-template-columns: repeat(2, 1fr);
    }
    
    .totals-row {
        flex-wrap: wrap;
        gap: 10px;
    }
}

/* Style pour l'autocomplétion des enseignants */
.teacher-autocomplete {
    border: 1px solid #d1d8dd;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 13px;
    transition: border-color 0.2s;
}

.teacher-autocomplete:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px rgba(40, 96, 144, 0.1);
}

.teacher-suggestions {
    box-shadow: 0 6px 12px rgba(0, 0, 0, 0.175);
    border-radius: 4px;
    max-height: 250px;
    overflow-y: auto;
}

.teacher-suggestions .dropdown-item {
    padding: 8px 12px;
    cursor: pointer;
    border-bottom: 1px solid #f0f4f7;
    transition: background-color 0.2s;
}

.teacher-suggestions .dropdown-item:last-child {
    border-bottom: none;
}

.teacher-suggestions .dropdown-item:hover,
.teacher-suggestions .dropdown-item.active {
    background-color: #f5f7fa;
}

.teacher-suggestions .dropdown-item.disabled {
    color: #8a99aa;
    cursor: default;
}

.teacher-suggestions .dropdown-item.disabled:hover {
    background-color: transparent;
}

/* Animation d'apparition */
.teacher-suggestions {
    animation: fadeIn 0.2s ease-in-out;
}

@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(-10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Style pour l'icône de recherche (optionnel) */
.teacher-autocomplete {
    background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="%238a99aa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>');
    background-repeat: no-repeat;
    background-position: right 8px center;
    background-size: 16px;
    padding-right: 32px;
}
</style>
        `);
        
        // Charger les données initiales
        // this.refresh();
    }
}
