from udshed.utils.site_vitrine import contexte

sitemap = 1


def get_context(context):
	return contexte(
		context,
		"/udshed",
		"Udshed — Logiciel de gestion académique pour universités et grandes écoles",
		"Udshed centralise candidatures en ligne, inscriptions, grilles d'enseignement, emplois du temps "
		"sans conflit, saisie anonyme des notes et résultats académiques. Développé par Ndewa360. "
		"Demandez une démo gratuite.",
	)
