# udshed/api/teaching_test.py

import frappe
import json
import pandas as pd
from frappe.utils import now_datetime, get_site_path
import os

# Données de test pour BTS_GL1
TEST_DATA = {
    'BTS_GL1': {
        '2024-2025': {
            'semester1': [
                {
                    'ue_code': 'IGL111',
                    'ue_title': 'Outils Mathématiques I',
                    'ue_credits': 6,
                    'courses': [
                        {
                            'code': 'IGL111a',
                            'title': 'Analyse Mathématiques I',
                            'credits': 3,
                            'type': 'ENS',
                            'nombre_dheure_cm': 25,
                            'nombre_dheure_td': 15,
                            'nombre_dheure_tp': 0,
                            'nombre_dheure_tpe': 5,
                            'total_hours': 45,
                            'fait_hours': 28,
                            'teacher': [],
                            'tcomm': '',
                            'cc': 1,
                            'cc_ret': 1,
                            'exam': 1,
                            'exam_ret': 0,
                            'pub': 1
                        },
                        {
                            'code': 'IGL111b',
                            'title': 'Algèbre Linéaire',
                            'credits': 3,
                            'type': 'ENS',
                            'nombre_dheure_cm': 14,
                            'nombre_dheure_td': 10,
                            'nombre_dheure_tp': 0,
                            'nombre_dheure_tpe': 6,
                            'total_hours': 30,
                            'fait_hours': 24,
                            'teacher': [{"teacher":'NGUEMFOUO Marcial',"type":"CM"}],
                            'tcomm': '',
                            'cc': 1,
                            'cc_ret': 1,
                            'exam': 1,
                            'exam_ret': 0,
                            'pub': 1
                        }
                    ]
                },
                {
                    'ue_code': 'IGL112',
                    'ue_title': 'Environnement de base I',
                    'ue_credits': 4,
                    'courses': [
                        {
                            'code': 'IGL112a',
                            'title': 'Environnement Micro-ordinateur',
                            'credits': 2,
                            'type': 'ENS',
                            'nombre_dheure_cm': 10,
                            'nombre_dheure_td': 6,
                            'nombre_dheure_tp': 14,
                            'nombre_dheure_tpe': 0,
                            'total_hours': 30,
                            'fait_hours': 30,
                            'teacher': [{"teacher":'SOB TAGNE Alfred de Vigny',"type":"CM"}],
                            'tcomm': '',
                            'cc': 1,
                            'cc_ret': 1,
                            'exam': 1,
                            'exam_ret': 0,
                            'pub': 1
                        },
                        {
                            'code': 'IGL112b',
                            'title': 'Outils bureautiques',
                            'credits': 2,
                            'type': 'ENS',
                            'nombre_dheure_cm': 0,
                            'nombre_dheure_td': 0,
                            'nombre_dheure_tp': 24,
                            'nombre_dheure_tpe': 6,
                            'total_hours': 30,
                            'fait_hours': 24,
                            'teacher': [{"teacher":'SOB TAGNE Alfred de Vigny',"type":"CM"}],
                            'tcomm': '',
                            'cc': 1,
                            'cc_ret': 1,
                            'exam': 0,
                            'exam_ret': 0,
                            'pub': 1
                        }
                    ]
                },
                {
                    'ue_code': 'IGL113',
                    'ue_title': 'Architecture',
                    'ue_credits': 3,
                    'courses': [
                        {
                            'code': 'IGL113a',
                            'title': 'Architecture des ordinateurs',
                            'credits': 3,
                            'type': 'ENS',
                            'nombre_dheure_cm': 25,
                            'nombre_dheure_td': 15,
                            'nombre_dheure_tp': 0,
                            'nombre_dheure_tpe': 5,
                            'total_hours': 45,
                            'fait_hours': 32,
                            'teacher': [{"teacher":'YANKAM MBOUBAG Hervé Patrick',"type":"CM"}],
                            'tcomm': '',
                            'cc': 1,
                            'cc_ret': 0,
                            'exam': 0,
                            'exam_ret': 0,
                            'pub': 1
                        }
                    ]
                },
                {
                    'ue_code': 'IGL114',
                    'ue_title': 'Algorithmique de Base',
                    'ue_credits': 3,
                    'courses': [
                        {
                            'code': 'IGL114a',
                            'title': 'Algorithmique de Base',
                            'credits': 3,
                            'type': 'ENS',
                            'nombre_dheure_cm': 25,
                            'nombre_dheure_td': 15,
                            'nombre_dheure_tp': 0,
                            'nombre_dheure_tpe': 5,
                            'total_hours': 45,
                            'fait_hours': 40,
                            'teacher': [{"teacher":'YANKAM MBOUBAG Hervé Patrick',"type":"CM"}],
                            'tcomm': '',
                            'cc': 1,
                            'cc_ret': 0,
                            'exam': 1,
                            'exam_ret': 0,
                            'pub': 1
                        }
                    ]
                }
            ],
            'semester2': [
                {
                    'ue_code': 'IGL121',
                    'ue_title': 'Outils mathématiques II',
                    'ue_credits': 4,
                    'courses': [
                        {
                            'code': 'IGL121a',
                            'title': 'Statistique descriptive',
                            'credits': 2,
                            'type': 'ENS',
                            'nombre_dheure_cm': 14,
                            'nombre_dheure_td': 10,
                            'nombre_dheure_tp': 0,
                            'nombre_dheure_tpe': 6,
                            'total_hours': 30,
                            'fait_hours': 0,
                            'teacher': [{"teacher":'FANTCHO Joseph Emmanuel',"type":"CM"}],
                            'tcomm': '',
                            'cc': 0,
                            'cc_ret': 0,
                            'exam': 0,
                            'exam_ret': 0,
                            'pub': 1
                        },
                        {
                            'code': 'IGL121b',
                            'title': 'Algèbre de BOOLE et des circuits',
                            'credits': 2,
                            'type': 'ENS',
                            'nombre_dheure_cm': 14,
                            'nombre_dheure_td': 10,
                            'nombre_dheure_tp': 0,
                            'nombre_dheure_tpe': 6,
                            'total_hours': 30,
                            'fait_hours': 24,
                            'teacher': [{"teacher":'LEALEA Theophile',"type":"CM"}],
                            'tcomm': '',
                            'cc': 1,
                            'cc_ret': 1,
                            'exam': 1,
                            'exam_ret': 1,
                            'pub': 1
                        }
                    ]
                },
                {
                    'ue_code': 'IGL122',
                    'ue_title': 'Environnement de base II',
                    'ue_credits': 4,
                    'courses': [
                        {
                            'code': 'IGL122a',
                            'title': "Système d'Exploitation I",
                            'credits': 2,
                            'type': 'ENS',
                            'nombre_dheure_cm': 14,
                            'nombre_dheure_td': 10,
                            'nombre_dheure_tp': 0,
                            'nombre_dheure_tpe': 6,
                            'total_hours': 30,
                            'fait_hours': 0,
                            'teacher': [{"teacher":'VUIDE PANGP Franck Manuel',"type":"CM"}],
                            'tcomm': '',
                            'cc': 0,
                            'cc_ret': 0,
                            'exam': 0,
                            'exam_ret': 0,
                            'pub': 1
                        },
                        {
                            'code': 'IGL122b',
                            'title': 'Programmation web 1',
                            'credits': 2,
                            'type': 'ENS',
                            'nombre_dheure_cm': 25,
                            'nombre_dheure_td': 15,
                            'nombre_dheure_tp': 0,
                            'nombre_dheure_tpe': 5,
                            'total_hours': 45,
                            'fait_hours': 0,
                            'teacher': [{"teacher":'SANOU KUE Flambel Junior',"type":"CM"}],
                            'tcomm': '',
                            'cc': 0,
                            'cc_ret': 0,
                            'exam': 0,
                            'exam_ret': 0,
                            'pub': 1
                        }
                    ]
                },
                {
                    'ue_code': 'IGL123',
                    'ue_title': 'Programmation I',
                    'ue_credits': 4,
                    'courses': [
                        {
                            'code': 'IGL123a',
                            'title': 'Programmation Structurée',
                            'credits': 4,
                            'type': 'ENS',
                            'nombre_dheure_cm': 24,
                            'nombre_dheure_td': 21,
                            'nombre_dheure_tp': 0,
                            'nombre_dheure_tpe': 15,
                            'total_hours': 60,
                            'fait_hours': 0,
                            'teacher': [{"teacher":'YANKAM MBOUBAG Hervé Patrick',"type":"CM"}],
                            'tcomm': '',
                            'cc': 0,
                            'cc_ret': 0,
                            'exam': 0,
                            'exam_ret': 0,
                            'pub': 1
                        }
                    ]
                }
            ]
        }
    }
}

