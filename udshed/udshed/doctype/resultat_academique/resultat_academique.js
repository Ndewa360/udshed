// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.ui.form.on("Resultat Academique", {

    refresh(frm) {
        frm.set_df_property("note_finale", "read_only", 1);
        frm.set_df_property("note_pct", "read_only", 1);
        frm.set_df_property("grade", "read_only", 1);
        frm.set_df_property("point", "read_only", 1);
        frm.set_df_property("mention", "read_only", 1);
        frm.set_df_property("statut", "read_only", 1);
        frm.set_df_property("est_rattrapage", "read_only", 1);

        if (frm.doc.statut === "Validé") {
            frm.set_indicator("statut", "green");
        } else {
            frm.set_indicator("statut", "red");
        }

        if (frm.doc.decision_annee === "Admis") {
            frm.page.set_indicator_title("Admis");
            frm.page.set_indicator("green");
        } else if (frm.doc.decision_annee === "Ajourné") {
            frm.page.set_indicator_title("Ajourné");
            frm.page.set_indicator("red");
        }

        if (!frm.is_new() && frm.doc.session_normale) {
            frm.add_custom_button __("Recalculer"), function() {
                frappe.call({
                    method: "udshed.api.resultat_academique.calculer_resultat_session",
                    args: {
                        student: frm.doc.student,
                        session_examen: frm.doc.session_normale
                    },
                    freeze: true,
                    freeze_message: __("Recalcul en cours..."),
                    callback(r) {
                        if (r.message && r.message.resultats && r.message.resultats.length) {
                            const premier = r.message.resultats[0];
                            frappe.msgprint({
                                title: __("Résultat recalculé"),
                                indicator: "green",
                                message: __("Note: {0}% | Grade: {1} | {2}",
                                    [premier.note_pct, premier.grade, premier.mention || ""])
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }, __("Actions"));
        }

        if (!frm.is_new() && frm.doc.student && frm.doc.academic_year) {
            frm.add_custom_button __("Résultats Semestre"), function() {
                frappe.call({
                    method: "udshed.api.resultat_academique.calculer_resultat_semestre",
                    args: {
                        student: frm.doc.student,
                        semestre: frm.doc.semestre,
                        academic_year: frm.doc.academic_year
                    },
                    freeze: true,
                    freeze_message: __("Calcul des résultats du semestre..."),
                    callback(r) {
                        if (r.message) {
                            frappe.msgprint({
                                title: __("Résultats Semestre"),
                                indicator: "green",
                                message: __("MPS: {0} | UE validées: {1}/{2}",
                                    [r.message.mps || 0, r.message.ue_validees || 0, r.message.total_ue || 0])
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }, __("Actions"));

            frm.add_custom_button __("Recalculer MPS/MPC"), function() {
                frappe.call({
                    method: "udshed.api.resultat_academique.calculer_et_sauvegarder_mps_mpc",
                    args: {
                        student: frm.doc.student,
                        semestre: frm.doc.semestre,
                        academic_year: frm.doc.academic_year
                    },
                    freeze: true,
                    freeze_message: __("Recalcul MPS/MPC en cours..."),
                    callback(r) {
                        if (r.message) {
                            frappe.msgprint({
                                title: __("MPS/MPC recalculé"),
                                indicator: "green",
                                message: __("MPS: {0} | MPC: {1} | Crédits: {2}/{3}",
                                    [r.message.mps, r.message.mpc,
                                     r.message.credits_obtenus, r.message.total_credits])
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }, __("Actions"));
        }
    },

    student(frm) {
        if (frm.doc.student) {
            frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Student",
                    filters: { name: frm.doc.student },
                    fieldname: ["nom_complet"]
                },
                callback(r) {
                    if (r.message) {
                        frm.set_value("student_name", r.message.nom_complet);
                    }
                }
            });
        }
    }
});
