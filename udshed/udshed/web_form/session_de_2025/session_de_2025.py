import frappe

def get_context(context):
    context.filieres = frappe.get_all(
        "Field of study",
        fields=["name", "name_of_field", "field_of_study_code", "faculte"],
        order_by="name_of_field"
    )
    context.centres_examen = ["Bangangté", "Bafoussam", "Yaoundé", "Douala"]
    context.niveaux = [
        "BTS 1", "BTS 2",
        "LICENCE 1", "LICENCE 2", "LICENCE 3",
        "MASTER 1", "MASTER 2"
    ]
    context.max_file_size = 10  # MB