@frappe.whitelist()
def get_teaching_grid(classe, academic_year, semester):
    """Récupérer la grille d'enseignement"""
    try:
        data = TEST_DATA.get(classe, {}).get(academic_year, {})
        semester_key = f'semester{semester}'
        result = data.get(semester_key, [])
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Erreur get_teaching_grid: {str(e)}")
        return {'error': str(e)}

@frappe.whitelist()
def get_stats(classe, academic_year):
    """Récupérer les statistiques"""
    try:
        data = TEST_DATA.get(classe, {}).get(academic_year, {})
        
        ue_count = 0
        course_count = 0
        total_credits = 0
        total_hours = 0
        
        for semester in ['semester1', 'semester2']:
            ues = data.get(semester, [])
            ue_count += len(ues)
            
            for ue in ues:
                courses = ue.get('courses', [])
                course_count += len(courses)
                
                for course in courses:
                    total_credits += course.get('credits', 0)
                    total_hours += course.get('total_hours', 0)
        
        return {
            'ue_count': ue_count,
            'course_count': course_count,
            'total_credits': total_credits,
            'total_hours': total_hours
        }
        
    except Exception as e:
        frappe.log_error(f"Erreur get_stats: {str(e)}")
        return {'error': str(e)}

@frappe.whitelist()
def update_course(course_code, field, value, academic_year, classe, semester):
    """Mettre à jour un champ d'un cours"""
    try:
        # Simuler une mise à jour
        frappe.logger().info(f"Mise à jour cours {course_code}: {field} = {value}")
        
        return {
            'success': True,
            'message': f'Cours {course_code} mis à jour'
        }
        
    except Exception as e:
        frappe.log_error(f"Erreur update_course: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

@frappe.whitelist()
def import_grid(file_url, academic_year):
    """Importer une grille depuis Excel"""
    try:
        # Simuler un import
        return {
            'success': True,
            'stats': {
                'ues_created': 2,
                'ues_updated': 0,
                'courses_created': 5,
                'courses_updated': 3
            }
        }
        
    except Exception as e:
        frappe.log_error(f"Erreur import_grid: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

@frappe.whitelist()
def export_grid(classe, academic_year, semester):
    """Exporter la grille en Excel"""
    try:
        data = get_teaching_grid(classe, academic_year, semester)
        
        # Créer un fichier Excel temporaire
        import tempfile
        import os
        from frappe.utils import get_site_path
        
        # Créer un DataFrame pandas
        rows = [
            ["Code UE","Code Cours","Intitule","Credits","Type","CM","TD","TP","TPE","Total","Enseignant"]
        ]
        
        for ue in data:
            # Ligne UE
            rows.append([ue['ue_code'], '', ue['ue_title'], ue['ue_credits'], 'UE', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
            
            # Lignes cours
            for course in ue['courses']:
                total_p = course['nombre_dheure_cm'] + course['nombre_dheure_td'] + course['nombre_dheure_tp']
                percentage = f"{(course['fait_hours'] / course['total_hours'] * 100):.1f}%" if course['total_hours'] > 0 else '0%'
                
                rows.append([
                    '', course['code'], course['title'], course['credits'], course['type'],
                    course['nombre_dheure_cm'], course['nombre_dheure_td'], course['nombre_dheure_tp'], total_p,
                    course['nombre_dheure_tpe'], course['total_hours'], course['fait_hours'], percentage,
                    course['teacher'], course['tcomm'],
                    course['cc'], course['cc_ret'], course['exam'], course['exam_ret'], course['pub']
                ])
        
        df = pd.DataFrame(rows)
        
        # Sauvegarder dans un fichier temporaire
        filename = f"teaching_grid_{classe}_{academic_year}_S{semester}.xlsx"
        file_path = get_site_path('public', 'files', 'temp', filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        df.to_excel(file_path, index=False, header=False)
        
        # Retourner l'URL du fichier
        return {
            'success': True,
            'file_url': f'/files/temp/{filename}'
        }
        
    except Exception as e:
        frappe.log_error(f"Erreur export_grid: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }