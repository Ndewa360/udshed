frappe.ui.form.on("Student", {

	refresh(frm) {
		// Afficher le matricule en bleu en haut du formulaire
		if (!frm.is_new()) {
			frm.set_intro(`Matricule : ${frm.doc.name}`, "blue");
		}
	}
});
