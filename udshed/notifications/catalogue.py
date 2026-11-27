# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

"""Catalogue des notifications d'udshed (valeurs par défaut des règles).

Chaque entrée devient une « Regle Notification » à la migration ; l'administrateur
peut ensuite en changer les canaux, les délais et les textes sans développement.

- canaux : Application (cloche et file « À faire »), E-mail, SMS ;
- obligatoire : décision ou échéance, non désactivable par l'utilisateur ;
- resume : pour le personnel, l'e-mail est regroupé dans le résumé quotidien ;
- relance : (relancer tous les N jours, nombre maximal de relances, escalade après N jours) ;
  0 = pas de relance / pas d'escalade. Une relance s'arrête dès que l'action est faite.
"""

A, E, S = "Application", "E-mail", "SMS"

CATALOGUE = {
	# ------------------------------------------------------------ Admission
	"candidature_deposee": dict(libelle="Accusé de réception de la candidature", categorie="Admission",
								canaux=(E,), obligatoire=1, destinataires="Candidat"),
	"candidature_coordination": dict(libelle="Nouvelle candidature reçue", categorie="Admission", canaux=(A, E),
									 destinataires="Coordination de la filière"),
	"candidature_decision": dict(libelle="Décision sur la candidature", categorie="Admission", canaux=(E, S),
								 obligatoire=1, destinataires="Candidat"),
	"candidature_a_etudier": dict(libelle="Dossiers de candidature en attente d'étude", categorie="Admission",
								  canaux=(A, E), resume=1, relance=(3, 3, 10),
								  destinataires="Coordination de la filière ; escalade : doyen, vice-doyen"),
	"concours_convocation": dict(libelle="Convocation au concours", categorie="Admission", canaux=(E, S),
								 obligatoire=1, destinataires="Candidat"),
	"concours_resultat": dict(libelle="Résultat du concours (liste d'attente)", categorie="Admission", canaux=(E, S),
							  obligatoire=1, destinataires="Candidat"),
	"admission_finalisation": dict(libelle="Finalisation de l'inscription des admis", categorie="Admission",
								   canaux=(E, S), obligatoire=1, destinataires="Admis"),
	"compte_etudiant_cree": dict(libelle="Matricule et compte étudiant", categorie="Admission", canaux=(E,),
								 obligatoire=1, destinataires="Nouvel étudiant"),
	"inscription_sans_ue": dict(libelle="Inscription sans UE", categorie="Scolarité", canaux=(A, E), resume=1,
								relance=(2, 5, 0), destinataires="Scolarité"),
	# ------------------------------------------------------------ Scolarité
	"reinscription_ouverte": dict(libelle="Réinscription ouverte", categorie="Scolarité", canaux=(A, E, S),
								  obligatoire=1, destinataires="Étudiants à réinscrire"),
	"reinscription_rappel": dict(libelle="Rappel : réinscription bientôt close", categorie="Scolarité",
								 canaux=(A, E, S), obligatoire=1, destinataires="Étudiants non réinscrits"),
	"reinscription_non_reinscrits": dict(libelle="Réinscription close : étudiants non réinscrits",
										 categorie="Scolarité", canaux=(A, E), resume=1,
										 destinataires="Agents de scolarité de la filière"),
	"requete_soumise": dict(libelle="Requête étudiante à traiter", categorie="Scolarité", canaux=(A, E), resume=1,
							relance=(2, 3, 5), destinataires="Scolarité de la filière ; escalade : doyen, vice-doyen"),
	"requete_reponse": dict(libelle="Réponse à une requête", categorie="Scolarité", canaux=(A, E), obligatoire=1,
							destinataires="Étudiant"),
	"acte_demande": dict(libelle="Demande d'acte à traiter", categorie="Scolarité", canaux=(A, E), resume=1,
						 relance=(2, 3, 5), destinataires="Responsables des actes ; escalade : doyen, vice-doyen"),
	"acte_decision": dict(libelle="Acte disponible ou refusé", categorie="Scolarité", canaux=(A, E), obligatoire=1,
						  destinataires="Étudiant"),
	"acte_a_retirer": dict(libelle="Acte prêt à retirer", categorie="Scolarité", canaux=(A, E), relance=(14, 2, 0),
						   destinataires="Étudiant"),
	"correction_demandee": dict(libelle="Correction de note à approuver", categorie="Évaluations", canaux=(A, E),
								resume=1, relance=(2, 3, 5),
								destinataires="Coordination, scolarité ; escalade : doyen, vice-doyen"),
	"correction_decision": dict(libelle="Décision sur une demande de correction", categorie="Évaluations",
							   canaux=(A, E), obligatoire=1, destinataires="Enseignant demandeur"),
	"correction_impact": dict(libelle="Correction de note : décision de passage à revoir", categorie="Scolarité",
							  canaux=(A, E), obligatoire=1, destinataires="Scolarité"),
	"correction_appliquee": dict(libelle="Note corrigée", categorie="Évaluations", canaux=(A, E), obligatoire=1,
								 destinataires="Étudiant"),
	# ------------------------------------------------------------ Enseignement
	"affectation_cours": dict(libelle="Affectation à un cours", categorie="Enseignement", canaux=(A, E),
							  destinataires="Enseignant"),
	"seance_modifiee": dict(libelle="Séance modifiée ou annulée à moins de 72 h", categorie="Enseignement",
							canaux=(A, E, S), obligatoire=1, destinataires="Enseignant, étudiants de la classe"),
	"convention_disponible": dict(libelle="Convention ou document de vacation disponible", categorie="Enseignement",
								  canaux=(A, E), destinataires="Enseignant"),
	# ------------------------------------------------------------ Évaluations
	"saisie_ouverte": dict(libelle="Période de saisie des notes ouverte", categorie="Évaluations", canaux=(A, E),
						   destinataires="Enseignants concernés"),
	"saisie_rappel": dict(libelle="Rappel : fin de la période de saisie", categorie="Évaluations", canaux=(A, E),
						  obligatoire=1, destinataires="Enseignants n'ayant pas confirmé"),
	"saisie_retard": dict(libelle="Saisie des notes en retard", categorie="Évaluations", canaux=(A, E), resume=1,
						  relance=(2, 5, 5), destinataires="Enseignant, coordination ; escalade : doyen, vice-doyen"),
	"derogation_demandee": dict(libelle="Dérogation de saisie à décider", categorie="Évaluations", canaux=(A, E),
								relance=(2, 3, 5), destinataires="Doyen, vice-doyen ; escalade : DAA"),
	"derogation_decidee": dict(libelle="Décision sur une dérogation de saisie", categorie="Évaluations",
							   canaux=(A, E), obligatoire=1, destinataires="Enseignant"),
	"examen_rappel": dict(libelle="Rappel : épreuve d'examen demain", categorie="Évaluations", canaux=(A, E, S),
						  destinataires="Étudiants de la classe, enseignant"),
	"notes_publiees": dict(libelle="Notes publiées", categorie="Évaluations", canaux=(A, E),
						   destinataires="Étudiants"),
	"classe_notes_completes": dict(libelle="Toutes les notes d'une classe sont confirmées", categorie="Évaluations",
								   canaux=(A, E), destinataires="Coordination de la filière"),
	"session_a_publier": dict(libelle="Session d'examen prête à publier", categorie="Résultats", canaux=(A, E),
							  resume=1, relance=(2, 3, 7),
							  destinataires="Coordination, scolarité ; escalade : doyen, vice-doyen"),
	# ------------------------------------------------------------ Résultats et jurys
	"deliberation_a_tenir": dict(libelle="Classe prête à délibérer", categorie="Résultats", canaux=(A, E),
								 relance=(3, 3, 7), destinataires="Doyen, vice-doyen ; escalade : DAA"),
	"resultats_annuels": dict(libelle="Décision de fin d'année", categorie="Résultats", canaux=(A, E, S),
							  obligatoire=1, destinataires="Étudiants de la classe"),
	"rattrapage_convocation": dict(libelle="Convocation au rattrapage", categorie="Résultats", canaux=(A, E, S),
								   obligatoire=1, destinataires="Étudiants concernés"),
	"jury_diplomation_a_ouvrir": dict(libelle="Jury de diplomation à ouvrir", categorie="Résultats", canaux=(A, E),
									  relance=(7, 3, 0), destinataires="Responsable de la diplomation"),
	"diplome_proclame": dict(libelle="Diplôme proclamé", categorie="Résultats", canaux=(A, E), obligatoire=1,
							 destinataires="Diplômé"),
	# ------------------------------------------------------------ Pilotage
	"resume_faculte": dict(libelle="Résumé hebdomadaire de la faculté", categorie="Pilotage", canaux=(E,),
						   destinataires="Doyen, vice-doyen"),
	"resume_etablissement": dict(libelle="Résumé hebdomadaire de l'établissement", categorie="Pilotage",
								 canaux=(E,), destinataires="DAA"),
	"echecs_email": dict(libelle="Échecs d'envoi d'e-mails", categorie="Pilotage", canaux=(A,),
						 destinataires="Administrateurs"),
	"jalon_non_prepare": dict(libelle="Jalon du calendrier non préparé", categorie="Pilotage", canaux=(A, E),
							  destinataires="DAA ; doyen et vice-doyen pour un jalon de faculté"),
	# ------------------------------------------------------------ Finances
	"frais_echeance": dict(libelle="Échéance de frais de scolarité", categorie="Finances", canaux=(A, E, S),
						   obligatoire=1, destinataires="Étudiant"),
	"frais_impaye": dict(libelle="Frais de scolarité impayés", categorie="Finances", canaux=(A, E, S),
						 relance=(7, 3, 0), destinataires="Étudiant"),
	"paiement_recu": dict(libelle="Paiement enregistré", categorie="Finances", canaux=(A, E), obligatoire=1,
						  destinataires="Étudiant"),
	# ------------------------------------------------------------ Assiduité
	"absences_seuil": dict(libelle="Seuil d'absences atteint", categorie="Assiduité", canaux=(A, E),
						   obligatoire=1, destinataires="Étudiant, coordination"),
	# ------------------------------------------------------------ Stages et soutenances
	"stage_a_valider": dict(libelle="Stage ou mémoire à valider", categorie="Stages", canaux=(A, E), resume=1,
							relance=(3, 3, 7), destinataires="Coordination ; escalade : doyen, vice-doyen"),
	"stage_decision": dict(libelle="Décision sur un stage ou mémoire", categorie="Stages", canaux=(A, E),
						   obligatoire=1, destinataires="Étudiant, encadrant"),
	"soutenance_programmee": dict(libelle="Soutenance programmée", categorie="Stages", canaux=(A, E, S),
								  obligatoire=1, destinataires="Étudiant, membres du jury"),
}
