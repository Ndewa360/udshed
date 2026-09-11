# Diagramme de Séquence — Module d'Inscription

## Flux global : Candidature → Inscription

```mermaid
sequenceDiagram
    autonumber
    actor Candidat
    participant Web as Page Web<br/>(/depot-candidature)
    participant API_Cand as api/candidature.py<br/>creer_candidature()
    participant DB as MariaDB<br/>(Frappe ORM)
    participant Mail as Serveur SMTP
    actor Coordonnateur

    %% Phase 1 : Dépôt de candidature
    Candidat->>Web: Remplit le formulaire de candidature
    Web->>API_Cand: creer_candidature(données)
    API_Cand->>DB: INSERT Session Inscription Candidate<br/>(status = "En attente")
    DB-->>API_Cand: doc.name (ex: CAND-2026-00001)
    API_Cand->>Mail: Envoi email accusé de réception
    Mail-->>Candidat: Email confirmation + numéro dossier
    API_Cand->>Mail: Envoi notification coordonnateur
    Mail-->>Coordonnateur: Notification nouvelle candidature
    API_Cand-->>Web: {status: "success", numero_dossier}
    Web-->>Candidat: Affiche confirmation + numéro dossier
```

## Flux d'authentification et d'inscription

```mermaid
sequenceDiagram
    autonumber
    actor Candidat
    participant Web_Insc as Page Web<br/>(/inscription-form)
    participant API_Insc as api/inscription.py<br/>authentifier_et_inscrire()
    participant DB as MariaDB<br/>(Frappe ORM)

    %% Phase 2 : Authentification
    Candidat->>Web_Insc: Saisit numéro dossier + nom
    Web_Insc->>API_Insc: authentifier_et_inscrire(numero_dossier, nom)
    API_Insc->>DB: Vérifier session inscription ouverte
    DB-->>API_Insc: Session Inscription (status=Open)
    API_Insc->>DB: GET Session Inscription Candidate
    DB-->>API_Insc: dossier (nom, email, filière, niveau...)
    API_Insc->>API_Insc: _verifier_candidature_validee()<br/>(statut == "Accepté")
    API_Insc-->>Web_Insc: {status: "authenticated", données candidat}
    Web_Insc-->>Candidat: Affiche formulaire pré-rempli (étape 2)
```

## Flux d'enregistrement de l'inscription

```mermaid
sequenceDiagram
    autonumber
    actor Candidat
    participant Web_Insc as Page Web<br/>(/inscription-form)
    participant API_Insc as api/inscription.py<br/>enregistrer_inscription()
    participant DB as MariaDB<br/>(Frappe ORM)
    participant PDF as Générateur PDF<br/>(wkhtmltopdf)
    participant Mail as Serveur SMTP

    %% Phase 3 : Enregistrement inscription
    Candidat->>Web_Insc: Remplit infos complémentaires + soumet
    Web_Insc->>API_Insc: enregistrer_inscription(dossier, données)

    API_Insc->>DB: Vérifier session ouverte + dossier valide
    API_Insc->>DB: Vérifier si déjà inscrit pour ce dossier
    DB-->>API_Insc: None (pas encore inscrit)

    %% Génération matricule
    API_Insc->>DB: Requête max matricule pour préfixe
    DB-->>API_Insc: matricules existants
    API_Insc->>API_Insc: _generer_matricule()<br/>(ex: "26B" + "001" = "26B001")

    %% Création Inscription Academique
    API_Insc->>DB: INSERT Inscription Academique<br/>(matricule=26B001, dossier_origine, infos)
    DB-->>API_Insc: doc.name
    API_Insc->>DB: COMMIT

    %% Finalisation Student + Enrôlement
    API_Insc->>API_Insc: _finaliser_student_et_enrollement()
    API_Insc->>DB: Rechercher Student existant par email
    DB-->>API_Insc: None (pas encore de Student)

    API_Insc->>DB: INSERT Student<br/>(matricule=26B001, nom, prénom, cycle, filière...)
    DB-->>API_Insc: student.name (STU-####)

    API_Insc->>DB: GET Session Inscription Candidate
    API_Insc->>DB: _cree_compte_utilisateur(student, candidate)<br/>Création compte Frappe (role: Student)
    DB-->>API_Insc: User créé

    API_Insc->>DB: _auto_enroll_student(student, filière, niveau)<br/>Inscription Teaching Units
    DB-->>API_Insc: Enrôlement créé
    API_Insc->>DB: COMMIT

    %% Email matricule
    API_Insc->>DB: GET Inscription Academique (matricule)
    API_Insc->>PDF: Générer PDF fiche officielle
    PDF-->>API_Insc: PDF bytes
    API_Insc->>Mail: Envoi email matricule + PDF link
    Mail-->>Candidat: Email "Votre matricule: 26B001"

    API_Insc-->>Web_Insc: {status: "success", matricule: "26B001", pdf_url}
    Web_Insc-->>Candidat: Affiche matricule + lien PDF
```

## Flux de validation par le coordonnateur

```mermaid
sequenceDiagram
    autonumber
    actor Coordonnateur
    participant Desk as Page Desk<br/>(consultation_candidatures)
    participant Ctrl as session_inscription_candidate.py<br/>update_candidate_status()
    participant DB as MariaDB<br/>(Frappe ORM)
    participant Mail as Serveur SMTP

    Coordonnateur->>Desk: Consulte liste candidatures
    Desk->>Ctrl: get_candidates_list()
    Ctrl->>DB: SELECT Session Inscription Candidate
    DB-->>Ctrl: liste candidats
    Ctrl-->>Desk: données candidates

    Coordonnateur->>Desk: Accepte un candidat
    Desk->>Ctrl: update_candidate_status(doc_name, "Accepté")
    Ctrl->>DB: UPDATE candidature_status = "Accepté"
    Ctrl->>Mail: Envoi email confirmation acceptation
    Mail-->>Candidat: Email "Votre candidature est acceptée"
    Ctrl-->>Desk: {status: "success"}
```

## Résumé des états du candidat

```mermaid
stateDiagram-v2
    [*] --> En_attente: Dépôt candidature
    En_attente --> Accepte: Coordonnateur accepte
    En_attente --> Refuse: Coordonnateur refuse
    Accepte --> Inscrit: Inscription finalisée
    Refuse --> [*]
    Inscrit --> [*]
```
