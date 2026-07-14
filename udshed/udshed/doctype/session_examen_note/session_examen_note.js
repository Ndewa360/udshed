// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Session Examen Note", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("Session Examen Note", {

    // Déclenché à chaque ouverture du formulaire
    refresh(frm) {
        // Rendre les champs résultats non modifiables visuellement
        frm.set_df_property("note_finale", "read_only", 1);
        frm.set_df_property("note_pct", "read_only", 1);
        frm.set_df_property("grade", "read_only", 1);
        frm.set_df_property("point", "read_only", 1);

        // Appliquer la visibilité des champs selon le type_ue actuel
        if (frm.doc.type_ue) {
            afficher_champs_selon_type(frm, frm.doc.type_ue);
        }
    },

    // Déclenché quand l'utilisateur change le type_ue
    type_ue(frm) {
        afficher_champs_selon_type(frm, frm.doc.type_ue);

        // Vider les notes quand on change de type
        frm.set_value("note_cc", 0);
        frm.set_value("note_examen", 0);
        frm.set_value("note_tp", 0);
        frm.set_value("note_rapport", 0);
        frm.set_value("note_competence", 0);
    }

});


function afficher_champs_selon_type(frm, type_ue) {

    // Par défaut on cache tout
    frm.set_df_property("note_cc", "hidden", 1);
    frm.set_df_property("note_examen", "hidden", 1);
    frm.set_df_property("note_tp", "hidden", 1);
    frm.set_df_property("note_rapport", "hidden", 1);
    frm.set_df_property("note_competence", "hidden", 1);

    if (type_ue === "Sans TP") {
        frm.set_df_property("note_cc", "hidden", 0);
        frm.set_df_property("note_examen", "hidden", 0);
    }
    else if (type_ue === "Avec TP") {
        frm.set_df_property("note_cc", "hidden", 0);
        frm.set_df_property("note_examen", "hidden", 0);
        frm.set_df_property("note_tp", "hidden", 0);
    }
    else if (type_ue === "Stage SMSB") {
        frm.set_df_property("note_rapport", "hidden", 0);
        frm.set_df_property("note_competence", "hidden", 0);
    }

    // Rafraîchir l'affichage
    frm.refresh_fields();
}