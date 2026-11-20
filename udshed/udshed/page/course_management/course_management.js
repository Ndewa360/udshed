frappe.require('/assets/udshed/css/course_management.css');

var page = null;
let levelMap = {}; // label => name


// =========================
// Rafraîchissement principal
// =========================
function refresh($cards_container,$empty_state,filters) {
	$cards_container.empty();

	if (!filters.academic_year || !filters.faculty || !filters.filiere) {
		$empty_state.show();
		return;
	}

	$empty_state.hide();
	load_teaching_units($cards_container,filters);
}



// =========================
// Chargement backend
// =========================
function load_teaching_units($cards_container,filters) {
	frappe.call({
		method: 'udshed.api.course.get_teaching_units',
		args: filters,
		freeze: true,
		callback: (r) => {
			const data = r.message || [];
			console.warn("Data to show",data)
			if (!data.length) {
				show_no_data($cards_container);
				return;
			}

			render_cards(data,$cards_container);
		}
	});
}

// =========================
// Chargement de niveau
// =========================
function loadLevels(filiere,niveau_field) {
	if (!filiere) {
		niveau_field.df.options = [];
		niveau_field.refresh();
		return;
	}

	frappe.call({
		method: "udshed.api.course.get_levels_for_field",
		args: { field_of_study: filiere },
		callback: (r) => {
			levelMap = r.message.reduce((acc, curr) => {
				acc[curr.level] = curr.name;
				return acc;
			}, {});
			niveau_field.df.options = r.message.map((value)=>({value:value.name,label:value.level})) || [];
			niveau_field.refresh();
		}
	});
}


// =========================
// Aucun résultat
// =========================
function show_no_data($cards_container) {
	$cards_container.html(`
		<div class="col-12 text-center text-muted" style="padding: 40px;">
			Aucun cours trouvé pour ce contexte.
		</div>
	`);
}

// =========================
// Rendu des cartes
// =========================
function render_cards(teaching_units, $cards_container) {
	$cards_container.empty();

	teaching_units.forEach(tu => {
		const $card = $(`
			<div class="col-md-4">
				<div class="card" style="margin-bottom: 20px;">
					<div class="card-body">
						<h5 class="card-title">
							📘 ${tu.course_title}
						</h5>
						<p class="text-muted">${tu.course_code || ''}</p>

						<hr>

						<strong>🎓 Classes</strong>
						<ul class="small">
							${tu.classes.map(c => `<li>${c}</li>`).join('')}
						</ul>

						<strong>👨‍🏫 Sections</strong>
						<ul class="small">
							${tu.sections.map(s =>
								`<li>${s.type} : ${s.teacher}</li>`
							).join('')}
						</ul>

						<div class="mt-3">
							<button class="btn btn-sm btn-secondary btn-edit">
								Modifier
							</button>
							<button class="btn btn-sm btn-primary btn-planning">
								Voir planning
							</button>
						</div>
					</div>
				</div>
			</div>
		`);

		$card.find('.btn-edit').on('click', () => {
			frappe.set_route('Form', 'Teaching Unit', tu.name);
		});

		$card.find('.btn-planning').on('click', () => {
			frappe.set_route('planning', {
				teaching_unit: tu.name
			});
		});

		$cards_container.append($card);
	});
}

// =========================
// Création Teaching Unit
// =========================
function open_create_teaching_unit_dialog(filters) {
	frappe.new_doc('Teaching Unit', {
		academic_year: filters.academic_year,
		faculty: filters.faculty
	});
}


frappe.pages['course-management'].on_page_load = function(wrapper) {
	page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Cours',
		single_column: true
	});


	// =========================
	// État interne
	// =========================
	let filters = {
		academic_year: null,
		faculty: null,
		filiere: null,
		niveau: null
	};

	// =========================
	// Zone principale
	// =========================
	const $content = $('<div class="course-management-content"></div>').appendTo(page.body);

	const $empty_state = $(`
		<div class="text-muted text-center" style="padding: 60px;">
			<h4>📘 Gestion des cours</h4>
			<p>Sélectionnez une année académique, une faculté et une filiére ainsi que le niveau pour afficher les cours.</p>
		</div>
	`).appendTo($content);

	const $cards_container = $('<div class="row"></div>').appendTo($content);

	// =========================
	// Action principale
	// =========================
	page.set_primary_action(__('Nouveau cours'), () => {
		open_create_teaching_unit_dialog(filters);
	});

	// =========================
	// Filtres
	// =========================
	const academic_year_field = page.add_field({
		label: 'Année académique',
		fieldtype: 'Link',
		fieldname: 'academic_year',
		options: 'Academic Year',
		reqd: 1,
		change() {
			filters.academic_year = this.get_value();
			refresh($cards_container,$empty_state,filters);
		}
	});

	const faculty_field = page.add_field({
		label: 'Faculté',
		fieldtype: 'Link',
		fieldname: 'faculty',
		options: 'Faculty',
		reqd: 1,
		change() {
			filters.faculty = this.get_value();
			filters.filiere = null;
			filters.niveau = null;

			filiere_field.set_value(null);
			niveau_field.set_value(null);
			refresh($cards_container,$empty_state,filters);
		}
	});

	const filiere_field = page.add_field({
		label: 'Filière',
		fieldtype: 'Link',
		fieldname: 'filiere',
		options: 'Field of study',
		reqd: 1,
		get_query() {
			if (!faculty_field.get_value()) {
				return {};
			}

			return {
				filters: {
					faculte: faculty_field.get_value()
				}
			};
		},
		change() {

			filters.filiere = this.get_value();
			filters.niveau = null;
			niveau_field.set_value(null);

			loadLevels(this.get_value(),niveau_field);
			refresh($cards_container,$empty_state,filters);
		}
	});

	const niveau_field = page.add_field({

		label: 'Niveau',
		fieldtype: 'Select',
		fieldname: 'niveau',
		change() {
			filters.niveau = this.get_value() || null;
			refresh($cards_container,$empty_state,filters);
		}
	});

	// =========================
	// Initial
	// =========================
	refresh($cards_container,$empty_state,filters);



}