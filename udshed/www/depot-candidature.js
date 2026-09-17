$(document).ready(function () {
    chargerFilieres();

    $("#form-candidature").on("input", "input[data-phone-input]", function () {
        this.value = formaterNumero(this.value);
    });

    function formaterNumero(valeur) {
        var chiffres = (valeur || "").replace(/\D/g, "").slice(0, 9);
        if (!chiffres) return "";
        var morceaux = [chiffres.charAt(0)];
        for (var i = 1; i < chiffres.length; i += 2) {
            morceaux.push(chiffres.slice(i, i + 2));
        }
        return morceaux.join(" ");
    }

    function chargerFilieres() {
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Field of study",
                fields: ["name", "name_of_field"],
                limit_page_length: 100,
            },
            callback: function (r) {
                if (r.message && r.message.length) {
                    var select = $("#form-candidature select[name='filiere']");
                    select.empty();
                    select.append('<option value="">Sélectionner la filière</option>');
                    r.message.forEach(function (f) {
                        select.append(
                            '<option value="' + f.name + '">' + (f.name_of_field || f.name) + "</option>"
                        );
                    });
                } else {
                    $("#form-candidature select[name='filiere']").append(
                        '<option value="">Aucune filière disponible</option>'
                    );
                }
            },
        });
    }

    $("#form-candidature").submit(function (event) {
        event.preventDefault();
        afficherErreur("");
        $("#btn_soumettre").prop("disabled", true).text("Envoi en cours...");

        var formData = {};
        $(this)
            .serializeArray()
            .forEach(function (field) {
                formData[field.name] = field.value;
            });

        $("#form-candidature select.indicatif").each(function () {
            var indicatif = $(this).val();
            var cible = $(this).data("indicatif");
            var num = (formData[cible] || "").replace(/\D/g, "");
            if (num) {
                formData[cible] = indicatif + num;
            } else {
                formData[cible] = "";
            }
        });

        if (!formData.filiere) {
            $("#btn_soumettre").prop("disabled", false).text("Soumettre ma candidature");
            afficherErreur("Veuillez sélectionner une filière.");
            return;
        }

        var documents = {
            birth_certificate: $(this).find("input[name='birth_certificate']")[0].files[0],
            access_diploma_copy: $(this).find("input[name='access_diploma_copy']")[0].files[0],
            id_photo: $(this).find("input[name='id_photo']")[0].files[0],
            remittance_receipt: $(this).find("input[name='remittance_receipt']")[0].files[0],
        };

        var manquants = [];
        Object.keys(documents).forEach(function (cle) {
            if (!documents[cle]) {
                manquants.push(
                    cle === "birth_certificate" ? "Certificat de naissance"
                    : cle === "access_diploma_copy" ? "Copie du diplôme"
                    : cle === "id_photo" ? "Photo d'identité"
                    : "Quittance de paiement"
                );
            }
        });

        if (manquants.length) {
            $("#btn_soumettre").prop("disabled", false).text("Soumettre ma candidature");
            afficherErreur("Veuillez joindre les documents obligatoires : " + manquants.join(", ") + ".");
            return;
        }

        var fichierRestant = Object.keys(documents).filter(function (k) {
            return documents[k] !== undefined;
        });
        var uploads = {};

        function chargerSuivant() {
            if (!fichierRestant.length) {
                formData.birth_certificate = uploads.birth_certificate;
                formData.access_diploma_copy = uploads.access_diploma_copy;
                formData.id_photo = uploads.id_photo;
                formData.remittance_receipt = uploads.remittance_receipt;
                soumettreCandidature(formData);
                return;
            }
            var cle = fichierRestant.shift();
            var fichier = documents[cle];
            var fd = new FormData();
            fd.append("file", fichier);
            fd.append("is_private", "0");
            fd.append("doctype", "Session Inscription Candidate");
            fd.append("folder", "Home/Attachments");

            fetch("/api/method/upload_file", {
                method: "POST",
                headers: {
                    "X-Frappe-CSRF-Token": frappe.csrf_token || "",
                },
                body: fd,
            })
                .then(function (res) { return res.json(); })
                .then(function (r) {
                    if (r.message && r.message.file_url) {
                        uploads[cle] = r.message.file_url;
                        chargerSuivant();
                    } else {
                        throw new Error("Upload échoué pour " + cle);
                    }
                })
                .catch(function () {
                    $("#btn_soumettre").prop("disabled", false).text("Soumettre ma candidature");
                    afficherErreur("Erreur lors du téléchargement d'un document. Veuillez réessayer.");
                });
        }
        chargerSuivant();
    });

    function soumettreCandidature(formData) {
        frappe.call({
            method: "udshed.api.candidature.creer_candidature",
            args: { donnees: JSON.stringify(formData) },
            callback: function (r) {
                if (r.message && r.message.status === "success") {
                    $("#form-candidature").hide();
                    $("#form-error").hide();
                    $("#dossier-number").text(r.message.numero_dossier);
                    $("#form-success").show();
                    $("html, body").animate({ scrollTop: 0 }, 300);
                } else {
                    $("#btn_soumettre").prop("disabled", false).text("Soumettre ma candidature");
                    afficherErreur(r.message ? r.message.message : "Erreur lors de la soumission.");
                }
            },
            error: function () {
                $("#btn_soumettre").prop("disabled", false).text("Soumettre ma candidature");
                afficherErreur("Erreur de connexion au serveur.");
            },
        });
    }

    function afficherErreur(message) {
        if (!message) {
            $("#form-error").hide();
            return;
        }
        $("#form-error").html('<span class="alert-text">' + message + "</span>").show();
        $("html, body").animate({ scrollTop: 0 }, 300);
    }
});
