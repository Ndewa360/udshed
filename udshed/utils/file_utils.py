import pandas as pd

from frappe.utils import get_url

import frappe
import base64
from frappe.utils import get_site_path, now_datetime
import os

def read_frappe_excel(file_url):
    """
    Reads an Excel file exported from Frappe into a pandas DataFrame.
    
    Args:
        file_path (str): The path to the Excel file (e.g., 'path/to/your/export.xlsx').
        
    Returns:
        pd.DataFrame: The data from the Excel file.
    """
    
    frappe.logger().info(f"Début import - fichier: {file_url}")
    
    # Étape 1: Récupérer le chemin complet du fichier
    if file_url.startswith('/private/files/'):
        file_path = get_site_path('private', 'files', file_url.replace('/private/files/', ''))
    elif file_url.startswith('/files/'):
        file_path = get_site_path('public', 'files', file_url.replace('/files/', ''))
    else: 
        # Essayer de récupérer depuis File doctype
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        if file_doc:
            file_path = file_doc.get_full_path()
        else:
            frappe.throw( f'Fichier non trouvé: {file_url}')
        
        if not os.path.exists(file_path):
            frappe.throw( f'Le fichier n\'existe pas sur le serveur: {file_path}')
        

    try:
        excel_file = pd.ExcelFile(file_path)
        sheet_name = excel_file.sheet_names[0]  # Première feuille

        # Use pandas.read_excel to load the data
        df = pd.read_excel(file_path,sheet_name=sheet_name)
        df = df.fillna('')
        data = df.to_numpy().tolist()
        print("data to list ",data)
        print("Excel file successfully read into a pandas DataFrame.")
        return data
    except Exception as e:
        frappe.throw( f'Erreur de lecture du fichier. fichier non conforme: {file_path}')


def load_school_logo(school_logo):
    file_doc = frappe.get_doc("File", {"file_url": school_logo})
    file_path = file_doc.get_full_path()

    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    return f"data:image/png;base64,{encoded}"


def get_app_logo():
    logo_path = os.path.join(
        frappe.get_app_path("udshed"),"public","images","logo.png"
    )
    with open(logo_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()    
    return f"data:image/png;base64,{encoded}"

def get_url_app_logo():
    # logo_path = os.path.join("public","images","logo.png")
    # logo_path = get_url(logo_path)
    return frappe.utils.get_url("/assets/udshed/images/logo.png")


def get_url_school_logo(school_logo):
    file_doc = frappe.get_doc("File", {"file_url": school_logo})
    file_path = file_doc.file_url
    return frappe.utils.get_url(file_path)

