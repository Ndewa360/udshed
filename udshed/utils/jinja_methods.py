# -*- coding: utf-8 -*-
"""Méthodes Jinja exposées aux templates (hook « jinja.methods »).

Depuis Frappe 16.6x, seules les fonctions *définies* dans ce module sont exposées
(une fonction simplement importée est ignorée) : chaque méthode est donc une
fonction locale qui délègue.
"""


def get_logo_data_uri():
	from udshed.api.school_setting import get_logo_data_uri as logo

	return logo()


def infos_campagne():
	from udshed.utils.campagne import infos_publiques

	return infos_publiques()


def etablissement():
	"""{{ etablissement().nom }}"""
	from udshed.utils.etablissement import etablissement as etab

	return etab()
