window.Udshed = window.Udshed || {};
window.Udshed.Insight = window.Udshed.Insight || {};

/**
 * Tableau de bord Insight, commun aux pages « insight-academique » et
 * « insight-financier ». Toutes les données viennent de
 * udshed.insight.api.tableau_de_bord (moteur unique côté serveur).
 *
 * Navigation : fil d'Ariane et lignes de répartition cliquables
 * (année › faculté › filière › classe ; enseignant › classes).
 */
window.Udshed.Insight.Dashboard = class {
    constructor(wrapper, mode) {
        this.mode = mode; // "academique" | "financier"
        this.wrapper = wrapper;
        this.filtres = { academic_year: null, semestre: null, faculty: null, filiere: null, niveau: null, teacher: null, type_seance: null };
        this.requete = 0;
        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: mode === "financier" ? __("Insight financier — vacations") : __("Insight académique — avancement des cours"),
            single_column: true,
        });
        this.$corps = $('<div class="uds-insight"></div>').appendTo(this.page.main);
        this.page.set_primary_action(__("Exporter Excel"), () => this.exporter(), "download");
        this.page.set_secondary_action(__("Actualiser"), () => this.charger());
        this.creer_filtres();
    }

    // ------------------------------------------------------------------ filtres
    creer_filtres() {
        const p = this.page;
        const champ = (df) => p.add_field({ ...df, change: () => this.sur_filtre(df.fieldname) });
        this.champs = {
            academic_year: champ({ fieldtype: "Link", fieldname: "academic_year", label: __("Année académique"), options: "Academic Year" }),
            semestre: champ({ fieldtype: "Select", fieldname: "semestre", label: __("Semestre"),
                options: [{ value: "", label: __("Tous les semestres") }, "Semestre 1", "Semestre 2"] }),
            faculty: champ({ fieldtype: "Select", fieldname: "faculty", label: __("Faculté") }),
            filiere: champ({ fieldtype: "Select", fieldname: "filiere", label: __("Filière") }),
            niveau: champ({ fieldtype: "Select", fieldname: "niveau", label: __("Niveau") }),
            teacher: champ({ fieldtype: "Select", fieldname: "teacher", label: __("Enseignant") }),
            type_seance: champ({ fieldtype: "Select", fieldname: "type_seance", label: __("Type de séance"),
                options: [{ value: "", label: __("Tous les types") }, { value: "CM", label: "CM" }, { value: "TD", label: "TD" },
                    { value: "TP", label: "TP" }, { value: "CC", label: __("Contrôle continu") },
                    { value: "EXAMEN", label: __("Examen") }, { value: "RATTRAPAGE", label: __("Rattrapage") }] }),
        };
        frappe.xcall("udshed.api.reference.annee_courante").then((annee) => {
            if (annee) this.appliquer({ academic_year: annee });
            else this.afficher_message(__("Choisissez une année académique."));
        });
    }

    sur_filtre(nom) {
        if (this._synchro) return;
        const valeur = this.champs[nom].get_value() || null;
        if (valeur === this.filtres[nom]) return;
        const nouveaux = { ...this.filtres, [nom]: valeur };
        // Un niveau supérieur qui change invalide les niveaux inférieurs.
        const cascade = { academic_year: ["faculty", "filiere", "niveau", "teacher"], faculty: ["filiere", "niveau"], filiere: ["niveau"] };
        (cascade[nom] || []).forEach((k) => { nouveaux[k] = null; });
        this.appliquer(nouveaux);
    }

    async appliquer(filtres) {
        this.filtres = { ...this.filtres, ...filtres };
        await this.charger_options();
        this.synchroniser_champs();
        this.charger();
    }

    async charger_options() {
        if (!this.filtres.academic_year) return;
        const r = await frappe.call({
            method: "udshed.insight.api.options_filtres",
            args: { mode: this.mode, academic_year: this.filtres.academic_year, faculty: this.filtres.faculty, filiere: this.filtres.filiere },
        });
        const o = r.message || {};
        const vide = (label) => [{ value: "", label }];
        this.options = o;
        this.champs.faculty.df.options = vide(__("Toutes les facultés")).concat(o.facultes || []);
        this.champs.filiere.df.options = vide(__("Toutes les filières")).concat(o.filieres || []);
        this.champs.niveau.df.options = vide(this.filtres.filiere ? __("Tous les niveaux") : __("Choisir une filière")).concat(o.niveaux || []);
        this.champs.teacher.df.options = vide(__("Tous les enseignants")).concat(o.enseignants || []);
        Object.values(this.champs).forEach((c) => c.refresh());
        this.champs.teacher.$wrapper.toggle(!o.enseignant_seul);
    }

    synchroniser_champs() {
        this._synchro = true;
        Object.entries(this.champs).forEach(([nom, champ]) => champ.set_value(this.filtres[nom] || ""));
        this._synchro = false;
    }

    // ------------------------------------------------------------------ données
    charger() {
        if (!this.filtres.academic_year) return;
        const n = ++this.requete;
        this.$corps.html(`<div class="text-center text-muted p-5"><i class="fa fa-spinner fa-spin"></i> ${__("Calcul des statistiques...")}</div>`);
        frappe.call({
            method: "udshed.insight.api.tableau_de_bord",
            args: { mode: this.mode, ...this.filtres },
            callback: (r) => { if (n === this.requete) this.rendre(r.message); },
            error: (err) => {
                if (n !== this.requete) return;
                // Erreur explicite (droits, filtre invalide…) : jamais de message générique.
                const msg = (err && err._server_messages && JSON.parse(JSON.parse(err._server_messages)[0]).message) || __("Impossible de calculer les statistiques.");
                this.afficher_message(msg, "danger");
            },
        });
    }

    exporter() {
        if (!this.filtres.academic_year) return;
        const params = new URLSearchParams({ mode: this.mode });
        Object.entries(this.filtres).forEach(([k, v]) => { if (v) params.append(k, v); });
        window.open(`/api/method/udshed.insight.api.exporter?${params.toString()}`);
    }

    afficher_message(texte, niveau = "info") {
        this.$corps.html(`<div class="alert alert-${niveau} mt-3">${frappe.utils.escape_html(texte)}</div>`);
    }

    // ------------------------------------------------------------------ rendu
    esc(v) { return frappe.utils.escape_html(v === null || v === undefined ? "" : String(v)); }
    h(v) { return `${(Number(v) || 0).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} h`; }
    pct(v) { return v === null || v === undefined ? "—" : `${(Number(v) || 0).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} %`; }
    argent(v) {
        const n = Number(v) || 0;
        try {
            return n.toLocaleString("fr-FR", { style: "currency", currency: this.devise || "XAF", maximumFractionDigits: 0 });
        } catch (e) {
            return `${n.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} ${this.esc(this.devise || "")}`;
        }
    }
    couleur(taux) { return taux >= 90 ? "green" : taux >= 75 ? "blue" : taux >= 50 ? "orange" : "red"; }
    barre(taux, attendu) {
        const t = Math.max(0, Math.min(100, Number(taux) || 0));
        const repere = attendu === null || attendu === undefined ? "" :
            `<span class="ui-repere" style="left:${Math.min(100, attendu)}%" title="${this.esc(__("Avancement attendu : {0}", [this.pct(attendu)]))}"></span>`;
        return `<div class="ui-barre"><span class="ui-rempli ${this.couleur(t)}" style="width:${t}%"></span>${repere}</div>`;
    }

    rendre(data) {
        this.data = data;
        this.devise = data.devise;
        const fin = this.mode === "financier";
        const k = data.kpis;
        this.$corps.html(`
            ${this.rendre_ariane(data)}
            <div class="ui-kpis">${fin ? this.kpis_financiers(k) : this.kpis_academiques(k)}</div>
            ${this.rendre_alertes(data.alertes)}
            <div class="ui-grille2">
                <div class="ui-carte"><h6>${fin ? __("Évolution cumulée : engagé et réalisé") : __("Évolution cumulée : heures planifiées et effectuées")}</h6><div class="ui-graph-evol"></div></div>
                <div class="ui-carte"><h6>${__("Statut des cours")}</h6><div class="ui-graph-statuts"></div>
                    <div class="small text-muted">${__("Séances par type")} : ${data.types.map((t) => `${this.esc(t.libelle)} ${t.valeur}`).join(" · ") || "—"}</div></div>
            </div>
            ${this.rendre_lignes(data)}
            ${this.rendre_cours(data)}
        `);
        this.$corps.find("[data-filtre]").on("click", (e) => {
            e.preventDefault();
            const filtre = JSON.parse($(e.currentTarget).attr("data-filtre"));
            const garde = { academic_year: this.filtres.academic_year, semestre: this.filtres.semestre, type_seance: this.filtres.type_seance };
            if (data.vue === "enseignant" && !filtre.teacher) garde.teacher = this.filtres.teacher;
            this.appliquer({ faculty: null, filiere: null, niveau: null, teacher: null, ...garde, ...filtre });
        });
        this.$corps.find(".ui-fiche").on("click", (e) => {
            const $b = $(e.currentTarget);
            frappe.call({
                method: "udshed.api.generate_teacher_doc.download_progression_cours",
                args: { teaching_unit: $b.data("tu"), teacher: data.filtres.teacher, nbre_heure: $b.data("fait"), total_heure: $b.data("total") },
                freeze: true,
                freeze_message: __("Génération de la fiche de progression..."),
                callback: (r) => Udshed.Utils.make_download_file_word(r.message, "fiche_de_progression"),
            });
        });
        this.$corps.find(".ui-recherche").on("input", (e) => {
            const q = e.target.value.toLowerCase();
            this.$corps.find(".ui-ligne-cours").each(function () { $(this).toggle($(this).text().toLowerCase().includes(q)); });
        });
        this.graphiques(data);
    }

    rendre_ariane(data) {
        const items = data.fil_ariane.map((f, i) => {
            const dernier = i === data.fil_ariane.length - 1;
            return dernier ? `<strong>${this.esc(f.libelle)}</strong>`
                : `<a href="#" data-filtre='${this.esc(JSON.stringify({ ...{ faculty: null, filiere: null, niveau: null, teacher: null }, ...f.filtre }))}'>${this.esc(f.libelle)}</a>`;
        });
        return `<div class="ui-ariane">${items.join(" › ")}
            <span class="text-muted small ml-2">· ${this.esc(data.filtres.academic_year)}${data.filtres.semestre ? " · " + this.esc(data.filtres.semestre) : ""} · ${__("au {0}", [frappe.datetime.str_to_user(data.date)])}</span></div>`;
    }

    carte(label, valeur, sous, couleur) {
        return `<div class="ui-kpi ${couleur || ""}"><div class="l">${label}</div><div class="v">${valeur}</div><div class="s">${sous || ""}</div></div>`;
    }

    kpis_academiques(k) {
        return [
            this.carte(__("Volume prévu"), this.h(k.cible), __("{0} cours", [k.cours])),
            this.carte(__("Planifié"), this.h(k.planifie), __("couverture {0}", [this.pct(k.couverture)]), k.couverture >= 100 ? "green" : "orange"),
            this.carte(__("Effectué"), this.h(k.echu), `${__("réalisation")} ${this.pct(k.completion)}${k.attendu !== null ? " · " + __("attendu") + " " + this.pct(k.attendu) : ""}`, this.couleur(k.completion)),
            this.carte(__("Pointé « Fait »"), this.h(k.pointe), __("{0} des séances passées", [this.pct(k.taux_pointage)])),
            this.carte(__("Cours en retard"), k.en_retard, __("{0} terminés · {1} non planifiés", [k.statuts.termine + k.statuts.depassement, k.statuts.non_planifie]), k.en_retard ? "red" : "green"),
            this.carte(__("Séances"), k.seances, __("{0} annulées · {1} évaluations", [k.annulees, k.evaluations])),
        ].join("");
    }

    kpis_financiers(k) {
        const reste = Math.max(0, (k.budget || 0) - (k.realise || 0));
        return [
            this.carte(__("Budget vacations"), this.argent(k.budget), __("{0} cours · {1}", [k.cours, this.h(k.cible)])),
            this.carte(__("Engagé (planifié)"), this.argent(k.engage), this.pct(k.taux_engage), k.taux_engage > 100 ? "red" : "blue"),
            this.carte(__("Réalisé (séances passées)"), this.argent(k.realise), this.pct(k.taux_realise), this.couleur(k.taux_realise)),
            this.carte(__("Reste à réaliser"), this.argent(reste), __("sur le budget")),
            this.carte(__("Heures effectuées"), this.h(k.echu), __("réalisation {0}", [this.pct(k.completion)])),
            this.carte(__("Cours en retard"), k.en_retard, __("{0} séances annulées", [k.annulees]), k.en_retard ? "red" : "green"),
        ].join("");
    }

    rendre_alertes(alertes) {
        if (!alertes.length) return `<div class="ui-ok">✓ ${__("Aucune alerte sur ce périmètre.")}</div>`;
        const icones = { danger: "⛔", warning: "⚠", info: "ℹ" };
        return `<div class="ui-alertes">${alertes.map((a) => `<div class="ui-alerte ${a.niveau}">${icones[a.niveau] || ""} ${this.esc(a.message)}</div>`).join("")}</div>`;
    }

    rendre_lignes(data) {
        if (!data.lignes.length) return "";
        const fin = this.mode === "financier";
        const titres = { annee: __("Par faculté"), faculte: __("Par filière"), filiere: __("Par classe"), enseignant: __("Par classe") };
        const lignes = data.lignes.map((l) => `
            <tr class="ui-cliquable" data-filtre='${this.esc(JSON.stringify(l.filtre))}' title="${this.esc(__("Afficher le détail"))}">
                <td><strong>${this.esc(l.libelle)}</strong></td>
                <td class="text-right">${l.cours}</td>
                <td class="text-right">${this.h(l.cible)}</td>
                <td class="text-right">${this.h(l.echu)}</td>
                <td style="min-width:160px">${this.barre(l.completion, l.attendu)}<span class="small">${this.pct(l.completion)}</span></td>
                <td class="text-right">${l.en_retard ? `<span class="indicator-pill red">${l.en_retard}</span>` : "0"}</td>
                ${fin ? `<td class="text-right">${this.argent(l.budget)}</td><td class="text-right">${this.argent(l.engage)}</td>
                         <td class="text-right">${this.argent(l.realise)} <span class="small text-muted">(${this.pct(l.taux_realise)})</span></td>` : ""}
            </tr>`).join("");
        return `<div class="ui-carte"><h6>${titres[data.vue] || __("Répartition")} <span class="small text-muted">— ${__("cliquez une ligne pour le détail")}</span></h6>
            <div class="ui-table"><table class="table table-sm table-hover">
                <thead><tr><th></th><th class="text-right">${__("Cours")}</th><th class="text-right">${__("Prévu")}</th><th class="text-right">${__("Effectué")}</th>
                    <th>${__("Réalisation")}</th><th class="text-right">${__("En retard")}</th>
                    ${fin ? `<th class="text-right">${__("Budget")}</th><th class="text-right">${__("Engagé")}</th><th class="text-right">${__("Réalisé")}</th>` : ""}</tr></thead>
                <tbody>${lignes}</tbody></table></div></div>`;
    }

    rendre_cours(data) {
        const fin = this.mode === "financier";
        // Vue enseignant (académique) : fiche de progression de cours (Word) par cours.
        const fiche = !fin && data.vue === "enseignant" && data.filtres.teacher;
        const statuts = {
            non_planifie: ["gray", __("Non planifié")], en_cours: ["blue", __("En cours")], termine: ["green", __("Terminé")],
            depassement: ["orange", __("Dépassement")], sans_volume: ["gray", __("Sans volume")],
        };
        const lignes = data.cours.map((c) => {
            const [coul, lib] = statuts[c.statut] || ["gray", c.statut];
            const drapeaux = [
                c.en_retard ? `<span class="indicator-pill red" title="${this.esc(__("Réalisé {0} pour {1} attendus", [this.pct(c.completion), this.pct(c.attendu_pct)]))}">${__("en retard")}</span>` : "",
                c.planning_incomplet ? `<span class="indicator-pill orange" title="${this.esc(__("Planifié {0} du volume", [this.pct(c.couverture)]))}">${__("planning incomplet")}</span>` : "",
                c.surplanifie ? `<span class="indicator-pill orange">${__("sur-planifié")}</span>` : "",
                c.tronc_commun ? `<span class="indicator-pill blue">${__("tronc commun")}</span>` : "",
                c.lie ? `<span class="indicator-pill purple">🔗 ${__("lié")}</span>` : "",
            ].join(" ");
            return `<tr class="ui-ligne-cours">
                <td><strong>${this.esc(c.code)}</strong> ${this.esc(c.intitule)}<div class="small text-muted">${this.esc(c.classes.join(", "))}</div>
                    <div class="small text-muted">${this.esc(c.enseignants.join(", ")) || `<span class="text-danger">${__("aucun enseignant")}</span>`}</div></td>
                <td class="text-right">${this.h(c.cible)}</td>
                <td class="text-right">${this.h(c.planifie)}</td>
                <td class="text-right">${this.h(c.echu)}<div class="small text-muted">${__("pointé")} ${this.h(c.pointe)}</div></td>
                <td style="min-width:150px">${this.barre(c.completion, c.attendu_pct)}<span class="small">${this.pct(c.completion)}</span></td>
                <td><span class="indicator-pill ${coul}">${lib}</span> ${drapeaux}</td>
                ${fin ? `<td class="text-right">${this.argent(c.budget)}</td><td class="text-right">${this.argent(c.engage)}</td><td class="text-right">${this.argent(c.realise)}</td>` : ""}
                ${fiche ? `<td><button class="btn btn-xs btn-default ui-fiche" data-tu="${this.esc(c.name)}" data-fait="${c.echu}" data-total="${c.cible}">
                    ${__("Fiche de progression")}</button></td>` : ""}
            </tr>`;
        }).join("");
        return `<div class="ui-carte"><div class="d-flex justify-content-between align-items-center flex-wrap" style="gap:8px">
                <h6 class="mb-0">${__("Cours")} (${data.cours.length}) <span class="small text-muted">— ${__("en retard d'abord")}</span></h6>
                <input class="form-control input-sm ui-recherche" style="max-width:260px" placeholder="${__("Rechercher un cours, une classe, un enseignant")}">
            </div>
            <div class="ui-table"><table class="table table-sm">
                <thead><tr><th>${__("Cours")}</th><th class="text-right">${__("Prévu")}</th><th class="text-right">${__("Planifié")}</th>
                    <th class="text-right">${__("Effectué")}</th><th>${__("Réalisation")}</th><th>${__("Statut")}</th>
                    ${fin ? `<th class="text-right">${__("Budget")}</th><th class="text-right">${__("Engagé")}</th><th class="text-right">${__("Réalisé")}</th>` : ""}
                    ${fiche ? "<th></th>" : ""}</tr></thead>
                <tbody>${lignes || `<tr><td colspan="9" class="text-muted text-center">${__("Aucun cours sur ce périmètre.")}</td></tr>`}</tbody>
            </table></div></div>`;
    }

    graphiques(data) {
        const fin = this.mode === "financier";
        const evol = data.evolution;
        const $e = this.$corps.find(".ui-graph-evol");
        if (evol.length) {
            new frappe.Chart($e[0], {
                type: "line", height: 240,
                data: {
                    labels: evol.map((p) => frappe.datetime.str_to_user(p.semaine)),
                    datasets: fin
                        ? [{ name: __("Engagé cumulé"), values: evol.map((p) => p.engage_cumule) },
                           { name: __("Réalisé cumulé"), values: evol.map((p) => p.realise_cumule) }]
                        : [{ name: __("Planifié cumulé (h)"), values: evol.map((p) => p.planifie_cumule) },
                           { name: __("Effectué cumulé (h)"), values: evol.map((p) => p.echu_cumule) }],
                },
                colors: ["#3b82f6", "#16a34a"],
                lineOptions: { regionFill: 1, hideDots: evol.length > 20 },
                axisOptions: { xIsSeries: true },
            });
        } else {
            $e.html(`<div class="text-muted small p-4 text-center">${__("Aucune séance planifiée.")}</div>`);
        }
        const s = data.kpis.statuts;
        const valeurs = [s.non_planifie, s.en_cours, s.termine, s.depassement];
        const $s = this.$corps.find(".ui-graph-statuts");
        if (valeurs.some((v) => v)) {
            new frappe.Chart($s[0], {
                type: "donut", height: 220,
                data: { labels: [__("Non planifiés"), __("En cours"), __("Terminés"), __("Dépassement")], datasets: [{ values: valeurs }] },
                colors: ["#9ca3af", "#3b82f6", "#16a34a", "#f59e0b"],
            });
        } else {
            $s.html(`<div class="text-muted small p-4 text-center">${__("Aucun cours.")}</div>`);
        }
    }
};
