window.Udshed = window.Udshed || {};
window.Udshed.TeachingGrid = window.Udshed.TeachingGrid || {};

window.Udshed.TeachingGrid.Dialog = {
    
    
// Ouvrir le dialogue d'assignation des enseignants
open_teacher_assignment_dialog(courseCode,teachingUnitCode, rowIndex, colIndex,filters,callbackFunction) {
    
    // Créer un dialogue avec un grid lié au child table de votre doctype
    var dialog = new frappe.ui.Dialog({
        title: __('Gestion des enseignants - {0}', [courseCode]),
        size: 'large',
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'info_html',
                options: `<div class="alert alert-info">
                    <i class="fa fa-info-circle"></i> 
                    Gérez les enseignants assignés à ce cours. Les modifications sont automatiquement sauvegardées.
                </div>`
            },
            {
                fieldtype: 'Section Break'
            },
            {
                fieldtype: 'Table',
                fieldname: 'table_enseignant',
                label: __('Enseignants'),
                options: 'Course Teacher Item',
                description: 'Liste des enseignants pour ce cours',
                fields: [
                    {
                        fieldtype: 'Link',
                        fieldname: 'enseignant',
                        label: 'Enseignant',
                        options: 'Teacher', // Votre doctype enseignant
                        in_list_view: 1,
                        reqd: 1,
                        columns: 4
                    },
                    {
                        fieldtype: 'Select',
                        fieldname: 'type_de_cours',
                        label: 'Type',
                        options: [
                            "Cours Magistral (CM)",
                            "Travaux Pratique (TP)",
                            "Travaux Dirigés (TD)"
                        ],
                        default: 'Cours Magistral (CM)',
                        in_list_view: 1,
                        columns: 3
                    }
                ],
            },
            {
                fieldtype: 'Section Break'
            },
            {
                fieldtype: 'HTML',
                fieldname: 'preview_html',
                options: '<div class="teacher-hours-preview">Prévisualisation de la répartition des heures</div>'
            }
        ],
        data:[],
        primary_action_label: __('Enregistrer'),        
        primary_action: function(values) {
            console.log("Field ",values)
            Udshed.TeachingGrid.UtilsQueries.update_teacher_list(teachingUnitCode,values.table_enseignant?values.table_enseignant:[],()=>{
                    dialog.hide()
                    callbackFunction()
                }
            );
        }
    });

    // Charger les données du cours pour la prévisualisation
    Udshed.TeachingGrid.Dialog.load_course_data_for_preview(teachingUnitCode, dialog,filters.academic_year);
        
    dialog.show();
},

load_course_data_for_preview(teachingUnitCode,dialog,academic_year)
{
    Udshed.TeachingGrid.UtilsQueries.load_doctype(
        {
            doctype: 'Teaching Unit',
            filters: {
                'name': teachingUnitCode,
            },
            fields: ['*']
        },
        (data)=>{
            if(!data) return;
            teacher_list = data.table_enseignant
            console.log("Teacher list ",teacher_list)
            // Récupérer le grid
            var grid = dialog.fields_dict.table_enseignant.grid;

            // Ajouter les données existantes
            if (teacher_list && teacher_list.length > 0) {
                grid.df.data = teacher_list.map((t)=>({
                    enseignant:t.enseignant,
                    type_de_cours: t.type_de_cours
                }))
                grid.refresh();
            } else {
                // Vider le grid
                grid.df.data = [];
                grid.refresh();
            }

        },
        "Chargement de la liste des enseignants du cours",
    )
},

// Mettre à jour la prévisualisation à partir du grid
update_teacher_preview_from_grid(courseDocName,teachingUnitName, dialog) {

    
    // Récupérer les données du grid
    var gridData = dialog.fields_dict.teachers.grid.get_data();
    
    // Créer un objet cours temporaire avec les données du grid
    Udshed.TeachingGrid.UtilsQueries.load_doctype_list(
        {
            doctype: 'Teaching Unit',
            name: teachingUnitName
        },
        (data)=>{
            if(data){
                var tempDoc = r.message;
                tempDoc.teachers = gridData;
                Udshed.TeachingGrid.Dialog.update_teacher_preview(tempDoc, dialog);
            }
        }
    )
},
   	 
