"""Actes académiques : modèles par défaut (certificat de scolarité, attestation
d'inscription, carte d'étudiant, relevé de notes, attestation de réussite,
diplôme). Un modèle existant n'est jamais modifié."""

from udshed.utils.actes import creer_modeles_defaut


def execute():
	creer_modeles_defaut()
