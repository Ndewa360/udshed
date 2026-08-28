$(document).ready(function() {
    var params = new URLSearchParams(window.location.search);
    var numero = (params.get("numero_dossier") || "").trim();
    var nom = (params.get("nom_candidat") || "").trim();
    var candidate;

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
            $("#form-inscription-academique").show();
        }
    });

    $("#form-inscription-academique").submit(function(event) {
        event.preventDefault();
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
                    $("#form-inscription-academique").html(
                        '<div class="text-center py-4">' +
                        '<h3>Inscription académique validée</h3>' +
                        '<p>Votre matricule officiel :</p>' +
                        '<p class="font-weight-bold h4">' + r.message.matricule + '</p>' +
                        '<a href="' + r.message.pdf_url + '" class="btn btn-success">Télécharger ma fiche PDF</a>' +
                        '</div>'
                    );
                } else {
                    $("#btn_enregistrer").prop("disabled", false).text(__("Terminer mon inscription"));
                }
            }
        });
    });
});
