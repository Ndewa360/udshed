"""Authentification unique des étudiants (Frappe /login).

- active la connexion par nom d'utilisateur ;
- chaque étudiant a un compte Frappe dont le nom d'utilisateur est son
  matricule (créé s'il manque, complété sinon).
Les étudiants existants se connectent avec leur matricule ; ceux qui n'ont pas
encore de mot de passe utilisent « Mot de passe oublié » sur /login.
"""

import frappe

from udshed.utils.compte_etudiant import activer_connexion_par_matricule, assurer_compte


def execute():
	activer_connexion_par_matricule()
	for nom in frappe.get_all("Student", pluck="name"):
		try:
			assurer_compte(nom)
		except Exception:
			frappe.log_error(title=f"Compte étudiant non créé : {nom}")
