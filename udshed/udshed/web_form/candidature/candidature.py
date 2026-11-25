import frappe

from udshed.utils.campagne import infos_publiques


def get_context(context):
	"""Formulaire générique de candidature : titre, établissement, campagne
	et centres viennent de la campagne d'admission courante (rien de figé)."""
	infos = infos_publiques()
	context.udshed_infos = infos
	campagne = infos["campagne"]
	etab = infos["etablissement"]
	if campagne:
		context.title = "{0} — {1}".format(campagne["titre"], etab.nom)
	context.max_file_size = 10  # Mo