open_add_course_dialog(filters, onDone = () => {}) {
    const d = new frappe.ui.Dialog({
        title: __("Ajouter un cours à la grille"),
        fields: [
            { fieldtype: "HTML", options: `<div class="text-muted small">${__("Si le code existe déjà pour l'année, le cours est rattaché à cette classe (tronc commun) avec ses propres crédits.")}</div>` },
            { fieldtype: "Data", fieldname: "code", label: __("Code du cours"), reqd: 1 },
            { fieldtype: "Data", fieldname: "intitule_cours", label: __("Intitulé") },
            { fieldtype: "Float", fieldname: "credits", label: __("Crédits (pour cette classe)"), reqd: 1, default: 3 },
            { fieldtype: "Column Break" },
            { fieldtype: "Select", fieldname: "ue_code", label: __("UE") },
            { fieldtype: "Data", fieldname: "ue_intitule", label: __("Intitulé de la nouvelle UE"),
              depends_on: "eval:doc.ue_code==='__nouvelle__'" },
            { fieldtype: "Data", fieldname: "ue_nouveau_code", label: __("Code de la nouvelle UE"),
              depends_on: "eval:doc.ue_code==='__nouvelle__'" },
            { fieldtype: "Section Break", label: __("Volume horaire") },
            { fieldtype: "Int", fieldname: "nombre_dheure_cm", label: "CM", default: 0 },
            { fieldtype: "Int", fieldname: "nombre_dheure_td", label: "TD", default: 0 },
            { fieldtype: "Column Break" },
            { fieldtype: "Int", fieldname: "nombre_dheure_tp", label: "TP", default: 0 },
            { fieldtype: "Int", fieldname: "nombre_dheure_tpe", label: "TPE", default: 0 },
            { fieldtype: "Section Break" },
            { fieldtype: "HTML", fieldname: "coherence" },
        ],
        primary_action_label: __("Ajouter"),
        primary_action(v) {
            const nouvelleUe = v.ue_code === "__nouvelle__";
            frappe.call({
                method: "udshed.api.teaching_grid.ajouter_cours",
                args: {
                    ...filters,
                    code: v.code,
                    intitule_cours: v.intitule_cours,
                    credits: v.credits,
                    ue_code: nouvelleUe ? v.ue_nouveau_code : v.ue_code,
                    ue_intitule: nouvelleUe ? v.ue_intitule : null,
                    nombre_dheure_cm: v.nombre_dheure_cm, nombre_dheure_td: v.nombre_dheure_td,
                    nombre_dheure_tp: v.nombre_dheure_tp, nombre_dheure_tpe: v.nombre_dheure_tpe,
                },
                freeze: true,
                callback: (r) => {
                    const res = r.message || {};
                    d.hide();
                    Udshed.Messages.success(res.rattache ? __("Cours existant rattaché à la classe.") : __("Cours ajouté."));
                    if (res.avertissement) Udshed.Messages.warning(res.avertissement);
                    onDone();
                },
                error: (err) => Udshed.Messages.error(err, __("Ajout impossible")),
            });
        },
    });

    // Rappel en direct de la règle 1 crédit ≈ 10-15 h (CM + TD + TP).
    const majCoherence = () => {
        const v = d.get_values(true) || {};
        const credits = Number(v.credits) || 0;
        const heures = (v.nombre_dheure_cm || 0) + (v.nombre_dheure_td || 0) + (v.nombre_dheure_tp || 0);
        const ok = credits > 0 && heures >= credits * 10 && heures <= credits * 15;
        d.fields_dict.coherence.$wrapper.html(
            `<div class="small ${ok ? "text-success" : "text-warning"}">${__("Norme : {0} à {1} h de CM+TD+TP pour {2} crédit(s) — saisi : {3} h", [credits * 10, credits * 15, credits, heures])}</div>`
        );
    };
    ["credits", "nombre_dheure_cm", "nombre_dheure_td", "nombre_dheure_tp"].forEach((f) => {
        d.fields_dict[f].$input && d.fields_dict[f].$input.on("input change", majCoherence);
    });

    frappe.call({
        method: "udshed.api.teaching_grid.lister_ues",
        args: { ...filters },
        callback: (r) => {
            const ues = (r.message || []).map((u) => ({ value: u.code, label: `${u.code} — ${u.intitule || ""}` }));
            ues.push({ value: "__nouvelle__", label: __("+ Nouvelle UE") });
            d.set_df_property("ue_code", "options", ues);
            majCoherence();
        },
    });
    d.show();
},

