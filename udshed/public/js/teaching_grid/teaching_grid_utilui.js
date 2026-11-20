window.Udshed = window.Udshed || {};
window.Udshed.TeachingGrid = window.Udshed.TeachingGrid || {};
window.Udshed.TeachingGrid.UtilsUi = {
    update_page_actions(filter,btnExporter,btnImporter,canEdit = true) 
    {
        if(!canEdit)
        {
            btnExporter.hide();
            btnImporter.hide();
        }
        else if(this.isValideFilterForGrid(filter))
        {
            btnExporter.show();
            btnImporter.show();
        } else {
            btnExporter.hide();
            btnImporter.hide();
        }
    },

    isValideFilterForGrid(filter)
    {
        return filter.academic_year && filter.faculty && filter.filiere && filter.niveau && filter.semestre;
    },
}
