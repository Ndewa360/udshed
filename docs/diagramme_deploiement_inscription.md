# Diagramme de Déploiement — Module d'Inscription

## Architecture UDSHED (Frappe Bench)

```mermaid
deploymentDiagram
    device "Navigateur" as NAV
    node "Serveur Bench" as BENCH {
        node "Nginx" as NGX
        node "Gunicorn (Frappe WSGI)" as GUN {
            node "App udshed" as APP {
                artifact "Pages www<br/>(/inscription, /depot-candidature,<br/>/inscription-form)" as WWW
                component "API Inscription<br/>(api/inscription.py)" as API_INSC
                component "API Candidature<br/>(api/candidature.py)" as API_CAND
                component "API Reinscription<br/>(api/reregistration.py)" as API_REREG
                component "Contrôleur Candidat<br/>(session_inscription_candidate.py)" as CTRL_CAND
                component "Doctypes<br/>(Session Inscription, Session Inscription<br/>Candidate, Inscription Academique,<br/>Student, Academic Reregistration)" as DT
            }
        }
        node "Workers RQ" as RQW
        component "Emails<br/>(frappe.sendmail)" as EM
        component "PDF / Print Formats<br/>(wkhtmltopdf)" as PDF
        artifact "site.local<br/>(sites/)" as SITE
    }

    database "MariaDB<br/>(Base du site)" as MDB
    node "Redis" as REDIS
    device "Serveur SMTP" as SMTP
    fileSystem "private/files" as FS

    link NAV NGX : HTTP/HTTPS
    link NGX GUN : Reverse proxy
    link GUN WWW : Frappe routing
    link WWW API_INSC : "/inscription-form"
    link WWW API_CAND : "/depot-candidature"
    link WWW API_REREG : "/reinscription-etudiant"
    link WWW CTRL_CAND : "/inscription-connexion"
    link API_INSC DT : Frappe ORM
    link API_CAND DT : Frappe ORM
    link API_REREG DT : Frappe ORM
    link CTRL_CAND DT : Frappe ORM
    link DT MDB : SQL
    link API_INSC EM : Envoi email matricule
    link API_CAND EM : Accusé réception<br/>+ notification coordonnateur
    link CTRL_CAND EM : Emails de validation
    link API_INSC PDF : Fiche Officielle UDM
    link API_CAND PDF : Fiche candidature
    link API_REREG PDF : Fiche réinscription
    link PDF FS : Lecture photos/fichiers
    link EM SMTP : SMTP
    link MDB REDIS : Cache
    link APP RQW : Job queue