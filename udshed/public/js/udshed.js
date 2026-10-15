$(document).on('app_ready', function() {
    frappe.router.on('change', () => {
        if (frappe.get_route()[1] === 'planning-academique') {
            // Logique pour maintenir la sidebar active
            console.log("Side bar desk")
            frappe.desk.sidebar.set_item_active("Planning Academique");
        }
    });
});