frappe.ui.form.on("Session Examen Note", {

    refresh(frm) {
        frm.set_df_property("note_cc", "read_only", 1);
        frm.set_df_property("note_finale", "read_only", 1);
        frm.set_df_property("note_pct", "read_only", 1);
        frm.set_df_property("grade", "read_only", 1);
        frm.set_df_property("point", "read_only", 1);
        frm.set_df_property("mention", "read_only", 1);
        frm.set_df_property("statut", "read_only", 1);
        frm.set_df_property("statut_color", "read_only", 1);

        if (frm.doc.type_ue) {
            afficher_champs_selon_type(frm, frm.doc.type_ue);
        }

        gerer_verrouillage_cc(frm);
        gerer_affichage_rattrapage(frm);
        ajouter_boutons_statut(frm);
        filtrer_par_enseignant(frm);
    },

    type_ue(frm) {
        afficher_champs_selon_type(frm, frm.doc.type_ue);

        frm.set_value("note_cc", 0);
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
    let champs = ["note_examen", "note_examen_rattrapage", "date_rattrapage",
                   "note_tp", "note_rapport", "note_competence"];

    champs.forEach(c => frm.set_df_property(c, "hidden", 1));

    if (type_ue === "Sans TP") {
        frm.set_df_property("note_examen", "hidden", 0);
        frm.set_df_property("note_examen_rattrapage", "hidden", 0);
        frm.set_df_property("date_rattrapage", "hidden", 0);
    } else if (type_ue === "Avec TP") {
        frm.set_df_property("note_examen", "hidden", 0);
        frm.set_df_property("note_examen_rattrapage", "hidden", 0);
        frm.set_df_property("date_rattrapage", "hidden", 0);
        frm.set_df_property("note_tp", "hidden", 0);
    } else if (type_ue === "Stage SMSB") {
        frm.set_df_property("note_rapport", "hidden", 0);
        frm.set_df_property("note_competence", "hidden", 0);
    }

    frm.refresh_fields();
}


function gerer_verrouillage_cc(frm) {
    let examen_existe = (frm.doc.note_examen && frm.doc.note_examen > 0) ||
                        (frm.doc.note_examen_rattrapage && frm.doc.note_examen_rattrapage > 0);

    frm.set_df_property("note_cc", "read_only", examen_existe ? 1 : 0);

    if (examen_existe && !frm.is_new()) {
        frm.set_df_property("note_cc", "description",
            "Note CC verrouillée — une note d'examen a déjà été enregistrée."
        );
    } else {
        frm.set_df_property("note_cc", "description", "");
    }
}


function gerer_affichage_rattrapage(frm) {
    let a_rattrapage = frm.doc.note_examen_rattrapage > 0;

    frm.set_df_property("note_examen_rattrapage", "read_only", a_rattrapage ? 1 : 0);
    frm.set_df_property("date_rattrapage", "read_only", a_rattrapage ? 1 : 0);
}


function ajouter_boutons_statut(frm) {
    if (frm.is_new()) return;

    let statut = frm.doc.statut || "Brouillon";
    let roles = frappe.user_roles || [];
    let is_coordo = roles.includes("System Manager") || roles.includes("Coordonateur");
    let is_admin = roles.includes("System Manager");

    frm.remove_custom_button("", "Statut");

    if (statut === "Brouillon") {
        frm.add_custom_button(__("Saisir"), function() {
            frm.set_value("statut", "Saisi");
            frm.save();
        }, __("Statut")).addClass("btn-primary-dark");
    }

    if (statut === "Saisi" && is_coordo) {
        frm.add_custom_button(__("Valider"), function() {
            frm.set_value("statut", "Validé");
            frm.save();
        }, __("Statut")).addClass("btn-primary");
    }

    if (statut === "Validé" && is_admin) {
        frm.add_custom_button(__("Publier"), function() {
            frm.set_value("statut", "Publié");
            frm.save();
        }, __("Statut")).addClass("btn-success");
    }
}


function filtrer_par_enseignant(frm) {
    if (frm.is_new() && !frappe.user_roles.includes("System Manager")) {
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Teacher",
                filters: {
                    email: frappe.session.user_email
                },
                fields: ["name"]
            },
            callback(r) {
                if (r.message && r.message.length > 0) {
                    let teacher_name = r.message[0].name;
                    frappe.call({
                        method: "udshed.api.user_data.get_teacher_ues",
                        args: { teacher: teacher_name },
                        callback(res) {
                            if (res.message) {
                                frm.set_query("teaching_unit", function() {
                                    return {
                                        filters: {
                                            name: ["in", res.message]
                                        }
                                    };
                                });
                            }
                        }
                    });
                }
            }
        });
    }
}
