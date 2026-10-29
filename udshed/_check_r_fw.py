import frappe
from frappe.cache_manager import build_domain_restricted_doctype_cache

def exec():
    dt = build_domain_restricted_doctype_cache() or frappe.cache.get_value("domain_restricted_doctypes")
    print("restricted_doctypes count:", len(dt))
    for name in ["User", "Report", "Dashboard", "Module Def", "Workspace", "Workspace Sidebar", "Communication", "File", "ToDo", "Address", "Contact", "Session Inscription Candidate"]:
        print(name, "->", name in dt)
    pages = frappe.cache.get_value("domain_restricted_pages") or []
    print("restricted_pages count:", len(pages))
    print("restricted_pages sample:", pages[:10])