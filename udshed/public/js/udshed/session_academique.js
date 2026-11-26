// Année académique de la session et filtres du périmètre (udshed/utils/session_academique.py).
//
// - Le personnel choisit l'année une fois, juste après la connexion ; elle vaut pour toute la
//   session (pour en changer : se déconnecter puis se reconnecter).
// - Les champs « Année académique » des nouveaux documents la prennent par défaut.
// - Les listes des DocTypes Udshed qui ont une année sont filtrées sur elle.
// - Udshed.Filtres.monter() : faculté / filière / niveau du périmètre de l'utilisateur ;
//   un filtre n'est modifiable que s'il offre plusieurs options.
(function () {
	if (typeof frappe === "undefined") return;
	window.Udshed = window.Udshed || {};

	const session = () => (frappe.boot && frappe.boot.udshed_session) || null;
	const API = "udshed.utils.session_academique.";

	Udshed.Session = {
		actif() {
			return !!session();
		},
		annee() {
			return (session() && session().annee) || null;
		},
		contexte() {
			if (!this._contexte) {
				this._contexte = frappe.xcall(API + "contexte_filtres").catch((e) => {
					this._contexte = null;
					throw e;
				});
			}
			return this._contexte;
		},
	};

	function memoriser(annee) {
		const s = session();
		s.annee = annee;
		s.choisie = true;
		const defauts = frappe.boot.user.defaults || (frappe.boot.user.defaults = {});
		defauts.academic_year = annee;
		defauts["Academic Year"] = annee;
	}

	function choisir(annee, recharger) {
		return frappe.xcall(API + "choisir_annee", { annee }).then(() => {
			memoriser(annee);
			if (recharger) window.location.reload();
		});
	}

	function demander_annee() {
		const s = session();
		if (!s || s.choisie) return;
		const annees = s.annees || [];
		if (annees.length <= 1) {
			if (annees.length) choisir(annees[0], false);
			return;
		}
		const d = new frappe.ui.Dialog({
			title: __("Année académique de travail"),
			fields: [
				{
					fieldtype: "HTML",
					options: `<p class="text-muted" style="font-size:14px">${__(
						"Cette année s'applique à tous les écrans pendant toute votre session. Pour travailler sur une autre année, il faudra vous déconnecter puis vous reconnecter."
					)}</p>`,
				},
				{
					fieldtype: "Select",
					fieldname: "annee",
					label: __("Année académique"),
					options: annees,
					default: annees.includes(s.annee_courante) ? s.annee_courante : annees[0],
					reqd: 1,
				},
			],
			primary_action_label: __("Commencer"),
			primary_action: (v) => {
				d.get_primary_btn().prop("disabled", true);
				choisir(v.annee, true).catch(() => d.get_primary_btn().prop("disabled", false));
			},
		});
		if (d.no_cancel) d.no_cancel();
		d.onhide = () => {
			if (!session().choisie) setTimeout(() => d.show(), 150);
		};
		d.show();
	}

	// ------------------------------------------------------------------ listes
	function champ_annee(meta) {
		const champs = (meta && meta.fields) || [];
		return (
			champs.find((df) => df.fieldtype === "Link" && df.options === "Academic Year" && df.fieldname === "academic_year") ||
			champs.find((df) => df.fieldtype === "Link" && df.options === "Academic Year") ||
			champs.find((df) => df.fieldname === "annee_academique") ||
			null
		);
	}

	function patcher_listes() {
		const LV = frappe.views && frappe.views.ListView;
		if (!LV || LV.prototype.__udshed_annee) return;
		const origine = LV.prototype.setup_defaults;
		LV.prototype.setup_defaults = function () {
			const resultat = origine.apply(this, arguments);
			const fixer = () => {
				const annee = Udshed.Session.annee();
				if (!annee || !this.meta || this.meta.module !== "Udshed") return;
				const df = champ_annee(this.meta);
				if (!df) return;
				// L'année de la session remplace toute année enregistrée dans les réglages de la liste.
				this.filters = (this.filters || []).filter((f) => f[1] !== df.fieldname);
				this.filters.push([this.doctype, df.fieldname, "=", annee]);
			};
			if (resultat && typeof resultat.then === "function") {
				return resultat.then((r) => {
					fixer();
					return r;
				});
			}
			fixer();
			return resultat;
		};
		LV.prototype.__udshed_annee = true;
	}

	// ------------------------------------------------------------------ filtres des écrans
	const ORDRE = ["faculty", "filiere", "niveau"];
	const LIBELLES = { faculty: "Faculté", filiere: "Filière", niveau: "Niveau" };

	Udshed.Filtres = {
		/**
		 * Ajoute à `page` les filtres du périmètre ; l'année est celle de la session (affichée).
		 *   champs : sous-ensemble ordonné de ["faculty", "filiere", "niveau"]
		 *   tous   : champs qui proposent « Tous » quand plusieurs options existent
		 *   on_change(valeurs) : appelé au démarrage puis à chaque changement
		 * Retourne { get(), pret: Promise<valeurs>, champs }.
		 */
		monter({ page, champs = ORDRE, tous = [], on_change = () => {}, valeurs = {}, libelles = {} }) {
			const etat = { academic_year: Udshed.Session.annee(), faculty: null, filiere: null, niveau: null, ...valeurs };
			if (page.set_indicator && etat.academic_year) page.set_indicator(__("Année {0}", [etat.academic_year]), "gray");
			let ctx = { facultes: [], filieres: [], niveaux: [] };
			let silence = false;
			const f = {};

			const options = (nom) => {
				if (nom === "faculty") return ctx.facultes || [];
				if (nom === "filiere") {
					const fac = f.faculty ? etat.faculty : null;
					return (ctx.filieres || []).filter((o) => !fac || o.faculte === fac);
				}
				if (!etat.filiere) return [];
				return (ctx.niveaux || []).filter((o) => o.filiere === etat.filiere);
			};

			const remplir = (nom) => {
				const champ = f[nom];
				if (!champ) return;
				const liste = options(nom);
				let valeur = etat[nom];
				if (!liste.some((o) => o.value === valeur)) valeur = liste.length === 1 ? liste[0].value : null;
				etat[nom] = valeur;
				const vide = tous.includes(nom) ? __("Tous") : __("Choisir…");
				champ.df.options = (liste.length > 1 ? [{ value: "", label: vide }] : []).concat(liste);
				silence = true;
				champ.refresh();
				champ.set_input(valeur || "");
				// Une seule option : déjà choisie et non modifiable.
				if (champ.$input) champ.$input.prop("disabled", liste.length <= 1);
				silence = false;
			};

			champs.forEach((nom) => {
				f[nom] = page.add_field({
					fieldtype: "Select",
					fieldname: nom,
					label: libelles[nom] || __(LIBELLES[nom]),
					options: [],
					change: () => {
						if (silence) return;
						etat[nom] = f[nom].get_value() || null;
						ORDRE.slice(ORDRE.indexOf(nom) + 1).forEach(remplir);
						on_change({ ...etat });
					},
				});
			});

			const pret = Udshed.Session.contexte().then((c) => {
				ctx = c || ctx;
				if (c && c.annee) etat.academic_year = c.annee;
				ORDRE.forEach(remplir);
				on_change({ ...etat });
				return { ...etat };
			});
			return { get: () => ({ ...etat }), pret, champs: f };
		},
	};

	/**
	 * Fige les filtres d'un écran construit avec page.add_field :
	 *  - l'année académique est celle de la session (non modifiable) ;
	 *  - faculté, filière, niveau : choisis et verrouillés s'il n'existe qu'une valeur possible
	 *    dans le périmètre de l'utilisateur.
	 */
	Udshed.Filtres.verrouiller = async function (page) {
		const champ = (n) => page && page.fields_dict && page.fields_dict[n];
		const bloquer = (c, oui, titre) => {
			if (!c || !c.$input) return;
			c.$input.prop("disabled", !!oui);
			c.$input.attr("title", oui ? titre || "" : "");
		};
		const annee = Udshed.Session.annee();
		const a = champ("academic_year");
		if (a && annee) {
			if (a.get_value() !== annee) await a.set_value(annee);
			bloquer(a, true, __("Année de la session. Pour en changer, déconnectez-vous puis reconnectez-vous."));
		}
		let ctx = null;
		try {
			ctx = await Udshed.Session.contexte();
		} catch (e) {
			return;
		}
		const uniques = {
			faculty: (ctx.facultes || []).map((o) => o.value),
			filiere: (ctx.filieres || []).map((o) => o.value),
		};
		for (const nom of ["faculty", "filiere"]) {
			const c = champ(nom);
			if (!c || uniques[nom].length !== 1) continue;
			if (!c.get_value()) await c.set_value(uniques[nom][0]);
			bloquer(c, true, __("Seule valeur possible dans votre périmètre."));
		}
		const niv = champ("niveau");
		if (niv && niv.df && niv.df.fieldtype === "Select" && !niv.__udshed_verrou) {
			niv.__udshed_verrou = true;
			const origine = niv.refresh.bind(niv);
			let encours = false;
			niv.refresh = function () {
				const res = origine.apply(this, arguments);
				if (!encours) {
					const valeurs = (niv.df.options || [])
						.map((o) => (o && typeof o === "object" ? o.value : o))
						.filter(Boolean);
					bloquer(niv, valeurs.length === 1, __("Seule valeur possible dans votre périmètre."));
					if (valeurs.length === 1 && niv.get_value() !== valeurs[0]) {
						encours = true;
						Promise.resolve(niv.set_value(valeurs[0])).finally(() => (encours = false));
					}
				}
				return res;
			};
			niv.refresh();
		}
	};

	$(document).on("app_ready", () => {
		if (!session()) return;
		patcher_listes();
		demander_annee();
	});
})();
