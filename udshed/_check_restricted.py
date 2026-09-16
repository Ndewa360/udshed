import frappe

def dump():
    from frappe.cache_manager import build_domain_restricted_doctype_cache
    val = frappe.cache.get_value("domain_restricted_doctypes")
    if val is None:
        val = build_domain_restricted_doctype_cache()
    print("restricted_doctypes (%d):" % len(val or []), sorted(val or [])[:80])

    from frappe.cache_manager import build_domain_restricted_page_cache
    p = frappe.cache.get_value("domain_restricted_pages")
    if p is None:
        p = build_domain_restricted_page_cache()
    print("restricted_pages:", sorted(p or []))

frappe.set_user("Administrator")
dump()