// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.ui.form.on("Session Examen Note", {

    refresh(frm) {
        frm.set_df_property("note_cc_moyenne", "read_only", 1);
        frm.set_df_property("note_examen_active", "read_only", 1);
        frm.set_df_property("note_finale", "read_only", 1);
        frm.set_df_property("note_pct", "read_only", 1);
        frm.set_df_property("grade", "read_only", 1);
        frm.set_df_property("point", "read_only", 1);
        frm.set_df_property("mention", "read_only", 1);
        frm.set_df_property("statut", "read_only", 1);

        if (frm.doc.type_ue) {
            afficher_champs_selon_type(frm, frm.doc.type_ue);
        }

        gerer_verrouillage_cc(frm);
        gerer_affichage_rattrapage(frm);
        ajouter_boutons_statut(frm);
    },

    type_ue(frm) {
        afficher_champs_selon_type(frm, frm.doc.type_ue);

        frm.clear_table("notes_cc");
        frm.set_value("note_cc_moyenne", 0);
        frm.set_value("note_examen", 0);
        frm.set_value("note_examen_rattrapage", 0);
        frm.set_value("date_rattrapage", null);
        frm.set_value("note_examen_active", 0);
        frm.set_value("note_tp", 0);
        frm.set_value("note_rapport", 0);
        frm.set_value("note_competence", 0);
        frm.refresh_fields();
    },

    note_examen_rattrapage(frm) {
        if (frm.doc.note_examen_rattrapage > 0 && !frm.doc.date_rattrapage) {
            frm.set_value("date_rattrapage", frappe.datetime.get_today());
        }
        gerer_affichage_rattrapage(frm);
    }

});


function afficher_champs_selon_type(frm, type_ue) {
    frm.set_df_property("notes_cc", "hidden", 1);
    frm.set_df_property("note_examen", "hidden", 1);
    frm.set_df_property("note_examen_rattrapage", "hidden", 1);
    frm.set_df_property("date_rattrapage", "hidden", 1);
    frm.set_df_property("note_tp", "hidden", 1);
    frm.set_df_property("note_rapport", "hidden", 1);
    frm.set_df_property("note_competence", "hidden", 1);

    if (type_ue === "Sans TP") {
        frm.set_df_property("notes_cc", "hidden", 0);
        frm.set_df_property("note_examen", "hidden", 0);
        frm.set_df_property("note_examen_rattrapage", "hidden", 0);
        frm.set_df_property("date_rattrapage", "hidden", 0);
    }
    else if (type_ue === "Avec TP") {
        frm.set_df_property("notes_cc", "hidden", 0);
        frm.set_df_property("note_examen", "hidden", 0);
        frm.set_df_property("note_examen_rattrapage", "hidden", 0);
        frm.set_df_property("date_rattrapage", "hidden", 0);
        frm.set_df_property("note_tp", "hidden", 0);
    }
    else if (type_ue === "Stage SMSB") {
        frm.set_df_property("note_rapport", "hidden", 0);
        frm.set_df_property("note_competence", "hidden", 0);
    }

    frm.refresh_fields();
}


function gerer_verrouillage_cc(frm) {
    let examen_existe = (frm.doc.note_examen && frm.doc.note_examen > 0) ||
                        (frm.doc.note_examen_rattrapage && frm.doc.note_examen_rattrapage > 0);

    frm.set_df_property("notes_cc", "read_only", examen_existe ? 1 : 0);

    if (examen_existe && !frm.is_new()) {
        frm.set_df_property("notes_cc", "description",
            "Notes CC verrouillées — une note d'examen a déjà été enregistrée."
        );
    } else {
        frm.set_df_property("notes_cc", "description", "");
    }
}


function gerer_affichage_rattrapage(frm) {
    let a_rattrapage = frm.doc.note_examen_rattrapage > 0;

    if (a_rattrapage) {
        frm.set_df_property("note_examen_rattrapage", "read_only", 1);
        frm.set_df_property("date_rattrapage", "read_only", 1);
    } else {
        frm.set_df_property("note_examen_rattrapage", "read_only", 0);
        frm.set_df_property("date_rattrapage", "read_only", 0);
    }
}


function ajouter_boutons_statut(frm) {
    if (frm.is_new()) return;

    let statut = frm.doc.statut || "Brouillon";

    if (statut === "Brouillon") {
        frm.add_custom_button(__("Saisir"), function() {
            frm.set_value("statut", "Saisi");
            frm.save();
        }, __("Statut")).addClass("btn-primary-dark");
    }

    if (statut === "Saisi") {
        let roles = frappe.user_roles || [];
        if (roles.includes("System Manager") || roles.includes("Coordonateur")) {
            frm.add_custom_button(__("Valider"), function() {
                frm.set_value("statut", "Validé");
                frm.save();
            }, __("Statut")).addClass("btn-primary");
        }
    }

    if (statut === "Validé") {
        let roles = frappe.user_roles || [];
        if (roles.includes("System Manager")) {
            frm.add_custom_button(__("Publier"), function() {
                frm.set_value("statut", "Publié");
                frm.save();
            }, __("Statut")).addClass("btn-success");
        }
    }
}
