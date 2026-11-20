import frappe

ROLE_ALIASES = {
	"Enseignant": "Teacher",
	"student": "Student",
	"Coordinateur": "Coordonateur",
	"Coordonnateur": "Coordonateur",
	"Udshed Financial Admin": "Comptable",
}

ROLE_LABELS = {
	"System Manager": "Administrateur système",
	"Workspace Manager": "Gestionnaire des espaces de travail",
	"Script Manager": "Gestionnaire de scripts",
	"Coordonateur": "Coordonateur",
	"Teacher": "Enseignant",
	"Student": "Étudiant",
	"Planning Manager": "Gestionnaire de planning",
	"Registration Manager": "Gestionnaire des inscriptions",
	"Agent de scolarité": "Agent de scolarité",
	"Comptable": "Comptable",
	"Correcteur": "Correcteur",
	"Guest": "Invité",
	"Desk User": "Utilisateur du bureau",
}

CHILD_DOCTYPES = ("Has Role", "DocPerm", "Custom DocPerm")


def execute():
	for alias, target in ROLE_ALIASES.items():
		_ensure_role(target)
		for doctype in CHILD_DOCTYPES:
			frappe.db.sql(
				"update `tab{0}` set role = %s where role = %s".format(doctype),
				(target, alias),
			)
		_dedupe_role_rows(target)
		if frappe.db.exists("Role", alias):
			frappe.delete_doc("Role", alias, ignore_permissions=True, force=True)

	for role, label in ROLE_LABELS.items():
		if frappe.db.exists("Role", role):
			frappe.db.set_value("Role", role, "role_name", label)

	frappe.clear_cache()


def check_alias_roles():
	aliases = tuple(ROLE_ALIASES) + ("Planning Admin",)
	placeholders = ", ".join(["%s"] * len(aliases))
	return frappe.db.sql(
		"select parent, parenttype, role from `tabHas Role` where binary role in ({0})".format(placeholders),
		aliases,
		as_dict=True,
	)


def _ensure_role(role):
	if frappe.db.exists("Role", role):
		return
	doc = frappe.new_doc("Role")
	doc.role_name = role
	doc.desk_access = 1
	doc.insert(ignore_permissions=True)


def _dedupe_role_rows(role):
	rows = frappe.get_all(
		"Has Role",
		filters={"role": role},
		fields=["parent", "parenttype"],
		distinct=True,
	)
	for row in rows:
		names = frappe.get_all(
			"Has Role",
			filters={"parent": row.parent, "parenttype": row.parenttype, "role": role},
			pluck="name",
		)
		for name in names[1:]:
			frappe.db.delete("Has Role", {"name": name})