open_delete_course_dialog(filters, courses, onDone = () => {}) {
    if (!courses.length) {
        Udshed.Messages.warning(__("Aucun cours dans cette grille."));
        return;
    }
    const d = new frappe.ui.Dialog({
        title: __("Retirer un cours de la grille"),
        fields: [
            {
                fieldtype: "Select", fieldname: "teaching_unit", label: __("Cours"), reqd: 1,
                options: courses.map((c) => ({ value: c.teaching_unit, label: `${c.code} — ${c.title}` })),
                change() { verifier(); },
            },
            { fieldtype: "HTML", fieldname: "etat" },
        ],
        primary_action_label: __("Retirer"),
        primary_action(v) {
            frappe.confirm(__("Retirer définitivement ce cours de la grille de la classe ?"), () => {
                frappe.call({
                    method: "udshed.api.teaching_grid.supprimer_cours",
                    args: { ...filters, teaching_unit: v.teaching_unit },
                    freeze: true,
                    callback: (r) => {
                        const res = r.message || {};
                        d.hide();
                        Udshed.Messages.success(res.supprime
                            ? __("Cours supprimé (il n'était utilisé par aucune autre classe).")
                            : __("Cours retiré de la grille de la classe."));
                        onDone();
                    },
                    error: (err) => Udshed.Messages.error(err, __("Suppression impossible")),
                });
            });
        },
    });
    function verifier() {
        const tu = d.get_value("teaching_unit");
        if (!tu) return;
        frappe.call({
            method: "udshed.api.teaching_grid.dependances_suppression",
            args: { ...filters, teaching_unit: tu },
            callback: (r) => {
                const res = r.message || {};
                const esc = frappe.utils.escape_html;
                let html = res.bloque
                    ? `<div class="alert alert-danger">🔒 ${__("Suppression impossible : ce cours a des données pour cette classe")} (${esc(res.dependances)}).</div>`
                    : `<div class="alert alert-success">${__("Aucune donnée ne dépend de ce cours pour cette classe : il peut être retiré.")}</div>`;
                if ((res.classes_partagees || []).length) {
                    html += `<div class="text-muted small">${__("Cours partagé avec : {0}. Il reste dans leurs grilles.", [esc(res.classes_partagees.join(", "))])}</div>`;
                }
                d.fields_dict.etat.$wrapper.html(html);
                d.get_primary_btn().prop("disabled", Boolean(res.bloque));
            },
        });
    }
    d.show();
    verifier();
},

