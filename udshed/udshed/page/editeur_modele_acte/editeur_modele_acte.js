// Éditeur visuel des modèles d'actes académiques.
// La page dessine le document à l'échelle (positions en mm) ; chaque élément
// se déplace, se redimensionne et se règle dans le panneau de propriétés.
// Le rendu final (PDF) est fait côté serveur : udshed/utils/actes.py.
frappe.pages["editeur-modele-acte"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Éditeur de modèle d'acte"), single_column: true });
	new EditeurActe(page);
};

const FORMATS = {
	"A4 portrait": [210, 297], "A4 paysage": [297, 210], "A5 paysage": [210, 148], "Carte (85,6 × 54 mm)": [85.6, 54],
};
const OUTILS = [
	["texte", __("Texte"), { w: 120, h: 10, contenu: __("Nouveau texte"), taille: 11 }],
	["logo", __("Logo"), { w: 25, h: 25 }],
	["image", __("Image"), { w: 40, h: 30 }],
	["photo", __("Photo étudiant"), { w: 25, h: 32 }],
	["qr", __("QR code"), { w: 28, h: 28 }],
	["signature", __("Signature"), { w: 45, h: 22 }],
	["cachet", __("Cachet"), { w: 32, h: 32 }],
	["cadre", __("Cadre / ligne"), { w: 120, h: 30, bordure: 0.5, couleur: "#1f3c88" }],
	["tableau_notes", __("Tableau des notes"), { w: 180, h: 120, taille: 8 }],
];

class EditeurActe {
	constructor(page) {
		this.page = page;
		this.echelle = 3; // pixels par mm à l'écran
		this.elements = [];
		this.selection = null;
		this.modele = (frappe.route_options && frappe.route_options.modele) || new URLSearchParams(location.search).get("modele");
		frappe.route_options = null;
		this.construire();
		if (this.modele) this.charger(this.modele);
		else this.choisirModele();
	}

	construire() {
		const p = this.page;
		p.set_primary_action(__("Enregistrer"), () => this.enregistrer());
		p.add_button(__("Aperçu PDF"), () => this.apercu());
		p.add_button(__("Ouvrir un autre modèle"), () => this.choisirModele());
		$(`<style>
			.ea { display: grid; grid-template-columns: 190px 1fr 280px; gap: 12px; align-items: start; }
			.ea-outils button { display: block; width: 100%; margin-bottom: 6px; text-align: left; }
			.ea-zone { overflow: auto; background: var(--control-bg); border-radius: 8px; padding: 18px; min-height: 70vh; }
			.ea-page { position: relative; background: #fff; margin: 0 auto; box-shadow: 0 4px 18px rgba(0,0,0,.12);
				background-size: cover; user-select: none; }
			.ea-el { position: absolute; box-sizing: border-box; cursor: move; overflow: hidden; color: #1b1f2a;
				outline: 1px dashed rgba(31,60,136,.35); line-height: 1.3; white-space: pre-wrap; }
			.ea-el.sel { outline: 2px solid #1f6feb; z-index: 999; }
			.ea-el .ea-poignee { position: absolute; right: 0; bottom: 0; width: 10px; height: 10px; background: #1f6feb; cursor: nwse-resize; }
			.ea-ph { display: flex; align-items: center; justify-content: center; color: #667085; font-size: 11px;
				background: repeating-linear-gradient(45deg,#f2f4f7,#f2f4f7 6px,#e4e7ec 6px,#e4e7ec 12px); width: 100%; height: 100%; }
			.ea-el img { width: 100%; height: 100%; object-fit: contain; pointer-events: none; }
			.ea-props .form-group { margin-bottom: 8px; }
			.ea-vars { max-height: 220px; overflow: auto; font-size: 12px; }
			.ea-vars a { display: block; padding: 2px 0; }
			@media (max-width: 1100px) { .ea { grid-template-columns: 1fr; } }
		</style>`).appendTo(p.main);
		this.$racine = $(`<div class="ea">
			<div class="ea-outils"><div class="text-muted small mb-2">${__("Ajouter")}</div></div>
			<div class="ea-zone"><div class="ea-page"></div></div>
			<div class="ea-props"><div class="text-muted">${__("Sélectionnez un élément pour le régler.")}</div></div>
		</div>`).appendTo(p.main);
		OUTILS.forEach(([type, libelle, defaut]) => {
			$(`<button class="btn btn-default btn-sm">${libelle}</button>`)
				.on("click", () => this.ajouter(type, defaut))
				.appendTo(this.$racine.find(".ea-outils"));
		});
		$(`<div class="text-muted small mt-3">${__("Astuce : flèches du clavier pour déplacer (Maj = 5 mm), Suppr pour effacer.")}</div>`)
			.appendTo(this.$racine.find(".ea-outils"));
		this.$page = this.$racine.find(".ea-page");
		$(document).on("keydown.editeur_acte", (e) => this.clavier(e));
		frappe.call("udshed.api.actes.variables_modele").then((r) => (this.variables = r.message || []));
	}

