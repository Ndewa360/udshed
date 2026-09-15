frappe.ready(function() {
	// ---- Style personnalisé — reproduit la structure de la page « Choix du candidat » ----
	const STYLE = `
		:root {
			--udshed-primary: #003B6F;
			--udshed-primary-dark: #003B6F;
			--udshed-accent: #F08000;
			--udshed-bg-soft: #ffffff;
			--udshed-border: #cbd9e8;
			--udshed-radius: 16px;
		}

		/* Fond de page — inspiré de la page « Choix du candidat » */
		.web-page-content, body {
			background: linear-gradient(180deg, #EAF1F8 0%, #d8e6f5 100%) !important;
			font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
		}

		/* Conteneur principal (= main-wrapper) */
		.web-form-container {
			max-width: 1000px !important;
			width: 100%;
			margin: 0 auto;
			padding: 2rem 1rem;
		}

		/* Masque l'en-tête natif de la web-form */
		.web-form-header {
			display: none !important;
		}

		/* Étapes (step-header) — pastilles rondes numérotées */
		.step-header {
			display: flex;
			justify-content: center;
			align-items: center;
			gap: 15px;
			margin-bottom: 2rem;
		}
		.step-header .step-item {
			display: flex;
			align-items: center;
			gap: 8px;
			font-size: 14px;
			color: #a6b7cc;
			font-weight: 500;
		}
		.step-header .step-item.active {
			color: #F08000;
			font-weight: 700;
		}
		.step-header .step-number {
			width: 28px;
			height: 28px;
			border-radius: 50%;
			background-color: #cbd9e8;
			color: #6b7a90;
			display: flex;
			align-items: center;
			justify-content: center;
			font-size: 13px;
			font-weight: 600;
		}
		.step-header .step-item.active .step-number {
			background: linear-gradient(135deg, #F08000, #ff9f3d);
			color: #ffffff;
			box-shadow: 0 4px 10px rgba(240,128,0,0.35);
		}
		.step-header .step-line {
			height: 3px;
			border-radius: 2px;
			background: linear-gradient(90deg, #cbd9e8, #F08000);
			width: 80px;
		}

		/* Carte principale (form-card) */
		.web-form .web-form-body {
			background: #ffffff;
			border-radius: var(--udshed-radius);
			border: 1px solid #cbd9e8;
			border-top: 5px solid #F08000;
			padding: 3rem;
			box-shadow: 0 6px 18px rgba(0, 59, 111, 0.08);
		}

		/* Titre de la carte */
		.form-card-title {
			display: inline-block;
			font-weight: 800;
			color: #003B6F;
			font-size: 22px;
			margin: 0 0 10px 0;
			text-align: left;
			padding-bottom: 8px;
			border-bottom: 3px solid #F08000;
		}
		.form-card-subtitle {
			color: #6b7280;
			font-size: 14px;
			margin: 0 0 22px 0;
			text-align: left;
		}

		/* Sections : grille de champs sur 2 colonnes, sans fond de section */
		.web-form .web-form-section {
			display: grid;
			grid-template-columns: repeat(2, 1fr);
			gap: 18px 24px;
			background: transparent;
			border: none;
			border-radius: 0;
			padding: 0;
			margin-bottom: 8px;
		}
		.web-form .web-form-section .frappe-control {
			grid-column: auto;
		}
		/* Champs pleine largeur */
		.web-form .web-form-section .frappe-control[data-fieldtype="Table"],
		.web-form .web-form-section .frappe-control[data-fieldtype="Attach"],
		.web-form .web-form-section .frappe-control[data-fieldtype="Text"],
		.web-form .web-form-section .frappe-control[data-fieldtype="Long Text"],
		.web-form .web-form-section .frappe-control[data-fieldtype="Small Text"],
		.web-form .web-form-section .frappe-control[data-fieldtype="Section Break"],
		.web-form .web-form-section .frappe-control[data-fieldtype="Column Break"],
		.web-form .web-form-section .frappe-control[data-fieldname="choix_de_formation"],
		.web-form .web-form-section .frappe-control[data-fieldname="diplome_formation"] {
			grid-column: 1 / -1;
		}

		/* Libellés des contrôles */
		.web-form .frappe-control .control-label {
			font-size: 14px;
			font-weight: 700;
			color: #003B6F;
			margin-bottom: 6px;
		}

		/* Champs (inputs / selects) */
		.web-form .form-control,
		.web-form .input-group .form-control {
			background-color: #EAF1F8 !important;
			border: 1px solid #cbd9e8 !important;
			border-radius: 10px !important;
			padding: 14px 16px !important;
			font-size: 15px !important;
			color: #003B6F !important;
			color-scheme: light !important;
			transition: all 0.2s ease;
		}
		.web-form .form-control::placeholder {
			color: #94a3b8;
		}
		.web-form .form-control:focus {
			border-color: #1f6feb !important;
			box-shadow: 0 0 0 3px rgba(31,111,235,0.15) !important;
			background-color: #ffffff !important;
			color: #003B6F !important;
		}
		.web-form select,
		.web-form select.form-control,
		.web-form .form-group select,
		.web-form .control-input select,
		.web-form input[type="file"] {
			background-color: #EAF1F8 !important;
			color: #003B6F !important;
			-webkit-text-fill-color: #003B6F !important;
			opacity: 1 !important;
		}
		.web-form select option,
		.web-form select.form-control option,
		.web-form .form-group select option {
			color: #003B6F !important;
			-webkit-text-fill-color: #003B6F !important;
			background-color: #ffffff !important;
			opacity: 1 !important;
		}
		.web-form select.form-control:focus,
		.web-form .form-group select:focus {
			background-color: #ffffff !important;
			color: #003B6F !important;
			-webkit-text-fill-color: #003B6F !important;
		}
		/* Le select native de Frappe reste actif : on s'assure qu'il ne soit pas masqué
		   et que sa sélection soit bien visible (le menu s'ouvre et les options s'affichent) */
		.web-form select.form-control,
		.web-form .form-group select {
			opacity: 1 !important;
			visibility: visible !important;
			display: inline-block;
		}
		.web-form .control-input {
			position: relative;
		}

		/* Tableaux (Choix de formation / Diplômes) */
		.web-form .frappe-control[data-fieldtype="Table"] .grid,
		.web-form .frappe-control[data-fieldtype="Table"] .form-grid {
			border: 1px solid var(--udshed-border);
			border-radius: 10px;
			overflow: hidden;
		}
		.web-form .frappe-control[data-fieldtype="Table"] .grid-heading-row {
			background: #EAF1F8;
			border-bottom: 1px solid #cbd9e8;
		}
		.web-form .frappe-control[data-fieldtype="Table"] .grid-heading-row .grid-static-col {
			color: #3d5877;
			font-weight: 700;
			font-size: 12px;
			text-transform: uppercase;
			letter-spacing: 0.3px;
		}
		.web-form .frappe-control[data-fieldtype="Table"] .grid-row {
			border-top: 1px solid var(--udshed-border);
		}
		.web-form .frappe-control[data-fieldtype="Table"] .grid-add-row,
		.web-form .frappe-control[data-fieldtype="Table"] .grid-remove-rows {
			margin-top: 8px;
		}

		/* Rubriques tableau — Choix de formation & Diplômes : bannière bien visible */
		.web-form .frappe-control[data-fieldname="choix_de_formation"] .control-label,
		.web-form .frappe-control[data-fieldname="diplome_formation"] .control-label {
			display: flex;
			align-items: center;
			gap: 10px;
			width: 100%;
			background: linear-gradient(90deg, #003B6F 0%, #1f6feb 100%);
			color: #ffffff !important;
			font-size: 15px !important;
			font-weight: 800 !important;
			text-transform: uppercase;
			letter-spacing: 0.5px;
			padding: 13px 16px;
			border-radius: 10px 10px 0 0;
			margin: 0;
			box-shadow: 0 4px 10px rgba(0, 59, 111, 0.15);
		}
		.web-form .frappe-control[data-fieldname="choix_de_formation"] .control-label::before,
		.web-form .frappe-control[data-fieldname="diplome_formation"] .control-label::before {
			content: "▸";
			color: #F08000;
			font-size: 16px;
			line-height: 1;
		}
		.web-form .frappe-control[data-fieldname="choix_de_formation"] .grid,
		.web-form .frappe-control[data-fieldname="diplome_formation"] .grid {
			border-top-left-radius: 0;
			border-top-right-radius: 0;
			border: 2px solid #cbd9e8;
			border-top: none;
			box-shadow: 0 4px 12px rgba(0, 59, 111, 0.08);
		}

		/* Boutons — fond noir, alignés à droite (style page « Choix du candidat ») */
		.web-form .btn-primary,
		.web-form .btn-next,
		.web-form .btn-sm-primary {
			display: inline-flex;
			align-items: center;
			justify-content: center;
			gap: 10px;
			padding: 12px 35px;
			font-size: 15px;
			font-weight: 600;
			border-radius: 10px;
			border: none;
			cursor: pointer;
			color: #fff;
			background: linear-gradient(135deg, #003B6F 0%, #1f6feb 100%);
			box-shadow: 0 4px 12px rgba(0, 59, 111, 0.25);
			transition: transform 0.15s ease, box-shadow 0.2s ease, background 0.2s ease;
		}
		.web-form .btn-primary:hover,
		.web-form .btn-next:hover,
		.web-form .btn-sm-primary:hover {
			background: #1f6feb;
			transform: translateY(-2px);
			box-shadow: 0 8px 16px -4px rgba(0, 0, 0, 0.18);
			color: #fff;
		}
		.web-form .btn-primary:active,
		.web-form .btn-next:active,
		.web-form .btn-sm-primary:active {
			transform: translateY(0);
		}
		.web-form .btn-primary:disabled,
		.web-form .btn-next:disabled {
			opacity: 0.7;
			cursor: not-allowed;
			transform: none;
		}
		.web-form .btn-secondary,
		.web-form .btn-previous {
			padding: 12px 30px;
			border-radius: 10px;
			font-size: 15px;
			font-weight: 600;
			color: #003B6F;
			background: #ffffff;
			border: 1px solid #003B6F;
			transition: transform 0.15s ease, box-shadow 0.2s ease, background 0.2s ease;
		}
		.web-form .btn-secondary:hover,
		.web-form .btn-previous:hover {
			background: #EAF1F8;
			color: #F08000;
			border-color: #F08000;
			transform: translateY(-2px);
			box-shadow: 0 6px 16px -6px rgba(0, 59, 111, 0.2);
		}

		/* Documents (pièces jointes) */
		.web-form .attach-missing {
			color: var(--udshed-accent);
		}

		/* Pied de formulaire — boutons alignés à droite (bouton « Continuer ») */
		.web-form .web-form-footer {
			margin-top: 8px;
		}
		.web-form .web-form-footer .web-form-actions {
			display: flex;
			justify-content: flex-end;
			align-items: center;
		}
		.web-form .web-form-footer .center-area.paging {
			display: flex;
			gap: 16px;
			justify-content: flex-end;
			margin-top: 0;
			padding-top: 20px;
			border-top: 0;
		}
		.web-form .web-form-footer .paging .btn + .btn {
			margin-left: 0;
		}

		/* Titre d'étape secondaire en bas */
		.web-form .web-form-step-title {
			color: #F08000 !important;
			font-weight: 700;
			letter-spacing: 0.5px;
		}

		/* Téléphone : badge +237 fixe à gauche, le numéro s'affiche à sa suite.
		   Les champs sont en Data (le contrôle Phone natif peut ne pas s'afficher
		   dans un web form), on ajoute le badge par JS. */
		.web-form .control-input.ud-tel-host {
			position: relative;
		}
		.web-form .control-input.ud-tel-host input {
			padding-left: 66px !important;
			padding-right: 16px !important;
		}
		.web-form .ud-tel-badge {
			position: absolute;
			top: 1px;
			left: 1px;
			bottom: 1px;
			z-index: 2;
			display: flex;
			align-items: center;
			min-width: 60px;
			padding: 0 10px;
			background-color: #EAF1F8;
			border-radius: 10px 0 0 10px;
			border-right: 1px solid #cbd9e8;
			font-size: 14px;
			font-weight: 700;
			color: #003B6F;
			pointer-events: none;
			user-select: none;
		}

		/* Responsive */
		@media (max-width: 768px) {
			.web-form .web-form-section { grid-template-columns: 1fr; }
			.web-form .web-form-body { padding: 20px 16px; }
			.step-header { gap: 8px; }
			.step-header .step-line { width: 40px; }
		}
	`;
	const styleEl = document.createElement('style');
	styleEl.type = 'text/css';
	styleEl.textContent = STYLE;
	document.head.appendChild(styleEl);

	// ---- Structure : pas-header (pastilles) + carte blanche, style page « Choix du candidat » ----
	const ETAPES = [
		'Candidature',
		'Informations personnelles',
		'Documents'
	];

	function construireStepHeader() {
		if (document.querySelector('.step-header')) return;
		const corps = document.querySelector('.web-form .web-form-body');
		if (!corps) return;

		const entete = document.createElement('div');
		entete.className = 'step-header';
		ETAPES.forEach(function (nom, idx) {
			if (idx > 0) {
				const ligne = document.createElement('div');
				ligne.className = 'step-line';
				entete.appendChild(ligne);
			}
			const item = document.createElement('div');
			item.className = 'step-item' + (idx === 0 ? ' active' : '');
			item.dataset.step = idx;
			item.innerHTML = '<span class="step-number">' + (idx + 1) + '</span>' + nom;
			entete.appendChild(item);
		});

		corps.parentNode.insertBefore(entete, corps);
	}

	function mettreAJourStepActive(index) {
		document.querySelectorAll('.step-header .step-item').forEach(function (item) {
			var actif = parseInt(item.dataset.step, 10) === index;
			if (actif) {
				item.classList.add('active');
			} else {
				item.classList.remove('active');
			}
		});
	}

	// Petit délai pour être certain que le squelette de la web-form est rendu
	let compteurStructure = 0;
	function revelerFormulaire() {
		if (document.body.classList.contains('udshed-formed')) return;
		document.body.classList.add('udshed-formed');
	}
	const intervalStructure = setInterval(function () {
		// Le step-header doit être construit et le titre copié une seule fois
		if (!document.querySelector('.form-card-title')) {
			const corps = document.querySelector('.web-form .web-form-body');
			const titreNat = document.querySelector('.web-form .web-form-title h1');
			const introNat = document.querySelector('.web-form .web-form-introduction');
			if (corps && titreNat) {
				const titre = document.createElement('h3');
				titre.className = 'form-card-title';
				titre.textContent = (titreNat.textContent || '').trim() || 'Dépôt de candidature';
				corps.insertBefore(titre, corps.firstChild);
				if (introNat && (introNat.textContent || '').trim()) {
					const sous = document.createElement('p');
					sous.className = 'form-card-subtitle';
					sous.textContent = introNat.textContent.trim();
					titre.after(sous);
				}
			}
		}
		construireStepHeader();
		if (document.querySelector('.step-header') && document.querySelector('.form-card-title')) {
			revelerFormulaire();
			clearInterval(intervalStructure);
			return;
		}
		compteurStructure++;
		if (compteurStructure > 40) {
			clearInterval(intervalStructure);
			revelerFormulaire();
		}
	}, 200);
	// Sécurité : ne jamais laisser le formulaire masqué
	window.addEventListener('load', revelerFormulaire);

	// ---- Menus déroulants (niveau / sexe / centre d'examen) : forcer le texte visible ----
	// Correctif inspiré de la page « Choix du candidat » : dans Frappe v16 le texte
	// sélectionné des <select> peut s'afficher en transparent/blanc.
	function forcerCouleurSelects() {
		document.querySelectorAll('.web-form select.form-control, .web-form .form-group select').forEach(function (select) {
			select.style.setProperty('color', '#003B6F', 'important');
			select.style.setProperty('-webkit-text-fill-color', '#003B6F', 'important');
			select.style.setProperty('background-color', '#EAF1F8', 'important');
			if (select.value !== '') {
				select.style.setProperty('opacity', '1', 'important');
			}
			select.addEventListener('change', function () {
				this.style.setProperty('color', '#003B6F', 'important');
				this.style.setProperty('-webkit-text-fill-color', '#003B6F', 'important');
				this.style.setProperty('opacity', '1', 'important');
			});
		});
	}
	document.addEventListener('DOMContentLoaded', forcerCouleurSelects);
	window.addEventListener('load', forcerCouleurSelects);
	const intervalSelects = setInterval(function () {
		forcerCouleurSelects();
	}, 500);
	setTimeout(function () { clearInterval(intervalSelects); }, 8000);

	// ---- Options toujours affichées au clic : niveau / sexe / centre d'examen ----
	// Frappe v16 peut rendre le texte des <option> transparent ; on force un
	// <select> natif avec des options visibles pour ces trois champs.
	const OPTIONS_DE_REPLI = {
		'niveau': [
			'Sélectionner le niveau',
			'BTS 1', 'BTS 2',
			'Licence 1', 'Licence 2', 'Licence 3',
			'Master 1', 'Master 2'
		],
		'sexe': ['Sélectionner', 'Homme', 'Femme'],
		'examination_centre': ['Sélectionner', 'Bangangté', 'Bafoussam', 'Yaoundé', 'Douala']
	};

	function garantirOptionsSelects() {
		Object.keys(OPTIONS_DE_REPLI).forEach(function (fieldname) {
			var champ = frappe.web_form.fields_dict[fieldname];
			if (!champ || !champ.df) return;
			// niveau : le champ dynamique (filière) gère les options
			if (fieldname === 'niveau' && frappe.web_form.get_value('filiere')) return;
			champ.df.options = OPTIONS_DE_REPLI[fieldname].join('\n');
			if (champ.refresh) champ.refresh();
		});
	}
	document.addEventListener('DOMContentLoaded', garantirOptionsSelects);
	window.addEventListener('load', garantirOptionsSelects);
	const intervalOptions = setInterval(garantirOptionsSelects, 500);
	setTimeout(function () { clearInterval(intervalOptions); }, 8000);

	// ---- Téléphones : badge +237 fixe à gauche, le numéro s'affiche à sa suite ----
	function installerChampsTelephone() {
		['phone', 'parent_phone'].forEach(function (fieldname) {
			var $ctrl = document.querySelector(
				'.web-form .frappe-control[data-fieldname="' + fieldname + '"]'
			);
			if (!$ctrl || $ctrl.querySelector('.ud-tel-badge')) return;
			var $col = $ctrl.querySelector('.control-input');
			if (!$col) return;
			var $input = $col.querySelector('input');
			if (!$input) return;

			// Badge "+237" inséré à gauche du champ de saisie
			var $badge = document.createElement('span');
			$badge.className = 'ud-tel-badge';
			$badge.setAttribute('aria-hidden', 'true');
			$badge.textContent = '+237';
			$col.insertBefore($badge, $input);
			$col.classList.add('ud-tel-host');

			// On n'affiche que les chiffres (le code pays reste dans la valeur)
			var brut = $input.value || '';
			$input.value = brut.replace(/^(\+?237|00237)[\s-]*/, '').replace(/\D/g, '');

			$input.addEventListener('input', function () {
				var v = ($input.value || '').replace(/\D/g, '');
				if ($input.value !== v) $input.value = v;
			});
		});
	}
	document.addEventListener('DOMContentLoaded', installerChampsTelephone);
	window.addEventListener('load', installerChampsTelephone);
	const intervalTel = setInterval(installerChampsTelephone, 500);
	setTimeout(function () { clearInterval(intervalTel); }, 8000);

	// Ajoute "+237-" devant chaque numéro juste avant la validation/soumission.
	// Le web form soumet la valeur des inputs : on met donc l'input à jour de façon
	// synchrone pendant la validation (get_values est lu juste après validate()).
	function prefixerPhones() {
		['phone', 'parent_phone'].forEach(function (fieldname) {
			var champ = frappe.web_form.fields_dict[fieldname];
			if (!champ) return;
			var brut = champ.get_input_value ? champ.get_input_value() : '';
			var numeros = String(brut || '')
				.replace(/^(\+?237|00237)[\s-]*/, '')
				.replace(/\D/g, '');
			var valeur = numeros ? '+237-' + numeros : null;
			if (champ.set_input) champ.set_input(valeur || '');
			if (champ.set_value) champ.set_value(valeur);
		});
	}

	// ---- Configuration ----
	const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
	const ALLOWED_TYPES = {
		'birth_certificate': ['application/pdf', 'image/jpeg', 'image/png'],
		'access_diploma_copy': ['application/pdf', 'image/jpeg', 'image/png'],
		'id_photo': ['image/jpeg', 'image/png'],
		'remittance_receipt': ['application/pdf', 'image/jpeg', 'image/png']
	};

	// ---- Auto-format full_name ----
	function updateFullName() {
		const first = frappe.web_form.get_value('first_name') || '';
		const last = frappe.web_form.get_value('last_name') || '';
		if (first || last) {
			frappe.web_form.set_value('full_name', (first + ' ' + last).trim());
		}
	}

	['first_name', 'last_name'].forEach(field => {
		const input = document.querySelector(`[data-fieldname="${field}"] input`);
		if (input) {
			input.addEventListener('input', updateFullName);
			input.addEventListener('blur', updateFullName);
		}
	});

	// ---- File validation ----
	function validateFile(fieldname, file) {
		const allowed = ALLOWED_TYPES[fieldname];
		if (!allowed) return true;

		if (file.size > MAX_FILE_SIZE) {
			frappe.msgprint({
				title: 'Fichier trop volumineux',
				message: `Le fichier "${file.name}" dépasse la taille maximale de 10 Mo.`,
				indicator: 'red'
			});
			return false;
		}

		if (!allowed.includes(file.type)) {
			frappe.msgprint({
				title: 'Type de fichier non autorisé',
				message: `Le fichier "${file.name}" doit être au format PDF, JPG ou PNG.`,
				indicator: 'red'
			});
			return false;
		}

		return true;
	}

	['birth_certificate', 'access_diploma_copy', 'id_photo', 'remittance_receipt'].forEach(fieldname => {
		const input = document.querySelector(`[data-fieldname="${fieldname}"] input[type="file"]`);
		if (input) {
			input.addEventListener('change', function(e) {
				const file = e.target.files[0];
				if (file && !validateFile(fieldname, file)) {
					e.target.value = ''; // Reset invalid file
				}
			});
		}
	});

	// ---- Form validation before submit ----
	frappe.web_form.validate = function() {
		// Numéros stockés avec le code pays +237
		prefixerPhones();

		const requiredFields = [
			'filiere', 'niveau', 'examination_centre',
			'first_name', 'last_name', 'birthdate', 'birth_place', 'sexe',
			'phone', 'email',
			'birth_certificate', 'access_diploma_copy', 'id_photo', 'remittance_receipt'
		];

		let missing = [];
		requiredFields.forEach(fieldname => {
			const value = frappe.web_form.get_value(fieldname);
			if (!value) {
				missing.push(fieldname);
			}
		});

		// Check table fields
		const choixFormation = frappe.web_form.get_value('choix_de_formation');
		if (!choixFormation || choixFormation.length === 0) {
			missing.push('choix_de_formation');
		}

		const diplomeFormation = frappe.web_form.get_value('diplome_formation');
		if (!diplomeFormation || diplomeFormation.length === 0) {
			missing.push('diplome_formation');
		}

		// Champs obligatoires à l'intérieur des lignes des tableaux
		const requiredRowFields = {
			'choix_de_formation': ['choix', 'filiere', 'niveau'],
			'diplome_formation': ['diplome', 'year', 'serie__field_of_study', 'place_of_acquisition', 'mention']
		};

		let incompleteRows = false;
		Object.keys(requiredRowFields).forEach(function (tableFieldname) {
			const colonnes = requiredRowFields[tableFieldname];
			(frappe.web_form.get_value(tableFieldname) || []).forEach(function (row) {
				// Ignorer les lignes totalement vides (lignes fantômes/placeholders)
				// afin qu'elles ne bloquent pas la soumission.
				const valeurs = colonnes.map(function (col) { return row[col]; });
				const totalementVide = valeurs.every(function (v) { return is_null(v); });
				if (totalementVide) return;

				colonnes.forEach(function (col) {
					if (is_null(row[col])) {
						incompleteRows = true;
						missing.push(tableFieldname + ' (' + col + ')');
					}
				});
			});
		});

		if (incompleteRows) {
			const champsManquants = missing
				.filter(function (m) { return m.indexOf('(') !== -1; })
				.join(', ');
			frappe.msgprint({
				title: 'Lignes incomplètes',
				message: 'Veuillez remplir tous les champs obligatoires de chaque ligne dans « Choix de formation » et « Diplômes » avant de soumettre.'
					+ (champsManquants ? '<br><br><b>Champs manquants :</b> ' + champsManquants : ''),
				indicator: 'red'
			});
			return false;
		}

		if (missing.length > 0) {
			frappe.msgprint({
				title: 'Champs obligatoires manquants',
				message: 'Veuillez remplir tous les champs obligatoires avant de soumettre.',
				indicator: 'red'
			});
			return false;
		}

		// Email validation
		const email = frappe.web_form.get_value('email');
		if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
			frappe.msgprint({
				title: 'Email invalide',
				message: 'Veuillez entrer une adresse email valide.',
				indicator: 'red'
			});
			return false;
		}

		return true;
	};

	// ---- Redirection après soumission ----
	// Le vrai nom du document n'est exposé qu'à travers la réponse de la sauvegarde
	// (response.message.name), pas via frappe.web_form.doc.name (indéfini pour une
	// nouvelle soumission). On le capture via handle_success avant la redirection.
	frappe.web_form._saved_name = null;
	const _udshed_handle_success = frappe.web_form.handle_success.bind(frappe.web_form);
	frappe.web_form.handle_success = function(data) {
		if (data && data.name) {
			frappe.web_form._saved_name = data.name;
		}
		return _udshed_handle_success(data);
	};

	frappe.web_form.after_save = function() {
		const docName = frappe.web_form._saved_name || frappe.web_form.doc.name;
		window.location.href = '/candidature-success?dossier=' + encodeURIComponent(docName);
	};

	// ---- Choix du candidat : les options s'affichent selon la filière sélectionnée ----
	if (frappe.web_form.is_new || frappe.web_form.in_edit_mode) {
		function chargerNiveaux(filiere, callback) {
			if (!filiere) {
				callback([]);
				return;
			}
			frappe.call({
				method: "udshed.api.candidature.get_niveaux_filiere",
				args: { filiere: filiere },
				callback: function (r) {
					var niveaux = r.message || [];
					callback(
						niveaux.filter(function (v, i, arr) {
							return arr.indexOf(v) === i;
						})
					);
				},
				error: function () {
					callback([]);
				},
			});
		}

		function mettreAJourNiveauxFiliere() {
			var filiere = frappe.web_form.get_value("filiere") || "";
			chargerNiveaux(filiere, function (niveaux) {
				var champ = frappe.web_form.fields_dict["niveau"];
				if (!champ) return;
				var options = niveaux.length ? ['', 'Sélectionner le niveau'] : ['Sélectionner le niveau'];
				niveaux.forEach(function (niveau) {
					options.push(niveau);
				});
				champ.df.options = options.join("\n");
				champ.refresh();
				frappe.web_form.set_value("niveau", "");
			});
		}

		frappe.web_form.on("filiere", mettreAJourNiveauxFiliere);

		// Dans la table « Choix de formation », le niveau proposé pour une ligne
		// ne contient que les niveaux de la filière choisie sur cette ligne.
		frappe.web_form.set_query("niveau", "choix_de_formation", function (frm, cdt, cdn) {
			var filiere =
				(frm && frm.filiere) ||
				(locals[cdt] && locals[cdt][cdn] && locals[cdt][cdn].filiere);
			if (!filiere) return;
			return { filters: { parent: filiere } };
		});

		mettreAJourNiveauxFiliere();
	}

	// ---- UX: Scroll to first error ----
	const originalValidate = frappe.web_form.validate;
	frappe.web_form.validate = function() {
		const result = originalValidate.call(this);
		if (result === false) {
			const firstError = document.querySelector('.frappe-control.has-error');
			if (firstError) {
				firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
			}
		}
		return result;
	};

	// ---- Stepper : boutons, pastilles et titres d'étapes en français ----
	const DERNIERE_ETAPE = ETAPES.length - 1;

	function gererBoutonsEtape() {
		if (!frappe.web_form || !frappe.web_form.is_multi_step_form) return;
		const etapeCourante = frappe.web_form.current_section;
		const submitBtn = document.querySelector('.submit-btn');
		if (!submitBtn) return;
		if (etapeCourante === DERNIERE_ETAPE) {
			$(submitBtn).show();
		} else {
			$(submitBtn).hide();
		}
	}

	function configurerStepper() {
		if (!frappe.web_form || !frappe.web_form.is_multi_step_form) return;

		$('.btn-next').text('Suivant');
		$('.btn-previous').text('Précédent');
		$('.submit-btn').text('Soumettre');

		const renderOriginal = frappe.web_form.render_progress_dots.bind(frappe.web_form);
		frappe.web_form.render_progress_dots = function () {
			renderOriginal();
			mettreAJourStepActive(this.current_section);
			gererBoutonsEtape();
		};

		frappe.web_form.render_progress_dots();
	}

	setTimeout(configurerStepper, 100);
});