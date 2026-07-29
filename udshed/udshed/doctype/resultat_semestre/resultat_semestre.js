// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.ui.form.on("Resultat Semestre", {

    refresh(frm) {
        frm.set_df_property("mps", "read_only", 1);
        frm.set_df_property("mpc", "read_only", 1);
        frm.set_df_property("total_credits", "read_only", 1);
        frm.set_df_property("credits_obtenus", "read_only", 1);
        frm.set_df_property("mention", "read_only", 1);
        frm.set_df_property("decision", "read_only", 1);

        if (frm.doc.mpc > 0) {
            frm.page.set_indicator_title(__("MPC: {0}", [frm.doc.mpc]));
            if (frm.doc.decision === "Admis") {
                frm.page.set_indicator("green");
            } else if (frm.doc.decision === "Ajourné") {
                frm.page.set_indicator("red");
            } else {
                frm.page.set_indicator("orange");
            }
        }

        if (!frm.is_new() && frm.doc.student && frm.doc.academic_year) {
            frm.add_custom_button(__("Recalculer MPS/MPC"), function() {
                frappe.call({
                    method: "udshed.api.resultat_academique.calculer_et_sauvegarder_mps_mpc",
                    args: {
                        student: frm.doc.student,
                        semestre: frm.doc.semestre,
                        academic_year: frm.doc.academic_year
                    },
                    freeze: true,
                    freeze_message: __("Recalcul en cours..."),
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
    }
});
