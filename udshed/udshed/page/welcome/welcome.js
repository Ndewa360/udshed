frappe.pages['welcome'].on_page_load = function(wrapper) {
	frappe.require([
		'/assets/udshed/css/welcome.css'
	]).then(() => {
		let page = frappe.ui.make_app_page({
			parent: wrapper,
			title: '',
			single_column: true
		});

		$(wrapper).html(`
			<div class="welcome-wrapper">
				<div class="welcome-topbar">
					<div class="welcome-logo">UDSHED</div>
					<button class="btn welcome-btn-login" onclick="window.location.href='/connexion-etudiant'">
						${__("Login")}
					</button>
				</div>

				<div class="welcome-hero">
					<h1 class="welcome-title">${__("Welcome to UDSHED")}</h1>
					<p class="welcome-subtitle">${__("University Management System")}</p>

					<div class="welcome-actions">
						<button class="btn welcome-action-btn" id="btn-submit-candidature">
							<span class="welcome-btn-icon">📝</span>
							${__("Submit an Application")}
						</button>

						<button class="btn welcome-action-btn" id="btn-track-candidature">
							<span class="welcome-btn-icon">🔍</span>
							${__("Track my Application")}
						</button>

						<button class="btn welcome-action-btn" id="btn-inscription">
							<span class="welcome-btn-icon">🎓</span>
							${__("Register")}
						</button>

						<button class="btn welcome-action-btn" id="btn-reinscription">
							<span class="welcome-btn-icon">🔄</span>
							${__("Re-register")}
						</button>
					</div>
				</div>
			</div>
		`);

		// Bouton Soumettre une candidature
		document.getElementById("btn-submit-candidature").addEventListener("click", () => {
			if (!navigator.onLine) {
				frappe.msgprint({
					title: __("Offline"),
					message: __("Vous êtes hors ligne. Vérifiez votre connexion internet."),
					indicator: "red"
				});
				return;
			}

			frappe.call({
				method: "udshed.udshed.doctype.session_inscription.session_inscription.get_open_session",
				callback: (r) => {
					if (r && r.message) {
						window.location.href = "/session-de-2025";
					} else {
						frappe.msgprint({
							title: __("Unavailable"),
							message: __("Registration sessions are not open at the moment."),
							indicator: "red"
						});
					}
				},
				error: () => {
					frappe.msgprint({
						title: __("Error"),
						message: __("Unable to verify session availability. Please try again later."),
						indicator: "red"
					});
				}
			});
		});

		// Bouton Suivre ma candidature
		document.getElementById("btn-track-candidature").addEventListener("click", () => {
			window.location.href = "/suivi-candidature";
		});

		// Bouton S'inscrire
		document.getElementById("btn-inscription").addEventListener("click", () => {
			if (!navigator.onLine) {
				frappe.msgprint({
					title: __("Offline"),
					message: __("Vous êtes hors ligne. Vérifiez votre connexion internet."),
					indicator: "red"
				});
				return;
			}

			frappe.call({
				method: "udshed.udshed.doctype.session_inscription.session_inscription.get_open_session",
				callback: (r) => {
					if (r && r.message) {
						window.location.href = "/inscription/inscription";
					} else {
						frappe.msgprint({
							title: __("Unavailable"),
							message: __("Aucune session d'inscription en cours."),
							indicator: "red"
						});
					}
				},
				error: () => {
					frappe.msgprint({
						title: __("Error"),
						message: __("Unable to verify session availability. Please try again later."),
						indicator: "red"
					});
				}
			});
		});

		// Bouton Se réinscrire → page de connexion (matricule + date de naissance) puis réinscription
		document.getElementById("btn-reinscription").addEventListener("click", () => {
			window.location.href = "/connexion-etudiant";
		});
	});
};
