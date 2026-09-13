$(document).ready(function() {
    var params = new URLSearchParams(window.location.search);
    var numero = (params.get("numero_dossier") || "").trim();
    var nom = (params.get("nom_candidat") || "").trim();
    var candidate;
    var currentStep = 1;
    var totalSteps = 5;
    var grilleChargee = false;

    function show_error(message) {
        $("#form-error").text(message).show();
        $("#candidat-authentifie").text("");
    }

    if (!numero || !nom) {
        show_error("Les informations du candidat sont manquantes.");
        return;
    }

    frappe.call({
        method: "udshed.api.inscription.authentifier_et_inscrire",
        args: { numero_dossier: numero, nom_candidat: nom },
        callback: function(r) {
            if (!r.message || r.message.status !== "authenticated") {
                show_error("Authentification échouée. Numéro de dossier ou nom incorrect.");
                return;
            }
            candidate = r.message;
            $("#candidat-authentifie").text("Candidat : " + candidate.nom_prenom);
            $("#filiere").val(candidate.filiere || "");
            $("#classe").val(candidate.classe || "");
            $("#stepper-wrapper").show();
        },
        error: function(r) {
            var message = (r && r.message) || "Une erreur est survenue. Veuillez réessayer.";
            if (r && r._server_messages) {
                message = r._server_messages;
            }
            show_error(String(message));
            $("#btn_enregistrer").prop("disabled", false);
        }
    });

    /* ---- Religion : champ texte pour "AUTRE" ---- */
    $("#religion-select").on("change", function() {
        var val = $(this).val();
        if (val === "AUTRE") {
            $(this).hide();
            $("#religion-autre").show().focus();
        } else {
            $("#religion-autre").val(val).hide();
        }
    });

    /* ---- Stepper navigation ---- */
    function updateStepper() {
        /* sections */
        $(".stepper-section").hide();
        $('.stepper-section[data-section="' + currentStep + '"]').show();

        /* circles & labels */
        for (var i = 1; i <= totalSteps; i++) {
            var $step = $('.stepper-step[data-step="' + i + '"]');
            var $circle = $step.find(".stepper-circle");
            $circle.removeClass("active done");
            $step.removeClass("active done");
            if (i < currentStep) {
                $circle.addClass("done").text("✓");
                $step.addClass("done");
            } else if (i === currentStep) {
                $circle.addClass("active").text(i);
                $step.addClass("active");
            } else {
                $circle.text(i);
            }
        }

        /* lines */
        $(".stepper-line").each(function(idx) {
            if (idx + 1 < currentStep) {
                $(this).addClass("done");
            } else {
                $(this).removeClass("done");
            }
        });

        /* buttons */
        $("#btn_prev").toggle(currentStep > 1);
        $("#btn_next").toggle(currentStep < totalSteps);
        $("#btn_enregistrer").toggle(currentStep === totalSteps);

        /* grille d'enseignement à l'étape finale */
        if (currentStep === totalSteps) {
            chargerGrille();
        }
    }

    function chargerGrille() {
        if (grilleChargee) return;
        grilleChargee = true;
        $("#grille-loader").show();
        frappe.call({
            method: "udshed.api.inscription.get_grille_enseignement",
            args: {
                numero_dossier: candidate.numero_dossier,
                nom_candidat: candidate.nom_prenom
            },
            callback: function(r) {
                $("#grille-loader").hide();
                if (r.message && r.message.status === "success") {
                    afficherGrille(r.message);
                } else {
                    $("#grille-enseignement").html(
                        '<div class="alert alert-warning">Impossible de charger la grille d\u0027enseignement.</div>'
                    );
                }
            },
            error: function() {
                grilleChargee = false;
                $("#grille-loader").hide();
                $("#grille-enseignement").html(
                    '<div class="alert alert-warning">Impossible de charger la grille d\u0027enseignement.</div>'
                );
            }
        });
    }

    function esc(valeur) {
        return String(valeur == null ? "" : valeur)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function afficherGrille(data) {
        $("#grille-intitule").text(
            "Filière : " + (data.filiere_label || data.filiere || "—") +
            " | Niveau : " + (data.niveau || "—") +
            " | Année académique : " + (data.academic_year || "—")
        );

        var html = "";
        (data.semestres || []).forEach(function(sem) {
            if (!sem.grid || !sem.grid.length) return;
            html += '<h6 class="mt-4 mb-2 text-primary">' + esc(sem.semestre) + "</h6>";
            html += '<div class="table-responsive mb-2">';
            html += '<table class="table table-bordered table-sm small">';
            html += '<thead><tr>' +
                '<th>Code</th><th>Intitulé</th><th>Crédits</th>' +
                '<th>CM</th><th>TD</th><th>TP</th><th>TPE</th><th>Total heures</th>' +
                "</tr></thead><tbody>";
            sem.grid.forEach(function(ue) {
                html += '<tr class="table-active">' +
                    "<td><strong>" + esc(ue.ue_code) + "</strong></td>" +
                    "<td><strong>" + esc(ue.ue_title) + "</strong></td>" +
                    "<td><strong>" + esc(ue.ue_credits) + "</strong></td>" +
                    "<td colspan=\"5\"></td></tr>";
                (ue.courses || []).forEach(function(c) {
                    html += "<tr>" +
                        "<td>" + esc(c.code) + "</td>" +
                        "<td>" + esc(c.title) + "</td>" +
                        "<td>" + esc(c.credits) + "</td>" +
                        "<td>" + esc(c.nombre_dheure_cm) + "</td>" +
                        "<td>" + esc(c.nombre_dheure_td) + "</td>" +
                        "<td>" + esc(c.nombre_dheure_tp) + "</td>" +
                        "<td>" + esc(c.nombre_dheure_tpe) + "</td>" +
                        "<td>" + esc(c.total_hours) + "</td></tr>";
                });
            });
            html += "</tbody></table></div>";
            html += '<p class="text-muted small">UE : <strong>' + esc(sem.stats.ue_count) + "</strong>" +
                " — Cours : <strong>" + esc(sem.stats.course_count) + "</strong>" +
                " — Crédits : <strong>" + esc(sem.stats.total_credits) + "</strong>" +
                " — Heures : <strong>" + esc(sem.stats.total_hours) + "</strong></p>";
        });

        if (!html) {
            html = '<div class="alert alert-info">Aucune grille d\u0027enseignement disponible pour votre filière pour le moment.</div>';
        }
        $("#grille-enseignement").html(html);
    }

    function validateStep(step) {
        var $section = $('.stepper-section[data-section="' + step + '"]');
        var firstInvalid = null;
        $section.find("[required]").each(function() {
            if (!$(this).val()) {
                $(this).addClass("is-invalid");
                if (!firstInvalid) firstInvalid = $(this);
            } else {
                $(this).removeClass("is-invalid");
            }
        });
        if (firstInvalid) {
            firstInvalid.focus();
            frappe.msgprint({
                title: "Champs obligatoires manquants",
                message: "Veuillez remplir tous les champs marqués d'un astérisque (*) avant de continuer.",
                indicator: "red"
            });
            return false;
        }
        return true;
    }

    $("#btn_next").on("click", function() {
        if (validateStep(currentStep)) {
            currentStep++;
            updateStepper();
            window.scrollTo({ top: 0, behavior: "smooth" });
        }
    });

    $("#btn_prev").on("click", function() {
        currentStep--;
        updateStepper();
        window.scrollTo({ top: 0, behavior: "smooth" });
    });

    /* ---- Soumission ---- */
    $("#form-inscription-academique").on("submit", function(event) {
        event.preventDefault();
        if (!validateStep(currentStep)) return;
        var donnees = {};
        $(this).serializeArray().forEach(function(field) {
            donnees[field.name] = field.value;
        });

        $("#btn_enregistrer").prop("disabled", true).text("Enregistrement...");
        frappe.call({
            method: "udshed.api.inscription.enregistrer_inscription",
            args: {
                numero_dossier: candidate.numero_dossier,
                nom_candidat: candidate.nom_prenom,
                donnees: JSON.stringify(donnees)
            },
            callback: function(r) {
                if (r.message && r.message.status === "success") {
                    $("#stepper-wrapper").html(
                        '<div class="text-center py-4">' +
                        '<h3 style="color: #28a745;">Inscription académique validée</h3>' +
                        '<p>Votre matricule :</p>' +
                        '<p class="font-weight-bold h4" style="color: #003B6F;">' + r.message.matricule + '</p>' +
                        '<a href="' + r.message.pdf_url + '" class="btn btn-success mt-3">Télécharger ma fiche d\u0027inscription</a>' +
                        '</div>'
                    );
                } else {
                    $("#btn_enregistrer").prop("disabled", false).text("Terminer mon inscription");
                }
            }
        });
    });

    updateStepper();
});

/* ---- Études antérieures : ajouter une ligne ---- */
window.addEtudeManuel = function() {
    var ligne = `<tr>
        <td><input type="text" class="form-control form-control-sm" placeholder="Diplôme"></td>
        <td><input type="text" class="form-control form-control-sm" placeholder="Établissement"></td>
        <td><input type="number" class="form-control form-control-sm" placeholder="Année"></td>
        <td><input type="text" class="form-control form-control-sm" placeholder="Pays"></td>
        <td><button class="btn btn-sm btn-danger" onclick="$(this).parent().parent().remove()">Supprimer</button></td>
    </tr>`;
    $("#etudes-antérieures-table").append(ligne);
};