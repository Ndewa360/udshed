$(document).on('app_ready', function() {
    frappe.router.on('change', () => {
        const route = frappe.get_route();
        const [doctype, name] = route;

        // Le workspace "Inscription - Reinscription" redirige directement
        // vers la page "Rapport général"
        if (doctype === 'app' && name === 'inscription___reinscription') {
            frappe.set_route('app', 'rapport-general');
            return;
        }

        // Redirection de la page "Workspace" ouverte via le Desktop Icon
        if (doctype === 'workspace-sidebar' && name === 'inscription___reinscription') {
            frappe.set_route('app', 'rapport-general');
            return;
        }

        if (route[1] === 'planning-academique') {
            // Logique pour maintenir la sidebar active
            console.log("Side bar desk")
            frappe.desk.sidebar.set_item_active("Planning Academique");
        }
    });
});