import frappe

def exec():
    # Check if user has default_workspace
    user = frappe.get_doc("User", "matricule.student@ndewa.edu")
    print("User:", user.email)
    print("Username:", user.username)
    print("default_workspace:", user.default_workspace)
    print("Roles:", [r.role for r in user.roles])
    
    # Test login mechanism - find by username
    from frappe.auth import find_by_credentials
    print("\n--- Testing find_by_credentials ---")
    try:
        result = find_by_credentials("STU-9999", "any")
        print("Found by username:", result)
    except Exception as e:
        print("Error:", e)