	choisirModele() {
		const d = new frappe.ui.Dialog({
			title: __("Modèle à dessiner"),
			fields: [{ fieldtype: "Link", options: "Modele Acte", fieldname: "modele", label: __("Modèle"), reqd: 1 }],
			primary_action: (v) => { d.hide(); this.charger(v.modele); },
		});
		d.show();
	}

	charger(nom) {
		frappe.db.get_doc("Modele Acte", nom).then((doc) => {
			this.doc = doc;
			this.modele = nom;
			this.page.set_title(__("Modèle : {0}", [nom]));
			const [l, h] = FORMATS[doc.format] || FORMATS["A4 portrait"];
			this.echelle = l < 100 ? 7 : 3;
			this.largeur = l; this.hauteur = h;
			this.$page.css({ width: l * this.echelle, height: h * this.echelle,
				backgroundImage: doc.image_fond ? `url("${doc.image_fond}")` : "none" });
			let layout = {};
			try { layout = JSON.parse(doc.layout || "{}"); } catch (e) { layout = {}; }
			this.elements = (layout.elements || []).map((el, i) => ({ id: "e" + i + Date.now(), ...el }));
			this.selection = null;
			this.rendre();
		});
	}

	px(mm) { return mm * this.echelle; }
	mm(px) { return Math.round((px / this.echelle) * 10) / 10; }

	ajouter(type, defaut) {
		if (!this.doc) return frappe.msgprint(__("Ouvrez d'abord un modèle."));
		const el = { id: "e" + Date.now(), type, x: 10, y: 10, ...JSON.parse(JSON.stringify(defaut)) };
		this.elements.push(el);
		this.selection = el.id;
		this.rendre();
		if (type === "image") this.televerser(el);
	}

	rendre() {
		this.$page.empty();
		this.elements.forEach((el) => {
			const $el = $(`<div class="ea-el" data-id="${el.id}"></div>`).css({
				left: this.px(el.x), top: this.px(el.y), width: this.px(el.w), height: this.px(el.h),
				fontSize: (el.taille || 11) * this.echelle * 0.3528 + "px", fontWeight: el.gras ? 700 : 400,
				fontStyle: el.italique ? "italic" : "normal", textAlign: el.align || "left", color: el.couleur || "",
				fontFamily: el.police || "",
			});
			if (el.id === this.selection) $el.addClass("sel");
			if (el.type === "texte") $el.text(el.contenu || "");
			else if (el.type === "cadre") $el.css({ border: `${(el.bordure ?? 0.5) * this.echelle}px solid ${el.couleur || "#1f3c88"}`,
				background: el.fond || "transparent", borderRadius: (el.arrondi || 0) * this.echelle });
			else if (el.type === "image" && el.src) $el.append(`<img src="${el.src}">`);
			else if (el.type === "logo" && frappe.boot.app_logo_url) $el.append(`<img src="${frappe.boot.app_logo_url}">`);
			else if (el.type === "signature" && this.doc.image_signature) $el.append(`<img src="${this.doc.image_signature}">`);
			else if (el.type === "cachet" && this.doc.image_cachet) $el.append(`<img src="${this.doc.image_cachet}">`);
			else {
				const noms = { photo: __("Photo"), qr: "QR", tableau_notes: __("Tableau des notes"), image: __("Image"),
					logo: __("Logo"), signature: __("Signature"), cachet: __("Cachet") };
				$el.append(`<div class="ea-ph">${noms[el.type] || el.type}</div>`);
			}
			$el.append(`<div class="ea-poignee"></div>`);
			this.brancherSouris($el, el);
			this.$page.append($el);
		});
		this.proprietes();
	}

