app_name = "udshed"
app_title = "Udshed"
app_publisher = "Ndewa360"
app_description = "Gestion académique : candidatures, inscriptions et réinscriptions, planning, notes et résultats"
app_email = "contact@ndewa-360.com"
app_license = "mit"

# App logo for login page and navbar
app_logo_url = ["/assets/udshed/images/logo1.png"]

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "udshed",
		"logo": "/assets/udshed/images/logo1.png",
		"title": "Udshed",
		# Route du desk : Frappe ouvre la première barre latérale du dock que l'utilisateur peut voir.
		"route": "/desk",
		"has_permission": "udshed.api.permission.has_app_permission",
		"role_home_page": {
			"All": "desk"
		}

	}
]

# Personnel : page « Accueil » (tuiles des espaces que ses droits lui ouvrent).
role_home_page = {
	"System Manager": "/desk/accueil-udshed",
	"Workspace Manager": "/desk",
	"Script Manager": "/desk",
	"Coordonateur": "/desk/accueil-udshed",
	"Planning Manager": "/desk/accueil-udshed",
	"Registration Manager": "/desk/accueil-udshed",
	"Agent de scolarité": "/desk/accueil-udshed",
	"Comptable": "/desk/accueil-udshed",
	"Correcteur": "/desk/accueil-udshed",
	"Responsable Diplomation": "/desk/accueil-udshed",
	"Responsable des partenariats": "/desk/accueil-udshed",
	"Doyen": "/desk/accueil-udshed",
	"Vice-Doyen": "/desk/accueil-udshed",
	"Directeur des Affaires Académiques": "/desk/accueil-udshed",
	"Teacher": "/desk/accueil-udshed",
	# Étudiant : directement son espace ; ses droits ne lui ouvrent que la barre « Mon espace étudiant ».
	"Student": "/app/mon-espace-etudiant",
}


#Fixutres
#------------
fixtures = [
    {
        "dt" : "Role",
        "filters": [
            ["name","in",["System Manager","Workspace Manager","Script Manager","Teacher","Student","Guest","Desk User","Coordonateur","Planning Manager","Registration Manager","Agent de scolarité","Comptable","Correcteur","Responsable Diplomation","Responsable des partenariats","Doyen","Vice-Doyen","Directeur des Affaires Académiques"]]
        ]
    },
    {
        "dt": "Web Page",
        "filters": [
            # Seule la page d'accueil est livrée (rendue dynamiquement) ; les
            # anciennes pages du dépôt en plusieurs étapes sont dépubliées
            # (patch campagne_admission).
            ["route", "in", ["index"]]
        ]
    },
    {
        "dt": "Page",
        "filters": [
            ["name", "in", ["gestion-des-niveaux"]]
        ]
    },
]


# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# Bundles Frappe (*.bundle.*) : `bench build` leur donne un nom versionné.
# Un chemin brut (/assets/udshed/js/udshed.js) était inclus SANS version et
# restait en cache en production : les navigateurs gardaient un ancien
# udshed.js sans Udshed.Loading (« Udshed.Loading is undefined »).
app_include_css = "udshed_desk.bundle.css"
# Sortable (glisser-déposer des niveaux) est déjà fourni par Frappe
# (window.Sortable, libs.bundle.js) : aucun chargement depuis un CDN externe.
app_include_js = [
	"udshed.bundle.js"
]

# include js, css files in header of web template
web_include_css = "udshed_web.bundle.css"
web_include_js = "udshed.bundle.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "udshed/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "udshed/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
home_page = "index"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Print Format Data
# ----------
# Injects the `data` context (from get_transcript_data) into the
# "Releve Notes" print format before HTML rendering. Frappe calls the
# last registered `pdf_body_html` hook (see frappe/www/printview.py).
pdf_body_html = "udshed.api.transcript.pdf_body_html"

# Jinja
# ----------

# add methods and filters to jinja environment
jinja = {
	"methods": "udshed.utils.jinja_methods",
}
# jinja_filters = "udshed.utils.jinja_filters"

# Installation
# ------------

# before_install = "udshed.install.before_install"
after_install = "udshed.scripts.install.after_install"

# Uninstallation
# ------------

before_uninstall = "udshed.scripts.uninstall.before_uninstall"
# after_uninstall = "udshed.uninstall.after_uninstall"

# Integration Setup
# ------------------
# before_app_install = "udshed.utils.before_app_install"
# after_app_install = "udshed.utils.after_app_install"

# Integration Cleanup
# -------------------
# before_app_uninstall = "udshed.utils.before_app_uninstall"
# after_app_uninstall = "udshed.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# notification_config = "udshed.notifications.get_notification_config"