show_import_dialog(filters, onAfterImported = (data) => {}) {
    const esc = (v) => frappe.utils.escape_html(v === null || v === undefined ? "" : String(v));
    const fmt = (v) => (Number(v) || 0).toLocaleString("fr-FR", { maximumFractionDigits: 2 });
    const STATUTS = {
        nouveau: ["green", __("Nouveau")],
        mis_a_jour: ["blue", __("Mis à jour")],
        ajout_classe: ["orange", __("Ajouté à la classe (tronc commun)")],
    };
    let analyse = null;

    const renderPreview = (data) => {
        const s = data.stats;
        const card = (valeur, libelle, couleur) =>
            `<div class="tg-prev-card ${couleur || ""}"><div class="v">${valeur}</div><div class="l">${libelle}</div></div>`;
        const erreurs = data.erreurs.length
            ? `<div class="alert alert-danger"><strong>${__("Erreurs bloquantes")} (${data.erreurs.length})</strong><ul>${
                data.erreurs.map((e) => `<li>${e.ligne ? __("Ligne {0}", [e.ligne]) + " : " : ""}${esc(e.message)}</li>`).join("")
              }</ul></div>`
            : `<div class="alert alert-success">${__("Aucune erreur : le fichier peut être importé.")}</div>`;
        const lignes = data.ues.map((ue) => {
            const tete = ue.code === "UNKNOW" ? "" : `
                <tr class="tg-prev-ue"><td>${esc(ue.code)}</td><td colspan="4">${esc(ue.intitule)}</td>
                <td>${ue.statut === "nouvelle" ? `<span class="indicator-pill green">${__("Nouvelle UE")}</span>` : ""}</td></tr>`;
            const cours = ue.cours.map((c) => {
                const [couleur, libelle] = STATUTS[c.statut] || ["gray", c.statut];
                const heures = (c.nombre_dheure_cm || 0) + (c.nombre_dheure_td || 0) + (c.nombre_dheure_tp || 0);
                const avert = (c.avertissements || []).map((a) => `<div class="text-warning small">⚠ ${esc(a)}</div>`).join("");
                return `<tr>
                    <td class="text-muted">${c.ligne}</td>
                    <td><strong>${esc(c.code)}</strong> ${esc(c.intitule_cours)}${avert}</td>
                    <td class="text-right">${fmt(c.credits)}</td>
                    <td class="text-right">${fmt(heures)} h</td>
                    <td>${(c.enseignants || []).length}</td>
                    <td><span class="indicator-pill ${couleur}">${libelle}</span></td>
                </tr>`;
            }).join("");
            return tete + cours;
        }).join("");
        const retraits = data.retraits.length ? `
            <h6 class="mt-3">${__("Cours absents du fichier (actuellement dans la grille de la classe)")}</h6>
            <ul class="small">${data.retraits.map((r) => r.bloque
                ? `<li>🔒 <strong>${esc(r.code)}</strong> ${esc(r.intitule)} : <span class="text-danger">${__("conservé")}</span> (${esc(r.dependances)})</li>`
                : `<li>🗑 <strong>${esc(r.code)}</strong> ${esc(r.intitule)} : ${__("sera retiré de la classe")}</li>`).join("")}</ul>` : "";
        return `
            <div class="tg-prev">
                <div class="tg-prev-cards">
                    ${card(s.ues_nouvelles + s.ues_existantes, __("UE"))}
                    ${card(s.cours_nouveaux, __("Cours nouveaux"), "green")}
                    ${card(s.cours_mis_a_jour + s.cours_ajoutes_a_la_classe, __("Cours mis à jour"), "blue")}
                    ${card(s.cours_retires, __("Retirés"), s.cours_retires ? "orange" : "")}
                    ${card(fmt(s.total_credits), __("Crédits"))}
                    ${card(s.avertissements, __("Avertissements"), s.avertissements ? "orange" : "")}
                </div>
                ${data.colonnes ? `<div class="small text-muted mb-2"><strong>${__("Colonnes reconnues")}</strong>
                    ${data.mode_colonnes === "position" ? `(${__("en-têtes non reconnus : ordre du modèle utilisé")})` : ""} :
                    ${Object.entries(data.colonnes).map(([role, entete]) => `${esc(role)} ← « ${esc(entete)} »`).join(" · ")}</div>` : ""}
                ${erreurs}
                <div class="tg-prev-table"><table class="table table-sm table-bordered">
                    <thead><tr><th>${__("Ligne")}</th><th>${__("Cours")}</th><th class="text-right">${__("Crédits")}</th>
                    <th class="text-right">CM+TD+TP</th><th>${__("Ens.")}</th><th>${__("Action")}</th></tr></thead>
                    <tbody>${lignes || `<tr><td colspan="6" class="text-muted">${__("Aucun cours")}</td></tr>`}</tbody>
                </table></div>
                ${retraits}
            </div>
            <style>
                .tg-prev-cards{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:12px}
                .tg-prev-card{border:1px solid var(--border-color);border-radius:8px;padding:8px;text-align:center}
                .tg-prev-card .v{font-size:18px;font-weight:700}.tg-prev-card .l{font-size:11px;color:var(--text-muted)}
                .tg-prev-card.green .v{color:var(--green-600)}.tg-prev-card.blue .v{color:var(--blue-600)}.tg-prev-card.orange .v{color:var(--orange-600)}
                .tg-prev-table{max-height:380px;overflow:auto}.tg-prev-ue td{background:#eef3f8;font-weight:600}
                @media (max-width:768px){.tg-prev-cards{grid-template-columns:repeat(3,1fr)}}
            </style>`;
    };

    const d = new frappe.ui.Dialog({
        title: __('Importer une grille'),
        size: 'extra-large',
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'template_info',
                options: `
                    <div class="alert alert-primary" style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
                        <div><i class="fa fa-download"></i> <strong>${__("Téléchargez d'abord le modèle")}</strong> ${__("pour respecter le format attendu.")}</div>
                        <button class="btn btn-sm btn-default download-template-btn"><i class="fa fa-file-excel-o"></i> ${__("Télécharger le modèle")}</button>
                    </div>`
            },
            {
                fieldtype: 'Attach',
                fieldname: 'file',
                label: __('Fichier Excel'),
                reqd: 1,
                description: __('Format .xlsx. Une prévisualisation est affichée avant tout import.'),
                change() {
                    analyse = null;
                    d.fields_dict.preview.$wrapper.empty();
                    d.set_primary_action(__('Prévisualiser'), previsualiser);
                }
            },
            { fieldtype: 'HTML', fieldname: 'preview' }
        ],
        primary_action_label: __('Prévisualiser'),
        primary_action: previsualiser,
    });

    function previsualiser(values) {
        const file_url = (values && values.file) || d.get_value('file');
        if (!file_url) {
            Udshed.Messages.validation(__('Joignez un fichier Excel.'));
            return;
        }
        Udshed.TeachingGrid.UtilsQueries.preview_import({ file_url, ...filters }, (data) => {
            if (!data) return;
            analyse = data;
            d.fields_dict.preview.$wrapper.html(renderPreview(data));
            if (data.erreurs.length) {
                d.set_primary_action(__('Corrigez le fichier puis rejoignez-le'), () => {
                    Udshed.Messages.warning(__("L'import est impossible tant que le fichier contient des erreurs."));
                });
                return;
            }
            d.set_primary_action(__('Confirmer l\'import'), () => importer(file_url));
        });
    }

    function importer(file_url) {
        if (!analyse || analyse.erreurs.length) return;
        Udshed.TeachingGrid.UtilsQueries.import_grid({ file_url, ...filters }, (data) => {
            if (!data || !data.status) return;
            d.hide();
            frappe.utils.play_sound("submit");
            const r = data.data;
            Udshed.Messages.dialog({
                title: __('Import réussi'),
                message: __("UE créées : {0}\nCours créés : {1}\nCours mis à jour : {2}\nCours retirés : {3}\nCours conservés (données existantes) : {4}",
                    [r.ues_created, r.courses_created, r.courses_updated, r.courses_deleted, r.courses_kept]),
                type: 'success'
            });
            onAfterImported(data);
        });
    }

    d.$wrapper.find('.download-template-btn').on('click', () => Udshed.TeachingGrid.UtilsQueries.download_template());
    d.show();
},
    

}
