# -*- coding: utf-8 -*-
"""Méthodes Jinja exposées aux templates (hook « jinja.methods »)."""
from udshed.api.school_setting import get_logo_data_uri  # noqa: F401
from udshed.utils.campagne import infos_publiques as infos_campagne  # noqa: F401
from udshed.utils.etablissement import etablissement  # noqa: F401  {{ etablissement().nom }}
