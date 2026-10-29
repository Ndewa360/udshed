// Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
// For license information, please see license.txt

frappe.ui.form.on("Course", {
    refresh: function (frm) {
        frm.set_value({
            "nombre_dheure_total":parseInt(frm.doc.nombre_dheure_cm) + parseInt(frm.doc.nombre_dheure_tp) 
        })
    },

    filiere(frm) {
        frm.clear_table('course_levels');

        if (!frm.doc.filiere) {
            frm.refresh_field('course_levels');
            return;
        }
 
        // frappe.call({
        //     method: 'frappe.client.get_list',
        //     args: {
        //         doctype: 'Field of study Level',
        //         filters: {
        //             filiere: frm.doc.filiere
        //         },
        //         fields: ['name']
        //     },
        //     callback: function (r) {
        //         if (r.message) {
        //             r.message.forEach(n => {
        //                 let row = frm.add_child('course_levels');
        //                 row.niveau = n.name;
        //             });
        //             frm.refresh_field('course_levels');
        //         }
        //     }
        // });
    }
});
