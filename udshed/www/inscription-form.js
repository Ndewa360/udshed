$(document).ready(function() {
    // Identité et jeton remis par « Mon dossier » via le stockage de session
    // (jamais dans l'URL : historique du navigateur, journaux du serveur).
    var session = {};
    try { session = JSON.parse(sessionStorage.getItem("udshed_inscription") || "{}") || {}; } catch (e) { session = {}; }
    var numero = (session.numero_dossier || "").trim();
    var nom = (session.nom_candidat || "").trim();
    var token = (session.token || "").trim();
    var candidate;
    var currentStep = 1;
    var totalSteps = 5;
    var grilleChargee = false;

    function show_error(message) {
        $("#form-error").text(message).show();
        $("#candidat-authentifie").text("");
    }

    if (!numero || !nom || !token) {
        show_error("Ouvrez d'abord votre dossier sur la page « Mon dossier » puis cliquez sur « Je confirme ma place ».");
        return;
    }

    frappe.call({
        method: "udshed.api.inscription.get_candidat_infos",
        args: {
            numero_dossier: numero,
            nom_candidat: nom,
            token: token
        },
        callback: function(r) {
            if (!r.message || r.message.status !== "authenticated") {
                show_error("Authentification échouée. Numéro de dossier ou nom incorrect.");
                return;
            }
            candidate = r.message;
            $("#candidat-authentifie").text("Candidat : " + candidate.nom_prenom);
            $("#filiere").val(candidate.filiere || "");
            $("#classe").val(candidate.classe || "");
            $("#annee_academique").val(candidate.annee_academique || "");
            if (candidate.finaliser_avant) {
                $("#date-limite").html("Finalisez votre inscription <strong>avant le " + escapeHtml(candidate.finaliser_avant)
                    + "</strong>. Passé cette date, votre place sera attribuée à un autre candidat.").show();
            }
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

    /* ---- Renoncement à la place ---- */
    $("#lien-renoncer").on("click", function(e) {
        e.preventDefault();
        var motif = window.prompt(
            "Vous allez renoncer définitivement à votre place : elle sera proposée à un autre candidat.\n\n"
            + "Motif (facultatif) :", "");
        if (motif === null) {
            return;
        }
        if (!window.confirm("Confirmez-vous renoncer à votre admission ? Cette action est définitive.")) {
            return;
        }
        frappe.call({
            method: "udshed.api.concours_finalisation.renoncer_admission",
            args: { numero_dossier: numero, nom_candidat: nom, token: token, motif: motif },
            callback: function(r) {
                if (r.message && r.message.status === "ok") {
                    $("#date-limite").hide();
                    $("#bloc-renoncer").hide();
                    $("#stepper-wrapper").html(
                        '<div class="alert alert-secondary text-center">Votre renoncement est enregistré : '
                        + 'votre place a été libérée. Nous vous souhaitons une bonne continuation.</div>');
                }
            }
        });
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

        /* grille : chargement à la première arrivée sur l'étape 5 */
        if (currentStep === totalSteps && !grilleChargee) {
            chargerGrille();
        }
    }

    function chargerGrille() {
        grilleChargee = true;
        $("#grille-loading").show();
        $("#grille-error").hide();
        $("#grille-content").hide();
        $("#btn_enregistrer").prop("disabled", true);

        frappe.call({
            method: "udshed.api.inscription.get_grille_enseignement",
            args: {
                numero_dossier: numero,
                nom_candidat: nom,
                token: token
            },
            callback: function(r) {
                $("#grille-loading").hide();
                if (!r.message || r.message.status !== "ok") {
                    afficherErreurGrille("Impossible de charger la grille d'enseignement.");
                    return;
                }
                var msg = r.message;
                $("#grille-filiere").text(msg.filiere_label || msg.filiere);
                $("#grille-niveau").text(msg.niveau || "—");
                $("#grille-annee").text(msg.academic_year || "—");

                var s1 = [];
                var s2 = [];
                (msg.cours || []).forEach(function(c) {
                    var sem = String(c.semestre || "").toLowerCase();
                    var dans = [];
                    if (/les deux|1.*2|2.*1/.test(sem)) {
                        dans = [1, 2];
                    } else if (/semestre *2|second|deuxi|s2/.test(sem)) {
                        dans = [2];
                    } else if (/semestre *1|premier|s1/.test(sem)) {
                        dans = [1];
                    } else {
                        dans = [1];
                    }
                    if (dans.indexOf(1) >= 0) s1.push(c);
                    if (dans.indexOf(2) >= 0) s2.push(c);
                });

                $("#grille-total").text(msg.total_credits || 0);
                remplirGrille("grille-s1-body", "grille-s1-total", s1);
                remplirGrille("grille-s2-body", "grille-s2-total", s2);

                if (!msg.cours || msg.cours.length === 0) {
                    afficherErreurGrille("Aucune unité d'enseignement trouvée pour cette filière et ce niveau. Veuillez contacter la scolarité.");
                    return;
                }
                $("#grille-content").show();
                $("#grille-confirm-check").prop("checked", false);
                $("#btn_enregistrer").prop("disabled", !$("#grille-confirm-check").prop("checked"));
            },
            error: function() {
                $("#grille-loading").hide();
                afficherErreurGrille("Une erreur est survenue lors du chargement de la grille d'enseignement.");
            }
        });
    }

    function remplirGrille(bodyId, totalId, cours) {
        var $tbody = $("#" + bodyId).empty();
        var total = 0;
        var index = 0;
        cours.forEach(function(c) {
            index++;
            total += Number(c.credits) || 0;
            $tbody.append(
                "<tr>" +
                "<td>" + index + "</td>" +
                "<td>" + escapeHtml(c.intitule || c.teaching_unit || "—") + "</td>" +
                "<td class='text-right'>" + (c.credits || 0) + "</td>" +
                "</tr>"
            );
        });
        if (index === 0) {
            $tbody.append("<tr><td colspan='3' class='text-muted' style='font-style: italic;'>Aucune unité d'enseignement pour ce semestre.</td></tr>");
        }
        $("#" + totalId).text(total);
    }

    function afficherErreurGrille(message) {
        $("#grille-error").text(message).show();
        $("#btn_enregistrer").prop("disabled", true);
    }

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
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

    $("#grille-confirm-check").on("change", function() {
        $("#btn_enregistrer").prop("disabled", !$(this).prop("checked"));
    });

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
        if (currentStep === totalSteps && !$("#grille-confirm-check").prop("checked")) {
            frappe.msgprint({
                title: "Confirmation requise",
                message: "Veuillez cocher la case de confirmation de la grille d'enseignement avant de terminer.",
                indicator: "orange"
            });
            return;
        }
        var donnees = {};
        $(this).serializeArray().forEach(function(field) {
            donnees[field.name] = field.value;
        });

        $("#btn_enregistrer").prop("disabled", true).text("Enregistrement...");
        frappe.call({
            method: "udshed.api.inscription.enregistrer_inscription",
            args: {
                // Mêmes valeurs que celles signées dans le jeton (URL).
                numero_dossier: numero,
                nom_candidat: nom,
                donnees: JSON.stringify(donnees),
                token: token
            },
            callback: function(r) {
                if (r.message && r.message.status === "success") {
                    try { sessionStorage.removeItem("udshed_inscription"); } catch (e) { /* rien */ }
                    var annee = r.message.annee_academique ? " pour l'année " + escapeHtml(r.message.annee_academique) : "";
                    $("#stepper-wrapper").html(
                        '<div class="text-center py-4">' +
                        '<h3 style="color: #28a745;">Inscription académique validée' + annee + '</h3>' +
                        '<p>Votre matricule officiel :</p>' +
                        '<p class="font-weight-bold h4" style="color: #003B6F;">' + escapeHtml(r.message.matricule) + '</p>' +
                        '<a href="' + escapeHtml(r.message.pdf_url) + '" class="btn btn-success mt-3">Télécharger ma fiche d\u0027inscription</a>' +
                        '<div class="alert alert-info mt-4 text-left" style="max-width: 560px; margin: 24px auto 0;">' +
                        '<b>Votre compte étudiant</b><br>Un e-mail vient de vous être envoyé avec votre matricule et un lien ' +
                        'pour <b>choisir votre mot de passe</b>. Vous vous connecterez ensuite sur ' +
                        '<a href="/login">la page de connexion</a> avec votre <b>matricule</b> (ou votre e-mail) ' +
                        'pour consulter votre grille, votre planning et vos notes.</div>' +
                        '</div>'
                    );
                } else {
                    $("#btn_enregistrer").prop("disabled", false).text("Confirmer ma grille et terminer");
                    var message = (r && r._server_messages) ? r._server_messages : (r.message && r.message._server_messages) ? r.message._server_messages : "L'enregistrement a échoué. Veuillez réessayer.";
                    $("#grille-error").text(String(message)).show();
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