	brancherSouris($el, el) {
		$el.on("mousedown", (e) => {
			e.preventDefault();
			this.selection = el.id;
			this.$page.find(".ea-el").removeClass("sel");
			$el.addClass("sel");
			this.proprietes();
			const redim = $(e.target).hasClass("ea-poignee");
			const depart = { x: e.pageX, y: e.pageY, ex: el.x, ey: el.y, ew: el.w, eh: el.h };
			$(document).on("mousemove.ea", (m) => {
				const dx = this.mm(m.pageX - depart.x), dy = this.mm(m.pageY - depart.y);
				if (redim) { el.w = Math.max(2, depart.ew + dx); el.h = Math.max(0.5, depart.eh + dy); }
				else {
					el.x = Math.min(Math.max(0, depart.ex + dx), this.largeur - 1);
					el.y = Math.min(Math.max(0, depart.ey + dy), this.hauteur - 1);
				}
				$el.css({ left: this.px(el.x), top: this.px(el.y), width: this.px(el.w), height: this.px(el.h) });
			});
			$(document).one("mouseup.ea", () => { $(document).off("mousemove.ea"); this.proprietes(); });
		});
	}

	courant() { return this.elements.find((e) => e.id === this.selection); }

	proprietes() {
		const el = this.courant();
		const $p = this.$racine.find(".ea-props").empty();
		if (!el) return $p.append(`<div class="text-muted">${__("Sélectionnez un élément pour le régler.")}</div>`);
		const champ = (cle, libelle, type = "number", pas = 0.5) =>
			`<div class="form-group"><label class="small">${libelle}</label><input class="form-control input-sm" data-cle="${cle}" type="${type}" step="${pas}" value="${frappe.utils.escape_html(el[cle] ?? "")}"></div>`;
		let html = `<div class="small text-muted mb-2">${__("Élément")} : <b>${el.type}</b></div>
			<div class="row"><div class="col-6">${champ("x", "X (mm)")}</div><div class="col-6">${champ("y", "Y (mm)")}</div>
			<div class="col-6">${champ("w", __("Largeur (mm)"))}</div><div class="col-6">${champ("h", __("Hauteur (mm)"))}</div></div>`;
		if (el.type === "texte") {
			html += `<div class="form-group"><label class="small">${__("Texte (variables entre {{ }})")}</label>
				<textarea class="form-control" rows="5" data-cle="contenu">${frappe.utils.escape_html(el.contenu || "")}</textarea></div>
				<div class="ea-vars border rounded p-2 mb-2">${(this.variables || []).map((v) =>
					`<a href="#" data-var="${v.cle}">+ ${frappe.utils.escape_html(v.libelle)}</a>`).join("")}</div>`;
		}
		if (["texte", "tableau_notes"].includes(el.type)) html += champ("taille", __("Taille du texte (pt)"));
		if (el.type === "texte") {
			html += `<div class="form-group"><label class="small">${__("Alignement")}</label><select class="form-control input-sm" data-cle="align">
				${["left", "center", "right", "justify"].map((a) => `<option value="${a}" ${el.align === a ? "selected" : ""}>${a}</option>`).join("")}</select></div>
				${champ("couleur", __("Couleur"), "color")}
				<div class="form-group"><label class="small">${__("Police")}</label><select class="form-control input-sm" data-cle="police">
				${[["", "Sans empattement"], ["serif", "Avec empattement"], ["monospace", "Chasse fixe"]].map(([v, l]) =>
					`<option value="${v}" ${(el.police || "") === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>
				<label class="small"><input type="checkbox" data-cle="gras" ${el.gras ? "checked" : ""}> ${__("Gras")}</label>
				<label class="small ml-3"><input type="checkbox" data-cle="italique" ${el.italique ? "checked" : ""}> ${__("Italique")}</label>`;
		}
		if (el.type === "cadre") html += champ("bordure", __("Épaisseur bordure (mm)"), "number", 0.1) + champ("couleur", __("Couleur bordure"), "color")
			+ champ("fond", __("Couleur de fond (vide = transparent)"), "text") + champ("arrondi", __("Arrondi (mm)"));
		if (el.type === "image") html += `<button class="btn btn-default btn-sm mb-2 ea-televerser">${__("Choisir l'image")}</button>`;
		html += `<div class="mt-2"><button class="btn btn-default btn-sm ea-dupliquer">${__("Dupliquer")}</button>
			<button class="btn btn-default btn-sm ea-avant">${__("Premier plan")}</button>
			<button class="btn btn-default btn-sm ea-arriere">${__("Arrière-plan")}</button>
			<button class="btn btn-danger btn-sm ea-supprimer mt-2">${__("Supprimer")}</button></div>`;
		$p.html(html);
		$p.find("[data-cle]").on("input change", (e) => {
			const $i = $(e.target), cle = $i.data("cle");
			el[cle] = $i.attr("type") === "checkbox" ? $i.is(":checked") : ($i.attr("type") === "number" ? parseFloat($i.val()) || 0 : $i.val());
			this.rendreSansProps();
		});
		$p.find("[data-var]").on("click", (e) => {
			e.preventDefault();
			const $t = $p.find("textarea[data-cle=contenu]")[0];
			const ins = `{{ ${$(e.target).data("var")} }}`;
			const pos = $t.selectionStart ?? $t.value.length;
			$t.value = $t.value.slice(0, pos) + ins + $t.value.slice(pos);
			el.contenu = $t.value;
			this.rendreSansProps();
		});
		$p.find(".ea-televerser").on("click", () => this.televerser(el));
		$p.find(".ea-dupliquer").on("click", () => {
			const copie = { ...JSON.parse(JSON.stringify(el)), id: "e" + Date.now(), x: el.x + 5, y: el.y + 5 };
			this.elements.push(copie); this.selection = copie.id; this.rendre();
		});
		$p.find(".ea-avant").on("click", () => { this.elements = this.elements.filter((e) => e !== el).concat([el]); this.rendre(); });
		$p.find(".ea-arriere").on("click", () => { this.elements = [el].concat(this.elements.filter((e) => e !== el)); this.rendre(); });
		$p.find(".ea-supprimer").on("click", () => { this.elements = this.elements.filter((e) => e !== el); this.selection = null; this.rendre(); });
	}

	rendreSansProps() {
		const props = this.proprietes;
		this.proprietes = () => {};
		this.rendre();
		this.proprietes = props;
	}

	televerser(el) {
		new frappe.ui.FileUploader({
			allow_multiple: false, restrictions: { allowed_file_types: ["image/*"] }, make_attachments_public: true,
			on_success: (file) => { el.src = file.file_url; this.rendre(); },
		});
	}

	clavier(e) {
		if (!this.selection || !$(e.target).is("body")) return;
		const el = this.courant();
		if (!el) return;
		const pas = e.shiftKey ? 5 : 0.5;
		const actions = { ArrowLeft: () => (el.x -= pas), ArrowRight: () => (el.x += pas), ArrowUp: () => (el.y -= pas), ArrowDown: () => (el.y += pas) };
		if (actions[e.key]) { e.preventDefault(); actions[e.key](); this.rendre(); }
		if (e.key === "Delete") { this.elements = this.elements.filter((x) => x !== el); this.selection = null; this.rendre(); }
	}

	layout() {
		return JSON.stringify({ elements: this.elements.map(({ id, ...reste }) => reste) });
	}

	enregistrer() {
		if (!this.modele) return;
		frappe.call("udshed.api.actes.enregistrer_layout", { modele: this.modele, layout: this.layout() })
			.then(() => frappe.show_alert({ message: __("Modèle enregistré"), indicator: "green" }));
	}

	apercu() {
		if (!this.modele) return;
		open_url_post("/api/method/udshed.api.actes.apercu_modele", { modele: this.modele, layout: this.layout() }, true);
	}
}
