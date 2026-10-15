import frappe
from frappe import _

@frappe.whitelist()
def get_dashboard_stats(academic_year, week_start, filiere=None):

    # Exemple simplifié
    planning = frappe.get_all(
        "Planning Item",
        filters={
            "academic_year": academic_year
        },
        fields=["cours", "date", "salle"]
    )

    total_courses = len(planning)
    total_teachers = 0
    rooms_used = len(set(p["salle"] for p in planning if p["salle"]))
    total_hours = total_courses * 2  # exemple

    chart_data = {}
    for p in planning:
        day = str(p["date"])
        chart_data.setdefault(day, 0)
        chart_data[day] += 2

    return {
        "kpi": {
            "total_courses": total_courses,
            "total_hours": total_hours,
            "total_teachers": total_teachers,
            "rooms_used": rooms_used
        },
        "chart": {
            "labels": list(chart_data.keys()),
            "values": list(chart_data.values())
        },
        "table": planning
    }


import frappe
from frappe import _
import json
import random
from datetime import datetime, timedelta

@frappe.whitelist()
def get_teacher_data(filters=None):
    """
    Retourne des données d'essai pour le développement
    """
    if isinstance(filters, str):
        filters = json.loads(filters)
    
    # Générer des données d'essai
    return generate_mock_data(filters)

def generate_mock_data(filters=None):
    """Génère un jeu de données d'essai réaliste"""
    
    # Enseignants fictifs
    teachers = [
        {"id": "T001", "name": "Dr. Martin Dupont", "dept": "Mathématiques", "avatar": "MD"},
        {"id": "T002", "name": "Prof. Sophie Laurent", "dept": "Physique", "avatar": "SL"},
        {"id": "T003", "name": "Dr. Jean Kouassi", "dept": "Informatique", "avatar": "JK"},
        {"id": "T004", "name": "Mme. Fatima Diallo", "dept": "Lettres", "avatar": "FD"},
        {"id": "T005", "name": "Prof. Marc Zadi", "dept": "Chimie", "avatar": "MZ"},
        {"id": "T006", "name": "Dr. Awa Touré", "dept": "Biologie", "avatar": "AT"},
        {"id": "T007", "name": "M. Paul Ekissi", "dept": "Histoire", "avatar": "PE"},
        {"id": "T008", "name": "Dr. Yves N'Guessan", "dept": "Philosophie", "avatar": "YN"}
    ]
    
    # Types de cours
    course_types = [
        {"code": "CM", "name": "Cours Magistral", "color": "badge-cm"},
        {"code": "TD", "name": "Travaux Dirigés", "color": "badge-td"},
        {"code": "TP", "name": "Travaux Pratiques", "color": "badge-tp"}
    ]
    
    # Filières et niveaux
    programs = [
        {"name": "Mathématiques", "faculty": "Sciences", "levels": ["L1", "L2", "L3", "M1", "M2"]},
        {"name": "Physique", "faculty": "Sciences", "levels": ["L1", "L2", "L3", "M1", "M2"]},
        {"name": "Informatique", "faculty": "Sciences", "levels": ["L1", "L2", "L3", "M1", "M2"]},
        {"name": "Lettres Modernes", "faculty": "Lettres", "levels": ["L1", "L2", "L3", "M1", "M2"]},
        {"name": "Chimie", "faculty": "Sciences", "levels": ["L1", "L2", "L3", "M1", "M2"]},
        {"name": "Biologie", "faculty": "Sciences", "levels": ["L1", "L2", "L3", "M1", "M2"]},
        {"name": "Histoire", "faculty": "Lettres", "levels": ["L1", "L2", "L3", "M1", "M2"]},
        {"name": "Philosophie", "faculty": "Lettres", "levels": ["L1", "L2", "L3", "M1", "M2"]}
    ]
    
    # Période
    period = filters.get('period', 'mois') if filters else 'mois'
    days = get_days_for_period(period)
    
    # Générer les données d'évolution
    evolution_data = []
    current_date = datetime.now()
    
    for i in range(days):
        date = current_date - timedelta(days=days-1-i)
        courses_count = random.randint(15, 40)
        total_hours = courses_count * random.uniform(1, 2.5)
        active_teachers = random.randint(5, 15)
        
        evolution_data.append({
            "date": date.strftime("%Y-%m-%d"),
            "courses_count": courses_count,
            "total_hours": round(total_hours, 1),
            "active_teachers": active_teachers
        })
    
    # Statistiques globales
    overview = {
        "total_courses": sum(d["courses_count"] for d in evolution_data),
        "active_teachers": 8,
        "total_hours": round(sum(d["total_hours"] for d in evolution_data), 1),
        "avg_hours": round(random.uniform(1.8, 2.2), 1),
        "avg_attendance": round(random.uniform(75, 95), 1),
        "by_type": [
            {"course_type": "CM", "count": random.randint(100, 200)},
            {"course_type": "TD", "count": random.randint(150, 250)},
            {"course_type": "TP", "count": random.randint(50, 120)}
        ]
    }
    
    # Cours par enseignant
    courses_by_teacher = []
    for teacher in teachers:
        courses_count = random.randint(15, 45)
        total_hours = courses_count * random.uniform(1.5, 2.5)
        unique_courses = random.randint(3, 8)
        programs_count = random.randint(2, 5)
        levels_count = random.randint(3, 8)
        avg_attendance = random.uniform(70, 98)
        
        courses_by_teacher.append({
            "teacher": teacher["id"],
            "teacher_name": teacher["name"],
            "department": teacher["dept"],
            "avatar": teacher["avatar"],
            "courses_count": courses_count,
            "total_hours": round(total_hours, 1),
            "avg_hours": round(total_hours / courses_count, 1),
            "unique_courses": unique_courses,
            "programs_count": programs_count,
            "levels_count": levels_count,
            "avg_attendance": round(avg_attendance, 1)
        })
    
    # Performance des enseignants
    teacher_performance = []
    for teacher in teachers:
        completed = random.randint(40, 80)
        cancelled = random.randint(0, 5)
        delayed = random.randint(2, 15)
        avg_delay = random.randint(5, 25)
        
        teacher_performance.append({
            "teacher": teacher["id"],
            "teacher_name": teacher["name"],
            "completed": completed,
            "cancelled": cancelled,
            "delayed": delayed,
            "avg_delay": avg_delay,
            "first_course": (datetime.now() - timedelta(days=random.randint(30, 180))).strftime("%Y-%m-%d"),
            "last_course": datetime.now().strftime("%Y-%m-%d")
        })
    
    # Cours par niveau
    courses_by_level = []
    for program in random.sample(programs, 6):
        for level in program["levels"]:
            if random.random() > 0.3:  # 70% de chance d'avoir des données
                courses_by_level.append({
                    "faculty": program["faculty"],
                    "program": program["name"],
                    "level": level,
                    "courses_count": random.randint(5, 30),
                    "total_hours": round(random.uniform(10, 70), 1),
                    "teachers_count": random.randint(2, 6),
                    "courses": random.randint(3, 10)
                })
    
    # Top enseignants
    top_teachers = sorted(courses_by_teacher, key=lambda x: x["courses_count"], reverse=True)[:5]
    
    return {
        "overview": overview,
        "courses_by_teacher": courses_by_teacher,
        "teacher_performance": teacher_performance,
        "courses_by_level": courses_by_level,
        "evolution": evolution_data,
        "top_teachers": top_teachers,
        "debug_info": {
            "period": period,
            "days": days,
            "filters_applied": filters
        }
    }

