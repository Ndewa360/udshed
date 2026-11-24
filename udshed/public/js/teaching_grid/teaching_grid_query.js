window.Udshed = window.Udshed || {};
window.Udshed.TeachingGrid = window.Udshed.TeachingGrid || {};

window.Udshed.TeachingGrid.UtilsQueries = {
    
    load_data(args, callbackFunction) {

        Udshed.Loading.call({
            method: 'udshed.api.teaching_grid.get_academic_teaching_unit',
            freeze: true,
            freeze_message: __("Chargement de la grille..."),
            args: {...args},
            callback: function(r) {
                
                if (r.message) {
                    callbackFunction(r.message)
                } else {
                    callbackFunction(null)
                }
            }
        });
    },
    preview_import(args, callbackFunction)
    {
        Udshed.Loading.call({
            method: 'udshed.api.teaching_grid.previsualiser_import_grille',
            freeze: true,
            freeze_message: __("Analyse du fichier..."),
            args: {...args},
            error: (error) => {
                Udshed.Messages.error(error, __('Analyse du fichier impossible.'));
                callbackFunction(null);
            },
            callback: (r) => callbackFunction(r.message || null)
        });
    },
    import_grid(args,callbackFunction)
    {
        Udshed.Loading.call({
            method: 'udshed.api.teaching_grid.import_grid',
            freeze: true,
            freeze_message: __("Importation de la grille..."),
            args: {...args},
            error:(error)=>{
                Udshed.Messages.error(error, __('Erreur lors de l\'importation.'));
                callbackFunction(null)
            },
            callback: function(r) {
                if (r.message) {
                    callbackFunction(r.message)
                } else {
                    callbackFunction(null)
                }
            }
        });
    },    
    load_doctype_list(args,callbackFunction,message ="Chargement de la liste")
    {
        Udshed.Loading.call({
            method: 'frappe.client.get_list',
            freeze:true,
            freeze_message:__(message),
            args: {...args},
            callback: function(r) {
                if (r.message) {
                    // nsage.teachers
                    callbackFunction(r.message);
                } else {
                    callbackFunction(null);
                }
            }
        });
    },
    load_doctype(args,callbackFunction,message ="Chargement de la liste")
    {
        Udshed.Loading.call({
            method: 'frappe.client.get',
            freeze:true,
            freeze_message:__(message),
            args: {...args},
            callback: function(r) {
                if (r.message) {
                    // nsage.teachers
                    callbackFunction(r.message);
                } else {
                    callbackFunction(null);
                }
            }
        });
    },

    download_template(callbackFunction= ()=>{})
    {
            Udshed.Loading.call({
            method: 'udshed.api.teaching_grid.download_template',
            freeze: true,
            freeze_message: __("Génération du modele en cours..."),
            callback: function(r) {
                if (r.message && r.message.success) {
                    // Ouvrir l'URL du fichier
                    window.open(r.message.file_url);
                    
                    Udshed.Messages.success(__('Téléchargement du template démarré'));
                    frappe.utils.play_sound("submit");

                } else {
                    Udshed.Messages.validation(r.message.error || __('Impossible de générer le template'), __('Erreur'));
                }
            }
        });
    },

    export_grid(filters,callbackFunction= ()=>{})
    {
        Udshed.Loading.call({
            method: 'udshed.api.teaching_grid.export_grid',
            args:{...filters},
            freeze: true,
            freeze_message: __("Exportation de la grille en cours..."),
            callback: function(r) {
                if (r.message && r.message.success) {
                    // Ouvrir l'URL du fichier
                    window.open(r.message.file_url);
                    
                    Udshed.Messages.success(__('Téléchargement de la grille démarré'));
                    frappe.utils.play_sound("submit");

                } else {
                    Udshed.Messages.validation(r.message.error || __('Impossible d\'exporter la grille'), __('Erreur'));
                }
            }
        });
    },

    update_teacher_list(teachingUnitCode,grid_teacher,callbackFunction = ()=>{})
    {
        Udshed.Loading.call({
            method: 'udshed.api.course.update_teacher_unit',
            args:{
                teaching_unit_code:teachingUnitCode,
                grid_teacher:[...grid_teacher]
            },
            freeze: true,
            freeze_message: __("Mise à jour de la grille en cours..."),
            callback: function(r) {
                if (r.message) {
                    // Ouvrir l'URL du fichier
                    
                    Udshed.Messages.success(__('Grille mise à jour'));
                    frappe.utils.play_sound("submit");
                    callbackFunction()

                } else {
                    Udshed.Messages.validation(__('Impossible de mettre à jour la grille'), __('Erreur'));
                }
            },
            error: (error) => {
                Udshed.Messages.error(error, __('Impossible de mettre à jour la grille'));
            }
        });
    }
}
