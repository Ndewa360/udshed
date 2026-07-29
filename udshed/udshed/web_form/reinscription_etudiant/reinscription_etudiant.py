import frappe

def get_context(context):
    context.no_cache = 1

def validate(doc, method):
    """Validation avant sauvegarde de la réinscription"""
    pass

def before_insert(doc, method):
    """Avant insertion - vérifications"""
    pass

def after_insert(doc, method):
    """Après insertion - envoi notification"""
    pass
