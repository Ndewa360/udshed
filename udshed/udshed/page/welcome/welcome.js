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
					<button class="btn welcome-btn-login" onclick="window.location.href='/login'">
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

						<button class="btn welcome-action-btn welcome-btn-disabled" id="btn-reinscription">
							<span class="welcome-btn-icon">🔄</span>
							${__("Re-register")}
						</button>
					</div>
				</div>
			</div>
		`);

		// Bouton Soumettre une candidature
		document.getElementById("btn-submit-candidature").addEventListener("click", () => {
			frappe.call({
				method: "udshed.udshed.doctype.session_inscription.session_inscription.get_open_session",
				callback: (r) => {
					if (r.message) {
						window.location.href = "/session-de-2025";
					} else {
						frappe.msgprint({
							title: __("Unavailable"),
							message: __("Registration sessions are not open at the moment."),
							indicator: "red"
						});
					}
				}
			});
		});

		// Bouton Suivre ma candidature
		document.getElementById("btn-track-candidature").addEventListener("click", () => {
			window.location.href = "/track-application";
		});

		// Bouton S'inscrire
		document.getElementById("btn-inscription").addEventListener("click", () => {
			window.location.href = "/app/student";
		});

		// Bouton Se réinscrire (désactivé pour l'instant)
		document.getElementById("btn-reinscription").addEventListener("click", () => {
			frappe.msgprint({
				title: __("Coming Soon"),
				message: __("This feature is not yet available."),
				indicator: "orange"
			});
		});
	});
};
