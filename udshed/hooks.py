app_name = "udshed"
app_title = "Udshed"
app_publisher = "Cédric Nguendap Bedjama"
app_description = "Gestion académique : candidatures, inscriptions et réinscriptions, planning, notes et résultats"
app_email = "c.nguendap@ndewa-360.com"
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
		"route": "/app/gestion-des-notes",
		"has_permission": "udshed.api.permission.has_app_permission",
		"role_home_page": {
			"All": "desk"
		}

	}
]

role_home_page = {
	"System Manager": "/desk",
	"Workspace Manager": "/desk",
	"Script Manager": "/desk",
	"Coordonateur": "/desk",
	"Teacher": "/desk",
	"Planning Manager": "/desk",
	"Registration Manager": "/desk",
	"Comptable": "/desk",
	"Agent de scolarité": "/desk",
	"Correcteur": "/desk",
	# Étudiant : directement son espace (desk restreint, voir boot_student.py).
	"Student": "/app/mon-espace-etudiant",
}


#Fixutres
#------------
fixtures = [
    {
        "dt" : "Role",
        "filters": [
            ["name","in",["System Manager","Workspace Manager","Script Manager","Teacher","Student","Guest","Desk User","Coordonateur","Planning Manager","Registration Manager","Agent de scolarité","Comptable","Correcteur"]]
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
        "dt": "Desktop Icon",
        "filters": [
            ["name","in",["Inscription - Reinscription","Gestion Des Notes","Insight","Planning Académique","Configuration"]]
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
permission_query_conditions = {
	"Student": "udshed.permissions.student_query",
	"Inscription Academique": "udshed.permissions.inscription_query",
	"Resultat Academique": "udshed.permissions.resultat_query",
	"Session Inscription Candidate": "udshed.permissions.candidature_query",
	"Academic Reregistration": "udshed.api.permission.academic_reregistration_query",
	"Progression Academique": "udshed.api.permission.progression_query",
}

has_permission = {
	"Student": "udshed.permissions.student_has_permission",
	"Inscription Academique": "udshed.permissions.inscription_has_permission",
	"Resultat Academique": "udshed.permissions.resultat_has_permission",
	"Session Inscription Candidate": "udshed.permissions.candidature_has_permission",
	"Academic Reregistration": "udshed.api.permission.academic_reregistration_has_permission",
	"Progression Academique": "udshed.api.permission.progression_has_permission",
}

# Boot Session
# ------------
# Restreint le desk des étudiants à l'espace « Inscription - Reinscription ».
boot_session = ["udshed.boot_student.configure_student_desk"]

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
