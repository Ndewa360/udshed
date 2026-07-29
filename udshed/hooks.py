<<<<<<< HEAD
app_name = "udshed"
app_title = "Udshed"
app_publisher = "Cédric Nguendap Bedjama"
app_description = "Outils de planification des cours"
app_email = "c.nguendap@ndewa-360.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "udshed",
		"logo": "/assets/udshed/images/logo.png",
		"title": "Udshed",
		"route": "/desk/planning-academique",
		"has_permission": "udshed.api.permission.has_app_permission"
	}
]



#Fixutres
#------------
fixtures = [
    {
        "dt" : "Role",
        "filters": [
            ["name","in",["Teacher","Coordonateur","Udshed Financial Admin", "Planning Manager", "Registration Manager"]]
        ]
    },
    
]


# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/udshed/css/udshed.css"
# app_include_js = "/assets/udshed/js/udshed.js"

# include js, css files in header of web template
# web_include_css = "/assets/udshed/css/udshed.css"
# web_include_js = "/assets/udshed/js/udshed.js"

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
# home_page = "login"

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

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "udshed.utils.jinja_methods",
# 	"filters": "udshed.utils.jinja_filters"
# }

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
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "udshed.utils.before_app_install"
# after_app_install = "udshed.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "udshed.utils.before_app_uninstall"
# after_app_uninstall = "udshed.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "udshed.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"udshed.tasks.all"
# 	],
# 	"daily": [
# 		"udshed.tasks.daily"
# 	],
# 	"hourly": [
# 		"udshed.tasks.hourly"
# 	],
# 	"weekly": [
# 		"udshed.tasks.weekly"
# 	],
# 	"monthly": [
# 		"udshed.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "udshed.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "udshed.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "udshed.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "udshed.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

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

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

=======
app_name = "udshed"
app_title = "Udshed"
app_publisher = "Cédric Nguendap Bedjama"
app_description = "Outils de planification des cours"
app_email = "c.nguendap@ndewa-360.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "udshed",
		"logo": "/assets/udshed/images/logo.png",
		"title": "Udshed",
		"route": "/desk/planning-academique",
		"has_permission": "udshed.api.permission.has_app_permission"
	}
]



#Fixutres
#------------
fixtures = [
    {
        "dt" : "Role",
        "filters": [
            ["name","in",["Teacher","Coordonateur","Udshed Financial Admin", "Planning Manager"]]
        ]
    },
    
]


# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/udshed/css/udshed.css"
# app_include_js = "/assets/udshed/js/udshed.js"

# include js, css files in header of web template
# web_include_css = "/assets/udshed/css/udshed.css"
# web_include_js = "/assets/udshed/js/udshed.js"

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
# home_page = "login"

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

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "udshed.utils.jinja_methods",
# 	"filters": "udshed.utils.jinja_filters"
# }

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
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "udshed.utils.before_app_install"
# after_app_install = "udshed.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "udshed.utils.before_app_uninstall"
# after_app_uninstall = "udshed.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "udshed.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"udshed.tasks.all"
# 	],
# 	"daily": [
# 		"udshed.tasks.daily"
# 	],
# 	"hourly": [
# 		"udshed.tasks.hourly"
# 	],
# 	"weekly": [
# 		"udshed.tasks.weekly"
# 	],
# 	"monthly": [
# 		"udshed.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "udshed.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "udshed.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "udshed.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "udshed.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

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

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

>>>>>>> 7a5ecfa (Ajout du module de réinscription)
