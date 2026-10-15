window.Udshed = window.Udshed || {};
window.Udshed.TeachingGrid = window.Udshed.TeachingGrid || {};

window.Udshed.TeachingGrid.Dialog = {
    
    
// Ouvrir le dialogue d'assignation des enseignants
open_teacher_assignment_dialog(courseCode,teachingUnitCode, rowIndex, colIndex,filters,callbackFunction) {
    
    // Créer un dialogue avec un grid lié au child table de votre doctype
    var dialog = new frappe.ui.Dialog({
        title: __('Gestion des enseignants - {0}', [courseCode]),
        size: 'large',
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'info_html',
                options: `<div class="alert alert-info">
                    <i class="fa fa-info-circle"></i> 
                    Gérez les enseignants assignés à ce cours. Les modifications sont automatiquement sauvegardées.
                </div>`
            },
            {
                fieldtype: 'Section Break'
            },
            {
                fieldtype: 'Table',
                fieldname: 'table_enseignant',
                label: __('Enseignants'),
                options: 'Course Teacher Item',
                description: 'Liste des enseignants pour ce cours',
                fields: [
                    {
                        fieldtype: 'Link',
                        fieldname: 'enseignant',
                        label: 'Enseignant',
                        options: 'Teacher', // Votre doctype enseignant
                        in_list_view: 1,
                        reqd: 1,
                        columns: 4
                    },
                    {
                        fieldtype: 'Select',
                        fieldname: 'type_de_cours',
                        label: 'Type',
                        options: [
                            "Cours Magistral (CM)",
                            "Travaux Pratique (TP)",
                            "Travaux Dirigés (TD)"
                        ],
                        default: 'Cours Magistral (CM)',
                        in_list_view: 1,
                        columns: 3
                    }
                ],
            },
            {
                fieldtype: 'Section Break'
            },
            {
                fieldtype: 'HTML',
                fieldname: 'preview_html',
                options: '<div class="teacher-hours-preview">Prévisualisation de la répartition des heures</div>'
            }
        ],
        data:[],
        primary_action_label: __('Enregistrer'),        
        primary_action: function(values) {
            console.log("Field ",values)
            Udshed.TeachingGrid.UtilsQueries.update_teacher_list(teachingUnitCode,values.table_enseignant?values.table_enseignant:[],()=>{
                    dialog.hide()
                    callbackFunction()
                }
            );
        }
    });

    // Charger les données du cours pour la prévisualisation
    Udshed.TeachingGrid.Dialog.load_course_data_for_preview(teachingUnitCode, dialog,filters.academic_year);
        
    dialog.show();
},

load_course_data_for_preview(teachingUnitCode,dialog,academic_year)
{
    Udshed.TeachingGrid.UtilsQueries.load_doctype(
        {
            doctype: 'Teaching Unit',
            filters: {
                'name': teachingUnitCode,
            },
            fields: ['*']
        },
        (data)=>{
            if(!data) return;
            teacher_list = data.table_enseignant
            console.log("Teacher list ",teacher_list)
            // Récupérer le grid
            var grid = dialog.fields_dict.table_enseignant.grid;

            // Ajouter les données existantes
            if (teacher_list && teacher_list.length > 0) {
                grid.df.data = teacher_list.map((t)=>({
                    enseignant:t.enseignant,
                    type_de_cours: t.type_de_cours
                }))
                grid.refresh();
            } else {
                // Vider le grid
                grid.df.data = [];
                grid.refresh();
            }

        },
        "Chargement de la liste des enseignants du cours",
    )
},

// Mettre à jour la prévisualisation à partir du grid
update_teacher_preview_from_grid(courseDocName,teachingUnitName, dialog) {

    
    // Récupérer les données du grid
    var gridData = dialog.fields_dict.teachers.grid.get_data();
    
    // Créer un objet cours temporaire avec les données du grid
    Udshed.TeachingGrid.UtilsQueries.load_doctype_list(
        {
            doctype: 'Teaching Unit',
            name: teachingUnitName
        },
        (data)=>{
            if(data){
                var tempDoc = r.message;
                tempDoc.teachers = gridData;
                Udshed.TeachingGrid.Dialog.update_teacher_preview(tempDoc, dialog);
            }
        }
    )
},
   	 
show_import_dialog(filters,onAfterImported= (data)=>{}) {
    
    var d = new frappe.ui.Dialog({
        title: __('Importer une grille'),
        freeze: true,
        freeze_message: __("Importation de la grille en cours..."),  
        size: 'medium',
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'template_info',
                options: `
                    <div class="alert alert-primary" style="display: flex; align-items: center; justify-content: space-between;">
                        <div>
                            <i class="fa fa-download"></i> 
                            <strong>Téléchargez d'abord le template</strong> pour vous assurer que votre fichier est au bon format.
                        </div>
                        <button class="btn btn-sm btn-default download-template-btn">
                            <i class="fa fa-file-excel-o"></i> Télécharger le template
                        </button>
                    </div>
                `
            },
            {
                fieldtype: 'Section Break'
            },

            {
                fieldtype: 'Attach',
                fieldname: 'file',
                label: __('Fichier Excel'),
                reqd: 1,
                description: 'Format .xlsx ou .xls'
            },
            {
                fieldtype: 'HTML',
                fieldname: 'instructions',
                options: `
                    <div class="well" style="background: #f8f9fa; padding: 10px; border-radius: 4px; margin-top: 10px;">
                        <h6><i class="fa fa-info-circle"></i> Instructions :</h6>
                        <ul class="small" style="margin-bottom: 0; padding-left: 20px;">
                            <li>Le fichier doit suivre exactement le format du template</li>
                            <li>Les lignes UE doivent avoir un code dans la première colonne</li>
                            <li>Les lignes cours doivent avoir un code dans la deuxième colonne</li>
                            <li>Les informations sur l'année académique, le niveau et le semestre ne doivent pas être renseignées</li>
                            <li>Ne modifiez pas la structure des colonnes</li>
                        </ul>
                    </div>
                `
            }
        ],
        primary_action_label: __('Importer'),
        primary_action(values) {
            
            // Afficher le chargement
            d.set_primary_action(__('Import en cours...'), null, 'btn-primary disabled');
            d.fields_dict.file.$wrapper.hide();

            d.hide();
            Udshed.TeachingGrid.UtilsQueries.import_grid({
                    file_url: values.file,
                    ...filters
                },
            (data)=>{
                if(!data) return;
                console.log("Data import",data)
                if(data.status)
                {
                    frappe.utils.play_sound("submit");

                    frappe.msgprint({
                        title: __('Import réussi'),
                        message: `
                            <p>UE créées: ${data.data.ues_created }</p>
                            <p>Cours créés: ${data.data.courses_created }</p>
                            <p>Cours mis à jour: ${data.data.courses_updated }</p>
                        `,
                        indicator: 'green'
                    });

                    onAfterImported(data);
                }
                else
                {
                    frappe.msgprint({
                        title: __('Echec d\'importation'),
                        message: data.message.replace("\n","<br\>"),
                        indicator: 'red'
                    });
                    frappe.utils.play_sound("error")
                }
                
            })
        }
    });
     d.$wrapper.find('.download-template-btn').on('click', ()=>{
        Udshed.TeachingGrid.UtilsQueries.download_template(
            //  ()=>d.hide()
            );
    });
    d.show();
},
    

}
