frappe.ui.form.on("Student", {

	refresh(frm) {
		frm.set_df_property("cycle", "read_only", 1);
		frm.set_df_property("nom_complet", "read_only", 1);

		// Afficher le matricule en bleu en haut du formulaire
		if (!frm.is_new()) {
			frm.set_intro(`Matricule : ${frm.doc.name}`, "blue");
		}
	},

	nom(frm) {
		frm.set_value("nom_complet", `${frm.doc.matricule || ""} - ${frm.doc.nom || ""} ${frm.doc.prenom || ""}`.replace(/ - $/, "").replace(/^ - /, "").trim());
	},

	prenom(frm) {
		frm.set_value("nom_complet", `${frm.doc.matricule || ""} - ${frm.doc.nom || ""} ${frm.doc.prenom || ""}`.replace(/ - $/, "").replace(/^ - /, "").trim());
	},

	matricule(frm) {
		frm.set_value("nom_complet", `${frm.doc.matricule || ""} - ${frm.doc.nom || ""} ${frm.doc.prenom || ""}`.replace(/ - $/, "").replace(/^ - /, "").trim());
	},

	niveau(frm) {
		if (!frm.doc.niveau) {
			frm.set_value("cycle", "");
			return;
		}

		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Field of study Level",
				filters: { name: frm.doc.niveau },
				fieldname: "level"
			},
			callback(r) {
				if (r.message && r.message.level) {
					let level = r.message.level;
					let cycle = "";
					if (level.startsWith("Licence")) {
						cycle = "Licence";
					} else if (level.startsWith("Master")) {
						cycle = "Master";
					} else if (level.startsWith("BTS")) {
						cycle = "BTS";
					} else {
						cycle = "Licence";
					}
					frm.set_value("cycle", cycle);
				}
			}
		});
	}
});
