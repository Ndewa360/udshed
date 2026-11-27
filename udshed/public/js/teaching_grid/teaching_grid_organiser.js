window.Udshed = window.Udshed || {};
window.Udshed.TeachingGrid = window.Udshed.TeachingGrid || {};

// Organisation des UE par glisser-déposer : chaque UE est une colonne, chaque cours une
// carte que l'on dépose dans une autre UE (enregistré immédiatement côté serveur).
window.Udshed.TeachingGrid.Organiser = {
    open(filters, grid, onDone = () => {}) {
        const esc = (v) => frappe.utils.escape_html(v === null || v === undefined ? "" : String(v));
        const fmt = (v) => (Number(v) || 0).toLocaleString("fr-FR", { maximumFractionDigits: 2 });
        const ues = (grid || []).filter((u) => u.ue_code && u.ue_code !== "UNKNOW").map((u) => ({
            code: u.ue_code, intitule: u.ue_title || "", courses: u.courses.map((c) => ({ ...c })),
        }));
        if (!ues.length) {
            Udshed.Messages.warning(__("Cette grille n'est pas organisée en UE."));
            return;
        }
        let modifie = false;

        const d = new frappe.ui.Dialog({
            title: __("Organiser les UE"),
            size: "extra-large",
            fields: [{ fieldtype: "HTML", fieldname: "board" }],
            primary_action_label: __("Terminer"),
            primary_action() { d.hide(); },
            secondary_action_label: __("Nouvelle UE"),
            secondary_action() { nouvelle(); },
        });
        d.onhide = () => { if (modifie) onDone(); };

        function render() {
            const cartes = ues.map((ue) => {
                const credits = ue.courses.reduce((s, c) => s + (Number(c.credits) || 0), 0);
                const cours = ue.courses.map((c) => `
                    <div class="tg-org-cours" draggable="true" data-tu="${esc(c.teaching_unit)}">
                        <div class="tg-org-ligne"><strong>${esc(c.code)}</strong><span class="tg-org-cr">${fmt(c.credits)} cr</span></div>
                        <div class="tg-org-titre">${esc(c.title)}</div>
                        ${c.classes_partagees ? `<span class="indicator-pill blue tg-org-tc">${__("Tronc commun")}</span>` : ""}
                    </div>`).join("");
                return `
                    <div class="tg-org-ue${ue.nouvelle ? " nouvelle" : ""}" data-ue="${esc(ue.code)}">
                        <div class="tg-org-tete">
                            <div><strong>${esc(ue.code)}</strong> <span class="text-muted">${esc(ue.intitule)}</span></div>
                            <span class="tg-org-total">${fmt(credits)} ${__("crédits")}</span>
                        </div>
                        <div class="tg-org-corps">${cours || `<div class="tg-org-vide">${__("Déposez un cours ici")}</div>`}</div>
                    </div>`;
            }).join("");
            d.fields_dict.board.$wrapper.html(`
                <p class="text-muted small">${__("Faites glisser un cours vers une autre UE : le déplacement est enregistré aussitôt. « Nouvelle UE » ajoute une colonne vide, créée au premier cours déposé.")}</p>
                <div class="tg-org-board">${cartes}</div>
                <style>
                    .tg-org-board{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;max-height:65vh;overflow:auto;padding:2px}
                    .tg-org-ue{border:1px solid var(--border-color);border-radius:10px;background:var(--subtle-fg,#f8f9fa);display:flex;flex-direction:column;min-height:140px}
                    .tg-org-ue.nouvelle{border-style:dashed}
                    .tg-org-ue.survol{border-color:var(--primary);box-shadow:0 0 0 2px var(--primary-light,rgba(40,96,144,.15))}
                    .tg-org-tete{padding:8px 10px;border-bottom:1px solid var(--border-color);display:flex;justify-content:space-between;gap:8px;align-items:baseline}
                    .tg-org-total{font-size:12px;color:var(--text-muted);white-space:nowrap}
                    .tg-org-corps{padding:8px;display:flex;flex-direction:column;gap:6px;flex:1}
                    .tg-org-cours{background:var(--card-bg,#fff);border:1px solid var(--border-color);border-radius:8px;padding:6px 8px;cursor:grab}
                    .tg-org-cours.en-cours{opacity:.4}
                    .tg-org-ligne{display:flex;justify-content:space-between;gap:6px}
                    .tg-org-cr{font-size:12px;color:var(--text-muted)}
                    .tg-org-titre{font-size:12px}
                    .tg-org-tc{margin-top:4px}
                    .tg-org-vide{color:var(--text-muted);font-size:12px;text-align:center;padding:24px 0;border:1px dashed var(--border-color);border-radius:8px}
                </style>`);
            lier();
        }

        function lier() {
            const $b = d.fields_dict.board.$wrapper;
            $b.find(".tg-org-cours").on("dragstart", (e) => {
                e.originalEvent.dataTransfer.setData("text/plain", $(e.currentTarget).attr("data-tu"));
                $(e.currentTarget).addClass("en-cours");
            }).on("dragend", (e) => $(e.currentTarget).removeClass("en-cours"));
            $b.find(".tg-org-ue").on("dragover", (e) => {
                e.preventDefault();
                $(e.currentTarget).addClass("survol");
            }).on("dragleave", (e) => $(e.currentTarget).removeClass("survol"))
              .on("drop", (e) => {
                e.preventDefault();
                $(e.currentTarget).removeClass("survol");
                deplacer(e.originalEvent.dataTransfer.getData("text/plain"), $(e.currentTarget).attr("data-ue"));
            });
        }

        function deplacer(tu, codeCible) {
            const source = ues.find((u) => u.courses.some((c) => c.teaching_unit === tu));
            const cible = ues.find((u) => u.code === codeCible);
            if (!source || !cible || source === cible) return;
            const cours = source.courses.find((c) => c.teaching_unit === tu);
            const envoyer = (confirme) => frappe.call({
                method: "udshed.api.grille_edition.changer_ue",
                args: { ...filters, teaching_unit: tu, ue_code: cible.code, ue_intitule: cible.intitule,
                        appliquer_au_tronc_commun: confirme ? 1 : 0 },
                freeze: true,
                callback: (r) => {
                    source.courses = source.courses.filter((c) => c !== cours);
                    cible.courses.push(cours);
                    cible.nouvelle = false;
                    modifie = true;
                    render();
                    const res = r.message || {};
                    if (res.avertissement) Udshed.Messages.warning(res.avertissement);
                    else Udshed.Messages.success(__("{0} déplacé vers {1}.", [cours.code, cible.code]));
                },
                error: (err) => Udshed.Messages.error(err, __("Déplacement refusé")),
            });
            if (cours.classes_partagees) {
                frappe.confirm(__("{0} est un cours de tronc commun : il changera d'UE dans toutes ses classes. Continuer ?", [cours.code]),
                    () => envoyer(true));
            } else {
                envoyer(false);
            }
        }

        function nouvelle() {
            frappe.prompt([
                { fieldname: "code", label: __("Code de l'UE"), fieldtype: "Data", reqd: 1 },
                { fieldname: "intitule", label: __("Intitulé"), fieldtype: "Data", reqd: 1 },
            ], (v) => {
                const code = (v.code || "").trim();
                if (ues.some((u) => u.code.toLowerCase() === code.toLowerCase())) {
                    Udshed.Messages.warning(__("L'UE {0} est déjà dans la grille.", [code]));
                    return;
                }
                ues.push({ code, intitule: (v.intitule || "").trim(), courses: [], nouvelle: true });
                render();
            }, __("Nouvelle UE"), __("Ajouter"));
        }

        render();
        d.show();
    },
};
