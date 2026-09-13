$(document).ready(function() {
    // Affiche une alerte d'erreur dans la carte d'authentification
    function showAuthError(message) {
        $(".auth-card .alert-danger").remove();
        var alertHtml = '<div class="alert-danger alert-dismissible" role="alert">'
            + '<p class="alert-text">' + message + '</p>'
            + '<button type="button" class="close" data-dismiss="alert" aria-label="Close">'
            + '<span aria-hidden="true">&times;</span></button>'
            + '</div>';
        $("#auth-form").before(alertHtml);
    }

    // Intercepte le clic sur le bouton "Se connecter"
    $("#btn_soumettre").click(function() {
        // Récupération des valeurs saisies dans l'interface HTML
        var numero = $("#num_dossier").val().trim();
        var nom = $("#nom_candidat").val().trim();

        // Sécurité : Vérification si un champ est laissé vide
        if(!numero || !nom) {
            frappe.msgprint(__("Veuillez remplir tous les champs requis."));
            return;
        }

        // Changement visuel du bouton pour indiquer le chargement
        $(this).prop('disabled', true).html('<span class="btn-label">Vérification...</span>');
        $(".auth-card .alert-danger").remove();

        // Appel de la fonction Python dans le module udshed
        frappe.call({
            method: "udshed.api.inscription.authentifier_et_inscrire",
            args: {
                numero_dossier: numero,
                nom_candidat: nom
            },
            callback: function(r) {
                if (r.message && r.message.status === "authenticated") {
                    var formUrl = "/inscription-form?numero_dossier="
                        + encodeURIComponent(numero)
                        + "&nom_candidat=" + encodeURIComponent(nom);
                    window.location.href = formUrl;
                } else {
                    $("#btn_soumettre").prop('disabled', false)
                        .html('<span class="btn-label">Continuer</span>');
                    showAuthError(
                        (r.message && r.message.message)
                        || __("Numéro de dossier ou nom incorrect.")
                    );
                }
            }
        });
    });

    $("#religion-select").on("change", function() {
        var val = $(this).val();
        if (val === "AUTRE") {
            $(this).hide();
            $("#religion-autre").show().focus();
        } else {
            $("#religion-autre").val(val).hide();
        }
    });

    $("#form-inscription-academique").submit(function(event) {
        event.preventDefault();
        var candidate = window.inscriptionCandidate;
        var donnees = {};
        $(this).serializeArray().forEach(function(field) {
            donnees[field.name] = field.value;
        });
        $("#btn_enregistrer").prop("disabled", true).text(__("Enregistrement..."));

        frappe.call({
            method: "udshed.api.inscription.enregistrer_inscription",
            args: {
                numero_dossier: candidate.numero_dossier,
                nom_candidat: candidate.nom_prenom,
                donnees: JSON.stringify(donnees)
            },
            callback: function(r) {
                if (r.message && r.message.status === "success") {
                    $("#inscription-form-container").html(`
                        <div style="text-align: center; padding: 10px;">
                            <h3 style="color: #2885a7; margin-bottom: 15px;">✓ Inscription Académique Validée !</h3>
                            <p style="margin-bottom: 5px; font-size: 14px;">Votre matricule :</p>
                            
                            <div style="font-size: 22px; font-weight: bold; color: #007bff; background: #e9f5ff; padding: 8px 15px; border-radius: 4px; display: inline-block; margin-bottom: 20px; border: 1px dashed #007bff;">
                                ${r.message.matricule}
                            </div>
                            
                            <p style="color: #555; margin-bottom: 20px; font-size: 13px;">Votre document a été généré. Cliquez sur le bouton ci-dessous pour lancer le téléchargement.</p>
                            
                            <a href="${r.message.pdf_url}" class="btn btn-success" style="display: inline-block; padding: 12px 24px; background-color: #28a745; color: white; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 14px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                                📥 Télécharger ma fiche d'inscription
                            </a>
                        </div>
                    `);
                } else {
                    $("#btn_enregistrer").prop("disabled", false).text(__("Enregistrer mon inscription"));
                }
            }
        });
    });
});