# Permissions
# -----------
# Un compte uniquement « Student » ne voit que SA fiche et SON inscription
# (voir udshed/permissions.py). Le personnel n'est pas concerné.
# Réinscriptions et progression : périmètre par rôle (udshed/api/permission.py).
# Permissions : un étudiant ne voit que ses documents, un coordonnateur les candidatures de ses
# filières, un agent de scolarité / un doyen uniquement son périmètre (udshed/perimetre_hooks.py).
permission_query_conditions = {
	"Student": "udshed.perimetre_hooks.query_student",
	"Inscription Academique": "udshed.perimetre_hooks.query_inscription_academique",
	"Academic Reregistration": "udshed.perimetre_hooks.query_academic_reregistration",
	"Progression Academique": "udshed.perimetre_hooks.query_progression_academique",
	"Session Inscription Candidate": "udshed.perimetre_hooks.query_session_inscription_candidate",
	"Session Examen Note": "udshed.perimetre_hooks.query_session_examen_note",
	"Examen Anonymat": "udshed.perimetre_hooks.query_examen_anonymat",
	"Equivalence UE": "udshed.perimetre_hooks.query_equivalence_ue",
	"Deliberation Jury": "udshed.perimetre_hooks.query_deliberation_jury",
	"Jury Diplomation": "udshed.perimetre_hooks.query_jury_diplomation",
	"Diplome Etudiant": "udshed.perimetre_hooks.query_diplome_etudiant",
	"Derogation Saisie": "udshed.perimetre_hooks.query_derogation_saisie",
	"Confirmation Saisie": "udshed.perimetre_hooks.query_confirmation_saisie",
	"Resultat Academique": "udshed.perimetre_hooks.query_resultat_academique",
	"Resultat UE": "udshed.perimetre_hooks.query_resultat_ue",
	"Resultat Semestre": "udshed.perimetre_hooks.query_resultat_semestre",
	"Acte Academique": "udshed.perimetre_hooks.query_acte_academique",
	"Requete Etudiant": "udshed.perimetre_hooks.query_requete_etudiant",
	"Correction Note": "udshed.perimetre_hooks.query_correction_note",
	"Periode Saisie Notes": "udshed.perimetre_hooks.query_periode_saisie_notes",
}

has_permission = {
	"Student": "udshed.perimetre_hooks.has_student",
	"Inscription Academique": "udshed.perimetre_hooks.has_inscription_academique",
	"Academic Reregistration": "udshed.perimetre_hooks.has_academic_reregistration",
	"Progression Academique": "udshed.perimetre_hooks.has_progression_academique",
	"Session Inscription Candidate": "udshed.perimetre_hooks.has_session_inscription_candidate",
	"Session Examen Note": "udshed.perimetre_hooks.has_session_examen_note",
	"Examen Anonymat": "udshed.perimetre_hooks.has_examen_anonymat",
	"Equivalence UE": "udshed.perimetre_hooks.has_equivalence_ue",
	"Deliberation Jury": "udshed.perimetre_hooks.has_deliberation_jury",
	"Jury Diplomation": "udshed.perimetre_hooks.has_jury_diplomation",
	"Diplome Etudiant": "udshed.perimetre_hooks.has_diplome_etudiant",
	"Derogation Saisie": "udshed.perimetre_hooks.has_derogation_saisie",
	"Confirmation Saisie": "udshed.perimetre_hooks.has_confirmation_saisie",
	"Resultat Academique": "udshed.perimetre_hooks.has_resultat_academique",
	"Resultat UE": "udshed.perimetre_hooks.has_resultat_ue",
	"Resultat Semestre": "udshed.perimetre_hooks.has_resultat_semestre",
	"Acte Academique": "udshed.perimetre_hooks.has_acte_academique",
	"Requete Etudiant": "udshed.perimetre_hooks.has_requete_etudiant",
	"Correction Note": "udshed.perimetre_hooks.has_correction_note",
}

# Recherche des niveaux (table enfant de la filière) pour tous les champs Link qui y pointent :
# sans elle, Frappe refuse la recherche aux utilisateurs non administrateurs.
standard_queries = {"Field of study Level": "udshed.api.reference.niveaux_query"}

# Année académique de travail, fixée pour la session (udshed.utils.session_academique).
# extend_bootinfo (recalculé à chaque chargement) et non boot_session : Frappe met le boot en
# cache par utilisateur, alors que l'année dépend de la session.
extend_bootinfo = ["udshed.utils.session_academique.boot"]
on_logout = "udshed.utils.session_academique.effacer_session"

# Navigation du desk (Frappe 16.6x) : barres latérales udshed/udshed/sidebar/ et dock
# udshed/dock/ ; chaque rôle ne voit que les entrées que ses droits lui ouvrent
# (audit : udshed.utils.navigation.afficher_matrice).

# Document Events
# ---------------
# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"udshed.udshed.tasks.daily"
	],
	"cron": {
		# Chaque dimanche à 23 h : les séances de la semaine non déclarées
		# « Non fait » à la main passent à « Fait » (udshed/utils/pointage.py).
		"0 23 * * 0": ["udshed.utils.pointage.tache_dimanche"],
	},
}

# Testing
# -------

# before_tests = "udshed.install.before_tests"

# Extend DocType Class
# ------------------------------
# extend_doctype_class = {
# 	"Task": "udshed.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "udshed.event.get_events"
# }
# override_doctype_dashboards = {
# 	"Task": "udshed.task.get_dashboard_data"
# }

# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["udshed.utils.before_request"]
# after_request = ["udshed.utils.after_request"]

# Job Events
# ----------
# before_job = ["udshed.utils.before_job"]
# after_job = ["udshed.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"udshed.auth.validate"
# ]

# export_python_type_annotations = True

# Website redirects
# -----------------
# Parcours candidat : un formulaire générique (/candidature) et un espace
# unique (/mon-dossier). Étudiants : connexion Frappe standard (/login, avec le
# matricule comme identifiant) puis espace étudiant dans le desk.
# Les anciennes adresses (liens d'emails, favoris) redirigent vers les nouvelles.
website_redirects = [
	{"source": r"/session-de-2025(/.*)?", "target": "/candidature/new"},
	{"source": "/session-2025", "target": "/candidature/new"},
	{"source": "/depot-candidature", "target": "/candidature/new"},
	{"source": "/suivi-candidature", "target": "/mon-dossier"},
	{"source": "/mon-admission", "target": "/mon-dossier"},
	{"source": r"/inscription(/inscription)?", "target": "/mon-dossier"},
	{"source": "/connexion-etudiant", "target": "/login"},
	{"source": "/dashboard-etudiant", "target": "/app/mon-espace-etudiant"},
	{"source": "/espace-etudiant", "target": "/app/mon-espace-etudiant"},
]

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
