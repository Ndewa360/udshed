// Page publique « Mon admission » : le candidat voit son résultat et,
// s'il est admis, confirme sa place (finalisation) ou y renonce.
$(document).ready(function () {
    var numero = "", nom = "", infos = null;

    function esc(s) {
        return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
        });
    }

    function erreur(message) {
        $(".auth-card .alert-danger").remove();
        $("#adm-form").before('<div class="alert-danger" role="alert"><p class="alert-text">' + esc(message) + "</p></div>");
    }

    function message_serveur(r) {
        try {
            var m = JSON.parse(r._server_messages);
            return JSON.parse(m[0]).message.replace(/<[^>]+>/g, "");
        } catch (e) {
            return "Une erreur est survenue. Veuillez réessayer.";
        }
    }

    $("#adm-form").on("submit", function (e) {
        e.preventDefault();
        numero = $("#adm_dossier").val().trim().toUpperCase();
        nom = $("#adm_nom").val().trim();
        if (!numero || !nom) { erreur("Veuillez remplir les deux champs."); return; }
        $("#adm_valider").prop("disabled", true);
        $(".auth-card .alert-danger").remove();
        frappe.call({
            method: "udshed.api.concours_finalisation.consulter_admission",
            args: { numero_dossier: numero, nom_candidat: nom },
            callback: function (r) {
                $("#adm_valider").prop("disabled", false);
                if (r.message) { infos = r.message; afficher(); }
            },
            error: function (r) {
                $("#adm_valider").prop("disabled", false);
                erreur(message_serveur(r));
            },
        });
    });

    function bloc(icone, classe, titre, corps) {
        return '<div class="adm-icone ' + classe + '">' + icone + '</div>'
            + '<h2 class="adm-titre">' + esc(titre) + "</h2>" + corps
            + '<p style="margin-top:18px"><a href="#" class="adm-autre" style="font-size:13px">Consulter un autre dossier</a></p>';
    }

    function afficher() {
        var i = infos, html = "";
        var formation = i.formation ? '<p class="adm-formation">' + esc(i.formation) + "</p>" : "";
        var contexte = i.concours ? "<p class=\"text-muted\" style=\"font-size:13px\">" + esc(i.concours) + "</p>" : "";

        if (i.etat === "admis" && !i.delai_depasse) {
            var reste = i.jours_restants;
            var compte = reste == null ? "" : (reste === 0 ? "Dernier jour aujourd'hui" : '<span class="adm-compte">' + reste + "</span> jour(s) restant(s)");
            html = bloc("✓", "ok", "Félicitations, vous êtes admis(e) !", contexte + formation
                + '<div class="adm-boite' + (reste != null && reste <= 3 ? " alerte" : "") + '">'
                + (i.date_limite ? "Confirmez votre place en finalisant votre inscription <b>avant le " + esc(i.date_limite) + "</b>.<br>" + compte + "<br>" : "")
                + "Passé ce délai, votre place sera attribuée au candidat suivant.</div>"
                + '<button class="btn btn-primary btn-block adm-confirmer"><span class="btn-label">Je confirme ma place et je m\'inscris</span></button>'
                + '<a href="#" class="adm-renoncer">Je ne viendrai pas : je renonce à ma place</a>');
        } else if (i.etat === "admis") {
            html = bloc("!", "att", "Délai de confirmation dépassé", formation
                + '<div class="adm-boite alerte">Le délai pour confirmer votre place a expiré le <b>' + esc(i.date_limite)
                + "</b>. Contactez la scolarité au plus vite en indiquant votre numéro de dossier <b>" + esc(i.numero_dossier) + "</b>.</div>");
        } else if (i.etat === "inscrit") {
            html = bloc("✓", "ok", "Votre inscription est confirmée", formation
                + (i.matricule ? '<p style="margin:0">Votre matricule :</p><div class="adm-mat">' + esc(i.matricule) + "</div>" : "")
                + (i.pdf_url ? '<a class="btn btn-primary btn-block" href="' + esc(i.pdf_url) + '"><span class="btn-label">Télécharger ma fiche d\'inscription</span></a>' : ""));
        } else if (i.etat === "attente") {
            var rangs = (i.rangs || []).map(function (r) { return "<li>" + esc(r.formation) + " : rang <b>" + esc(r.rang) + "</b></li>"; }).join("");
            html = bloc("⏳", "att", "Vous êtes sur liste d'attente", contexte
                + '<div class="adm-boite">Si une place se libère, elle vous sera proposée par e-mail dans l\'ordre du classement.'
                + (rangs ? '<ul class="adm-rangs">' + rangs + "</ul>" : "") + "</div>");
        } else if (i.etat === "refuse") {
            html = bloc("✕", "non", "Candidature non retenue", contexte
                + (i.motif ? '<div class="adm-boite">' + esc(i.motif) + "</div>" : ""));
        } else if (i.etat === "desiste") {
            html = bloc("–", "neutre", "Vous avez renoncé à votre place", '<div class="adm-boite">' + esc(i.motif || "") + "</div>");
        } else {
            html = bloc("…", "neutre", "Candidature en cours de traitement", contexte
                + '<div class="adm-boite">Statut actuel : <b>' + esc(i.statut) + "</b>. Vous serez informé(e) par e-mail.</div>");
        }

        $("#adm-form, .adm-intro").hide();
        $("#adm-resultat").html(html).show();
    }

    $("#adm-resultat").on("click", ".adm-autre", function (e) {
        e.preventDefault();
        infos = null;
        $("#adm-resultat").hide().empty();
        $("#adm-form, .adm-intro").show();
    });

    $("#adm-resultat").on("click", ".adm-confirmer", function () {
        window.location.href = "/inscription-form?numero_dossier=" + encodeURIComponent(numero)
            + "&nom_candidat=" + encodeURIComponent(nom) + "&token=" + encodeURIComponent(infos.token || "");
    });

    $("#adm-resultat").on("click", ".adm-renoncer", function (e) {
        e.preventDefault();
        var motif = window.prompt("Vous allez renoncer définitivement à votre place : elle sera proposée à un autre candidat.\n\nMotif (facultatif) :", "");
        if (motif === null) return;
        if (!window.confirm("Confirmez-vous renoncer à votre admission ? Cette action est définitive.")) return;
        frappe.call({
            method: "udshed.api.concours_finalisation.renoncer_admission",
            args: { numero_dossier: numero, nom_candidat: nom, token: infos.token, motif: motif },
            callback: function (r) {
                if (r.message && r.message.status === "ok") {
                    infos = { etat: "desiste", motif: "Votre renoncement est enregistré. Nous vous souhaitons une bonne continuation." };
                    afficher();
                }
            },
            error: function (r) { erreur(message_serveur(r)); },
        });
    });
});
