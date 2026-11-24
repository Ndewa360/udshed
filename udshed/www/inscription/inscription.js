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
                        + "&nom_candidat=" + encodeURIComponent(nom)
                        + "&date_naissance=" + encodeURIComponent(r.message.date_naissance || "")
                        + "&token=" + encodeURIComponent(r.message.token || "");
                    window.location.href = formUrl;
                } else {
                    // Erreur d'authentification : recharge automatique de la page
                    // pour permettre au candidat de remplir à nouveau ses infos.
                    showAuthError(__("Authentification échouée. Numéro de dossier ou nom incorrect."));
                    rechargerPage();
                }
            },
            error: function(r) {
                var message = (r && r._server_messages)
                    ? r._server_messages
                    : (r && r.message && r.message.message) || __("Une erreur est survenue. Veuillez réessayer.");
                showAuthError(String(message));
                rechargerPage();
            }
        });
    });

    function resetButton() {
        $("#btn_soumettre").prop("disabled", false).html('<span class="btn-label">Continuer</span>');
    }

    // Recharge automatiquement la page pour laisser le candidat ressaisir
    // ses informations sans avoir à actualiser manuellement.
    function rechargerPage() {
        resetButton();
        setTimeout(function() {
            window.location.reload();
        }, 2000);
    }
});
