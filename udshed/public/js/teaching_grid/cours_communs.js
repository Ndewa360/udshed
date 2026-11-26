window.Udshed = window.Udshed || {};
window.Udshed.TeachingGrid = window.Udshed.TeachingGrid || {};

/**
 * Cours communs : deux grilles de classes côte à côte, reliées par des traits.
 *  - trait bleu plein   : tronc commun (le même cours est dans les deux grilles) ;
 *  - trait violet       : cours liés (même enseignement, intitulés différents) — cliquer pour délier ;
 *  - trait gris pointillé : suggestion (intitulés identiques) — cliquer pour lier.
 * Pour lier : cliquer un cours d'un côté, un trait suit la souris, cliquer le
 * cours d'arrivée de l'autre côté. Une liaison n'ajoute aucune classe aux
 * cours : chaque classe garde son cours, son intitulé et ses crédits ; le
 * planning, les conflits et la saisie des notes les traitent comme un seul
 * enseignement.
 */
window.Udshed.TeachingGrid.CoursCommuns = {
    open(filters, onChange = () => {}) {
        if (!filters.academic_year) {
            Udshed.Messages.validation(__("Sélectionnez d'abord l'année académique."));
            return;
        }
        const API = "udshed.api.cours_commun.";
        const esc = (v) => frappe.utils.escape_html(v === null || v === undefined ? "" : String(v));
        const fmt = (v) => (Number(v) || 0).toLocaleString("fr-FR", { maximumFractionDigits: 1 });
        const etat = { data: null, depart: null, modifie: false };
        const niveauxParFiliere = {};

        // Les « change » peuvent se déclencher pendant la construction du dialogue (d encore nul).
        const cote = (suffixe, cote_label, defauts) => [
            {
                fieldtype: "Link", fieldname: `faculte_${suffixe}`, label: __("{0} — Faculté", [cote_label]), options: "Faculty",
                default: defauts.faculty || null,
                change: () => { if (d && d.get_value(`filiere_${suffixe}`)) d.set_value(`filiere_${suffixe}`, null); },
            },
            {
                fieldtype: "Link", fieldname: `filiere_${suffixe}`, label: __("{0} — Filière", [cote_label]), options: "Field of study",
                default: defauts.filiere || null,
                get_query: () => {
                    const fac = d && d.get_value(`faculte_${suffixe}`);
                    return fac ? { filters: { faculte: fac } } : {};
                },
                change: () => { if (d) chargerNiveaux(suffixe); },
            },
            {
                fieldtype: "Select", fieldname: `niveau_${suffixe}`, label: __("{0} — Niveau", [cote_label]),
                change: () => { if (d) { majExclusions(); charger(); } },
            },
        ];

        let d = null;
        d = new frappe.ui.Dialog({
            title: __("Cours communs entre deux grilles — {0}", [filters.academic_year]),
            size: "extra-large",
            fields: [
                {
                    fieldtype: "Select", fieldname: "semestre", label: __("Semestre"),
                    options: [
                        { value: "", label: __("Tous les semestres") },
                        { value: "Semestre 1", label: "Semestre 1" },
                        { value: "Semestre 2", label: "Semestre 2" },
                    ],
                    default: filters.semestre || "",
                    change: () => charger(),
                },
                { fieldtype: "Column Break" },
                { fieldtype: "HTML", fieldname: "legende" },
                { fieldtype: "Section Break", label: __("Les deux classes à comparer") },
                ...cote("g", __("Gauche"), filters),
                { fieldtype: "Column Break" },
                ...cote("d", __("Droite"), { faculty: filters.faculty }),
                { fieldtype: "Section Break" },
                { fieldtype: "HTML", fieldname: "zone" },
            ],
        });
        d.$wrapper.find(".modal-dialog").css({ "max-width": "min(1400px, 96vw)", width: "96vw" });
        d.fields_dict.legende.$wrapper.html(`
            <div class="cc-legende">
                <span><i class="cc-l tronc"></i>${__("Tronc commun")}</span>
                <span><i class="cc-l lie"></i>${__("Cours liés (cliquer pour délier)")}</span>
                <span><i class="cc-l sugg"></i>${__("Suggestion (cliquer pour lier)")}</span>
                <div class="text-muted small">${__("Pour lier : cliquez un cours, puis le cours identique de l'autre grille. Échap pour annuler.")}</div>
            </div>`);
        const $zone = d.fields_dict.zone.$wrapper;
        $zone.html(`<div class="text-muted text-center p-4">${__("Choisissez une classe de chaque côté.")}</div>`);
        injecterStyle();

        d.onhide = () => {
            $(document).off("keydown.cc");
            $(window).off("resize.cc");
            if (etat.modifie) onChange();
        };
        $(document).on("keydown.cc", (e) => { if (e.key === "Escape" && etat.depart) { e.stopPropagation(); annulerDepart(); } });
        $(window).on("resize.cc", frappe.utils.debounce(dessiner, 120));
        d.show();

        // Niveau de gauche par défaut = la classe affichée dans la page.
        chargerNiveaux("g", filters.niveau);
        chargerNiveaux("d");

        // ------------------------------------------------------------------
        function classe(s) {
            return { filiere: d.get_value(`filiere_${s}`), niveau: d.get_value(`niveau_${s}`) };
        }

        function chargerNiveaux(s, valeurInitiale) {
            const filiere = d.get_value(`filiere_${s}`);
            const champ = d.fields_dict[`niveau_${s}`];
            if (!filiere) {
                niveauxParFiliere[s] = [];
                majExclusions();
                charger();
                return;
            }
            frappe.call({
                // Niveaux de n'importe quelle filière : on peut comparer sa grille à une autre.
                method: "udshed.api.reference.niveaux_filiere",
                args: { filiere: filiere },
                callback: (r) => {
                    niveauxParFiliere[s] = r.message || [];
                    majExclusions(valeurInitiale && s === "g" ? valeurInitiale : null, s);
                    charger();
                },
            });
        }

        // Une classe choisie d'un côté n'est pas proposée de l'autre côté.
        function majExclusions(valeurForcee, coteForce) {
            ["g", "d"].forEach((s) => {
                const autre = classe(s === "g" ? "d" : "g");
                const champ = d.fields_dict[`niveau_${s}`];
                const filiere = d.get_value(`filiere_${s}`);
                const options = (niveauxParFiliere[s] || [])
                    .filter((n) => !(filiere === autre.filiere && String(n.name) === String(autre.niveau)))
                    .map((n) => ({ value: String(n.name), label: n.level }));
                const actuel = (s === coteForce && valeurForcee) ? String(valeurForcee) : d.get_value(`niveau_${s}`);
                champ.df.options = [{ value: "", label: __("Choisir le niveau") }, ...options];
                champ.refresh();
                const garde = options.some((o) => o.value === String(actuel)) ? String(actuel) : "";
                if (champ.get_value() !== garde) champ.set_input(garde);
                champ.value = garde;
            });
        }

        function charger() {
            const g = classe("g");
            const dr = classe("d");
            annulerDepart();
            if (!g.filiere || !g.niveau || !dr.filiere || !dr.niveau) {
                $zone.html(`<div class="text-muted text-center p-4">${__("Choisissez une classe de chaque côté.")}</div>`);
                return;
            }
            frappe.call({
                method: API + "comparer_grilles",
                args: {
                    academic_year: filters.academic_year,
                    semestre: d.get_value("semestre") || null,
                    filiere_gauche: g.filiere, niveau_gauche: g.niveau,
                    filiere_droite: dr.filiere, niveau_droite: dr.niveau,
                },
                freeze: true,
                freeze_message: __("Chargement des deux grilles..."),
                callback: (r) => { etat.data = r.message; rendre(); },
                error: (err) => Udshed.Messages.error(err, __("Chargement impossible")),
            });
        }

        function colonne(s, cote) {
            const lignes = cote.ues.map((ue) => `
                ${ue.code === "UNKNOW" ? "" : `<div class="cc-ue">${esc(ue.code)} — ${esc(ue.intitule)}</div>`}
                ${ue.cours.map((c) => `
                    <div class="cc-cours" data-cote="${s}" data-tu="${esc(c.teaching_unit)}" tabindex="0"
                         title="${esc(c.code)} — ${esc(c.intitule)}">
                        <div class="cc-titre"><strong>${esc(c.code)}</strong> ${esc(c.intitule)}</div>
                        <div class="cc-meta">${fmt(c.credits)} cr · ${fmt(c.heures)} h ${c.semestre ? "· " + esc(c.semestre) : ""}
                            ${c.classes > 1 ? `<span class="cc-badge tronc">${__("tronc commun")}</span>` : ""}
                            ${c.groupe ? `<span class="cc-badge lie">${__("lié")}</span>` : ""}
                        </div>
                    </div>`).join("")}`).join("");
            return `<div class="cc-col" data-cote="${s}">
                <div class="cc-entete">${esc(cote.libelle)}</div>
                ${lignes || `<div class="text-muted p-3">${__("Aucun cours dans cette grille.")}</div>`}
            </div>`;
        }

        function rendre() {
            const data = etat.data;
            const nbTronc = data.liens.filter((l) => l.type === "tronc_commun").length;
            const nbLies = data.liens.filter((l) => l.type === "lie").length;
            $zone.html(`
                <div class="cc-resume">
                    ${__("{0} cours en tronc commun · {1} liaison(s) · {2} suggestion(s)", [nbTronc, nbLies, data.suggestions.length])}
                    ${data.peut_lier ? "" : `<span class="text-warning"> — ${__("lecture seule : il faut gérer au moins une des deux classes pour créer ou supprimer une liaison")}</span>`}
                </div>
                <div class="cc-zone">
                    ${colonne("g", data.gauche)}
                    <div class="cc-milieu"></div>
                    ${colonne("d", data.droite)}
                    <svg class="cc-svg"></svg>
                </div>`);
            const $z = $zone.find(".cc-zone");
            $z.on("click", ".cc-cours", function () { clicCours($(this)); });
            $z.on("mousemove", (e) => suivreSouris(e));
            $z.on("click", (e) => {
                if (etat.depart && !$(e.target).closest(".cc-cours, .cc-trait").length) annulerDepart();
            });
            setTimeout(dessiner, 30);
        }

        function ancre($row, cote, zoneRect) {
            const r = $row[0].getBoundingClientRect();
            return {
                x: (cote === "g" ? r.right : r.left) - zoneRect.left,
                y: r.top + r.height / 2 - zoneRect.top,
            };
        }

        function chemin(a, b) {
            const dx = Math.max(40, Math.abs(b.x - a.x) / 2);
            const sens = b.x >= a.x ? 1 : -1;
            return `M${a.x},${a.y} C${a.x + dx * sens},${a.y} ${b.x - dx * sens},${b.y} ${b.x},${b.y}`;
        }

        function dessiner() {
            if (!etat.data) return;
            const $z = $zone.find(".cc-zone");
            const svg = $z.find(".cc-svg")[0];
            if (!svg) return;
            const zr = $z[0].getBoundingClientRect();
            svg.setAttribute("width", zr.width);
            svg.setAttribute("height", $z[0].scrollHeight);
            const ligne = (lien, type) => {
                const $a = $z.find(`.cc-cours[data-cote="g"][data-tu="${CSS.escape(lien.gauche)}"]`);
                const $b = $z.find(`.cc-cours[data-cote="d"][data-tu="${CSS.escape(lien.droite)}"]`);
                if (!$a.length || !$b.length) return "";
                $a.addClass(`cc-${type}`);
                $b.addClass(`cc-${type}`);
                const p = chemin(ancre($a, "g", zr), ancre($b, "d", zr));
                const titre = type === "tronc" ? __("Même cours dans les deux grilles (tronc commun)")
                    : type === "lie" ? __("Cours liés — cliquer pour délier") : __("Suggestion — cliquer pour lier");
                return `<g class="cc-trait ${type}" data-g="${esc(lien.gauche)}" data-d="${esc(lien.droite)}">
                    <title>${titre}</title><path class="clic" d="${p}"></path><path class="vu" d="${p}"></path></g>`;
            };
            svg.innerHTML =
                etat.data.suggestions.map((s) => ligne(s, "sugg")).join("") +
                etat.data.liens.map((l) => ligne(l, l.type === "tronc_commun" ? "tronc" : "lie")).join("") +
                `<path class="cc-temp" d=""></path>`;
            $(svg).find(".cc-trait.lie").on("click", function (e) { e.stopPropagation(); delier($(this).data("g"), $(this).data("d")); });
            $(svg).find(".cc-trait.sugg").on("click", function (e) { e.stopPropagation(); lier($(this).data("g"), $(this).data("d")); });
        }

        function clicCours($row) {
            const data = etat.data;
            if (!data) return;
            const s = $row.data("cote");
            const tu = String($row.data("tu"));
            if (!etat.depart) {
                if (!data.peut_lier) {
                    Udshed.Messages.warning(__("Lecture seule : il faut gérer les deux classes pour créer une liaison."));
                    return;
                }
                etat.depart = { cote: s, tu, $row };
                $row.addClass("cc-depart");
                $zone.find(".cc-zone").addClass("cc-en-liaison");
                return;
            }
            if (etat.depart.cote === s) {
                // Même côté : on change de cours de départ.
                const memeCours = etat.depart.tu === tu;
                annulerDepart();
                if (!memeCours) clicCours($row);
                return;
            }
            const g = s === "d" ? etat.depart.tu : tu;
            const dr = s === "d" ? tu : etat.depart.tu;
            annulerDepart();
            lier(g, dr);
        }

        function suivreSouris(e) {
            if (!etat.depart) return;
            const $z = $zone.find(".cc-zone");
            const zr = $z[0].getBoundingClientRect();
            const a = ancre(etat.depart.$row, etat.depart.cote, zr);
            const b = { x: e.clientX - zr.left, y: e.clientY - zr.top };
            $z.find(".cc-temp").attr("d", chemin(a, b));
        }

        function annulerDepart() {
            if (!etat.depart) return;
            etat.depart.$row.removeClass("cc-depart");
            etat.depart = null;
            const $z = $zone.find(".cc-zone");
            $z.removeClass("cc-en-liaison");
            $z.find(".cc-temp").attr("d", "");
        }

        function intitule(tu) {
            for (const cote of [etat.data.gauche, etat.data.droite]) {
                for (const ue of cote.ues) {
                    const c = ue.cours.find((x) => x.teaching_unit === tu);
                    if (c) return `${c.code} — ${c.intitule}`;
                }
            }
            return tu;
        }

        function lier(g, dr) {
            if (g === dr) {
                Udshed.Messages.warning(__("C'est déjà le même cours (tronc commun)."));
                return;
            }
            frappe.confirm(
                __("Lier « {0} » ({1}) et « {2} » ({3}) ?<br><br>Ils seront planifiés comme un seul enseignement : chaque classe garde son cours, son intitulé et ses crédits.",
                    [esc(intitule(g)), esc(etat.data.gauche.libelle), esc(intitule(dr)), esc(etat.data.droite.libelle)]),
                () => frappe.call({
                    method: API + "lier_cours",
                    args: { teaching_units: [g, dr] },
                    freeze: true,
                    callback: () => { etat.modifie = true; Udshed.Messages.success(__("Cours liés.")); charger(); },
                    error: (err) => Udshed.Messages.error(err, __("Liaison impossible")),
                })
            );
        }

        function delier(g, dr) {
            if (!etat.data.peut_lier) {
                Udshed.Messages.warning(__("Lecture seule : il faut gérer les deux classes pour supprimer une liaison."));
                return;
            }
            frappe.confirm(
                __("Supprimer la liaison entre « {0} » et « {1} » ?", [esc(intitule(g)), esc(intitule(dr))]),
                () => frappe.call({
                    method: API + "delier_cours",
                    args: { teaching_unit: dr },
                    freeze: true,
                    callback: () => { etat.modifie = true; Udshed.Messages.success(__("Liaison supprimée.")); charger(); },
                    error: (err) => Udshed.Messages.error(err, __("Opération impossible")),
                })
            );
        }

        function injecterStyle() {
            if (document.getElementById("cc-style")) return;
            $("head").append(`<style id="cc-style">
                .cc-legende{display:flex;flex-wrap:wrap;gap:14px;align-items:center;font-size:12px;padding-top:24px}
                .cc-l{display:inline-block;width:26px;height:0;margin-right:6px;vertical-align:middle;border-top:3px solid}
                .cc-l.tronc{border-color:#2563eb}.cc-l.lie{border-color:#9333ea}.cc-l.sugg{border-color:#9ca3af;border-top-style:dashed}
                .cc-resume{font-size:13px;margin-bottom:10px}
                .cc-zone{position:relative;display:grid;grid-template-columns:1fr 150px 1fr;align-items:start}
                .cc-col{position:relative;z-index:2;border:1px solid var(--border-color);border-radius:10px;overflow:hidden;background:var(--card-bg)}
                .cc-entete{background:var(--subtle-fg);font-weight:700;padding:10px 12px;border-bottom:1px solid var(--border-color)}
                .cc-ue{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--text-muted);padding:8px 12px 4px;background:var(--subtle-accent)}
                .cc-cours{padding:8px 12px;border-bottom:1px solid var(--border-color);cursor:pointer;transition:background .15s}
                .cc-cours:hover{background:var(--subtle-accent)}
                .cc-cours.cc-tronc{box-shadow:inset 4px 0 0 #2563eb}.cc-col[data-cote="g"] .cc-cours.cc-tronc{box-shadow:inset -4px 0 0 #2563eb}
                .cc-cours.cc-lie{box-shadow:inset 4px 0 0 #9333ea}.cc-col[data-cote="g"] .cc-cours.cc-lie{box-shadow:inset -4px 0 0 #9333ea}
                .cc-cours.cc-depart{background:#fef3c7 !important;outline:2px solid #f59e0b}
                .cc-en-liaison .cc-col[data-cote] .cc-cours:not(.cc-depart){cursor:crosshair}
                .cc-titre{font-size:13px}.cc-meta{font-size:11px;color:var(--text-muted)}
                .cc-badge{border-radius:8px;padding:0 6px;margin-left:4px;font-size:10px;font-weight:600}
                .cc-badge.tronc{background:#dbeafe;color:#1d4ed8}.cc-badge.lie{background:#f3e8ff;color:#7e22ce}
                .cc-svg{position:absolute;left:0;top:0;z-index:1;overflow:visible;pointer-events:none}
                .cc-trait .vu{fill:none;stroke-width:2.5}.cc-trait .clic{fill:none;stroke:transparent;stroke-width:14;pointer-events:stroke}
                .cc-trait.tronc .vu{stroke:#2563eb}.cc-trait.lie .vu{stroke:#9333ea}.cc-trait.sugg .vu{stroke:#9ca3af;stroke-dasharray:6 5}
                .cc-trait.lie,.cc-trait.sugg{cursor:pointer}.cc-trait.lie:hover .vu{stroke:#dc2626}.cc-trait.sugg:hover .vu{stroke:#16a34a}
                .cc-temp{fill:none;stroke:#f59e0b;stroke-width:2.5;stroke-dasharray:4 4}
                @media (max-width:900px){.cc-zone{grid-template-columns:1fr 60px 1fr}}
            </style>`);
        }
    },
};