def get_days_for_period(period):
    """Retourne le nombre de jours pour une période donnée"""
    periods = {
        "semaine": 7,
        "mois": 30,
        "trimestre": 90,
        "annee": 365
    }
    return periods.get(period, 30)

@frappe.whitelist()
def get_filter_options():
    """Options pour les filtres (données d'essai)"""
    
    return {
        "faculties": ["Sciences", "Lettres", "Droit", "Médecine", "Économie"],
        "programs": [
            "Mathématiques", "Physique", "Chimie", "Informatique", "Biologie",
            "Lettres Modernes", "Histoire", "Philosophie", "Anglais",
            "Droit Public", "Droit Privé", "Sciences Économiques"
        ],
        "levels": ["L1", "L2", "L3", "M1", "M2", "Doctorat"],
        "teachers": [
            {"name": "T001", "teacher_name": "Dr. Martin Dupont"},
            {"name": "T002", "teacher_name": "Prof. Sophie Laurent"},
            {"name": "T003", "teacher_name": "Dr. Jean Kouassi"},
            {"name": "T004", "teacher_name": "Mme. Fatima Diallo"},
            {"name": "T005", "teacher_name": "Prof. Marc Zadi"},
            {"name": "T006", "teacher_name": "Dr. Awa Touré"},
            {"name": "T007", "teacher_name": "M. Paul Ekissi"},
            {"name": "T008", "teacher_name": "Dr. Yves N'Guessan"},
            {"name": "T009", "teacher_name": "Prof. Claire Bernard"},
            {"name": "T010", "teacher_name": "Dr. Amadou Koné"}
        ],
        "periods": [
            {"value": "semaine", "label": "Cette semaine"},
            {"value": "mois", "label": "Ce mois"},
            {"value": "trimestre", "label": "Ce trimestre"},
            {"value": "annee", "label": "Cette année"},
            {"value": "personnalise", "label": "Personnalisé"}
        ]
    }

@frappe.whitelist()
def get_teacher_details(teacher_id):
    """Détails d'un enseignant spécifique (données d'essai)"""
    
    teachers_details = {
        "T001": {
            "name": "Dr. Martin Dupont",
            "department": "Mathématiques",
            "email": "martin.dupont@universite.edu",
            "phone": "+225 07 89 45 67 89",
            "specialty": "Analyse numérique, Équations différentielles",
            "courses": [
                {"code": "MATH201", "name": "Analyse 3", "level": "L2", "hours": 24},
                {"code": "MATH301", "name": "Analyse numérique", "level": "L3", "hours": 30},
                {"code": "MATH401", "name": "Équations aux dérivées partielles", "level": "M1", "hours": 36}
            ],
            "stats": {
                "total_courses": 42,
                "total_hours": 98.5,
                "avg_attendance": 87.5,
                "punctuality": 92
            }
        },
        "T002": {
            "name": "Prof. Sophie Laurent",
            "department": "Physique",
            "email": "sophie.laurent@universite.edu",
            "phone": "+225 05 67 89 12 34",
            "specialty": "Physique quantique, Mécanique statistique",
            "courses": [
                {"code": "PHY202", "name": "Mécanique quantique 1", "level": "L2", "hours": 30},
                {"code": "PHY302", "name": "Physique statistique", "level": "L3", "hours": 30},
                {"code": "PHY403", "name": "Théorie des champs", "level": "M2", "hours": 40}
            ],
            "stats": {
                "total_courses": 38,
                "total_hours": 102.5,
                "avg_attendance": 91.2,
                "punctuality": 95
            }
        }
    }
    
    return teachers_details.get(teacher_id, {
        "name": "Enseignant non trouvé",
        "department": "-",
        "email": "-",
        "phone": "-",
        "specialty": "-",
        "courses": [],
        "stats": {
            "total_courses": 0,
            "total_hours": 0,
            "avg_attendance": 0,
            "punctuality": 0
        }
    })