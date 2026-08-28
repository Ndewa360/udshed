frappe.ready(function() {
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
	frappe.web_form.after_save = function() {
		const docName = frappe.web_form.doc.name;
		window.location.href = '/candidature-success?dossier=' + encodeURIComponent(docName);
	};

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
});