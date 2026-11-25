// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

// Correction motivée d'une note (année close, réclamation après publication) :
// l'enseignant demande, la coordination approuve ; voir udshed/utils/correction_note.py.
function ajouter_bouton_correction(frm) {
    if (frm.is_new()) return;
    frm.add_custom_button(__("Demander une correction"), () => {
        frappe.call({
            method: "udshed.utils.correction_note.composantes_de_la_note",
            args: { note: frm.doc.name },
        }).then((r) => {
            const info = r.message || {};
            const champs = (info.lignes || []).map((l) => ({
                fieldtype: "Float", fieldname: l.champ.replace(":", "_"), label: `${l.composante} (actuelle : ${l.valeur ?? "—"})`,
                default: l.valeur, description: l.champ,
            }));
            const d = new frappe.ui.Dialog({
                title: __("Correction de la note"),
                fields: [
                    { fieldtype: "HTML", options: `<p class="text-muted">${__("Note finale actuelle : {0}/20. Modifiez uniquement les composantes à corriger.", [info.note_finale ?? "—"])}</p>` },
                    ...champs,
                    { fieldtype: "Section Break" },
                    { fieldtype: "Select", fieldname: "motif_type", label: __("Type de motif"), reqd: 1,
                      options: ["Réclamation de l'étudiant", "Erreur de saisie", "Décision du jury", "Autre"] },
                    { fieldtype: "Small Text", fieldname: "motif", label: __("Motif détaillé"), reqd: 1 },
                ],
                primary_action_label: info.peut_approuver ? __("Corriger") : __("Envoyer la demande"),
                primary_action(v) {
                    const lignes = (info.lignes || [])
                        .filter((l) => v[l.champ.replace(":", "_")] !== l.valeur)
                        .map((l) => ({ champ: l.champ, nouvelle_valeur: v[l.champ.replace(":", "_")] }));
                    if (!lignes.length) {
                        frappe.msgprint(__("Aucune note n'a été modifiée."));
                        return;
                    }
                    frappe.call({
                        method: "udshed.utils.correction_note.demander_correction",
                        args: { note: frm.doc.name, lignes, motif_type: v.motif_type, motif: v.motif },
                        freeze: true,
                    }).then((res) => {
                        d.hide();
                        const m = res.message || {};
                        frappe.msgprint(m.statut === "Appliquée"
                            ? __("Correction {0} appliquée.", [m.name])
                            : __("Demande {0} envoyée : elle sera appliquée après approbation.", [m.name]));
                        frm.reload_doc();
                    });
                },
            });
            d.show();
        });
    });
}

frappe.ui.form.on("Session Examen Note", {

    refresh(frm) {
        verrouiller_champs_calcules(frm);
        afficher_champs_selon_type(frm, frm.doc.type_ue);
        gerer_verrouillage_cc(frm);
        gerer_affichage_rattrapage(frm);
        verrouiller_si_session_publiee(frm);
        ajouter_boutons_statut(frm);
        ajouter_bouton_correction(frm);
    },

    type_ue(frm) {
        afficher_champs_selon_type(frm, frm.doc.type_ue);
    },

    note_examen_rattrapage(frm) {
        if (frm.doc.note_examen_rattrapage > 0 && !frm.doc.date_rattrapage) {
            frm.set_value("date_rattrapage", frappe.datetime.get_today());
        }
        gerer_affichage_rattrapage(frm);
    }

});

function verrouiller_champs_calcules(frm) {
    ["note_cc_moyenne", "note_examen_active", "note_finale",
     "note_pct", "grade", "point", "mention"].forEach(function(fieldname) {
        frm.set_df_property(fieldname, "read_only", 1);
    });
}

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

    frm.set_df_property("note_examen_rattrapage", "read_only", a_rattrapage ? 1 : 0);
    frm.set_df_property("date_rattrapage", "read_only", a_rattrapage ? 1 : 0);
}

function verrouiller_si_session_publiee(frm) {
    if (!frm.doc.session_examen || frm.is_new()) {
        return;
    }
    frappe.db.get_value("Session Examen", frm.doc.session_examen, "statut", function(r) {
        if (r && r.statut === "Publiée" && !frm.is_new()) {
            frm.set_df_property("notes_cc", "read_only", 1);
            frm.set_df_property("note_examen", "read_only", 1);
            frm.set_df_property("note_examen_rattrapage", "read_only", 1);
            frm.set_df_property("date_rattrapage", "read_only", 1);
            frm.set_df_property("note_tp", "read_only", 1);
            frm.set_df_property("note_rapport", "read_only", 1);
            frm.set_df_property("note_competence", "read_only", 1);
            frappe.show_alert({
                message: __("Session publiée — notes verrouillées."),
                indicator: "red"
            }, 5);
        }
    });
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
