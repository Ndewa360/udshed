$(document).ready(function() {
    var params = new URLSearchParams(window.location.search);
    var numero = (params.get("numero_dossier") || "").trim();
    var nom = (params.get("nom_candidat") || "").trim();
    var candidate;
    var currentStep = 3;
    var totalSteps = 4;

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
                        '<p>Votre matricule officiel :</p>' +
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