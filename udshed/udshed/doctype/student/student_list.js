// Filtres de la liste des étudiants : filière et cycle sont des filtres
// standards (champs du dossier) ; année académique et niveau sont calculés
// à partir des inscriptions / réinscriptions (le dossier n'a pas d'année).
const UDSHED_NIVEAUX = [
	"Licence 1", "Licence 2", "Licence 3", "BTS 1", "BTS 2", "Master 1", "Master 2",
	"Doctorat 1", "Doctorat 2", "Doctorat 3", "Doctorat 4", "Doctorat 5", "Doctorat 6", "Doctorat 7",
];

frappe.listview_settings["Student"] = {
	onload(listview) {
		const etat = { annee: null, niveau: null };

		const appliquer = () => {
			if (!etat.annee && !etat.niveau) {
				listview.filter_area.remove("name");
				return;
			}
			frappe.call({
				method: "udshed.udshed.doctype.student.student.etudiants_par_annee",
				args: { academic_year: etat.annee, niveau: etat.niveau },
			}).then((r) => {
				const matricules = r.message || [];
				listview.filter_area.remove("name").then(() =>
					// Liste vide : valeur impossible pour n'afficher aucun étudiant
					listview.filter_area.add([["Student", "name", "in", matricules.length ? matricules : ["__aucun__"]]])
				);
			});
		};

		// Contrôles créés hors de page.add_field : les champs de page.fields_dict
		// sont lus comme filtres sur des colonnes de Student, qui n'existent pas ici.
		const $zone = listview.page.page_form.find(".standard-filter-section");
		const controle = (df, cle) => {
			const $wrap = $('<div class="form-group frappe-control input-max-width col-md-2"></div>').appendTo($zone);
			const ctrl = frappe.ui.form.make_control({
				parent: $wrap,
				df: {
					...df,
					placeholder: df.label,
					onchange() {
						const valeur = ctrl.get_value() || null;
						if (valeur === etat[cle]) return;
						etat[cle] = valeur;
						appliquer();
					},
				},
				render_input: true,
				only_input: true,
			});
			ctrl.refresh();
			return ctrl;
		};

		controle({ fieldtype: "Link", fieldname: "udshed_annee", label: __("Année académique"), options: "Academic Year" }, "annee");
		controle({ fieldtype: "Select", fieldname: "udshed_niveau", label: __("Niveau"), options: [{ value: "", label: __("Niveau") }, ...UDSHED_NIVEAUX] }, "niveau");
	},
};
