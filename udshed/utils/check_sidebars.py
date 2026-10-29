import frappe

def execute():
    frappe.connect()

    # Re-save the workspace to trigger cache invalidation
    ws = frappe.get_doc("Workspace", "Inscription - Reinscription")
    ws.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"Re-saved workspace: {ws.name}")

    # Clear all caches
    frappe.clear_cache()
    print("Cleared all caches")

    frappe.destroy()
