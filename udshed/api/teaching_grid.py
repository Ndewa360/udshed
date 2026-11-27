import frappe
from frappe import _
import pandas as pd
import os
import re
import traceback
import unicodedata
from frappe.query_builder import DocType
from frappe.utils import get_site_path
import udshed.utils.file_utils as file_utils
import udshed.api.course as cours_api
import udshed.api.planning_permission as planning_permission


def _cle_alphabetique(texte):
    """Clé de tri : insensible à la casse et aux accents (ordinal alphabétique)."""
    norm = unicodedata.normalize("NFD", str(texte or "")).encode("ascii", "ignore").decode()
    return norm.lower()


def _cell_texte(valeur):
    """Normalise une cellule Excel en texte propre.

    Pandas livre les cellules numériques en float : un code cours purement
    numerique (« 101 ») arrive en 101.0 et une cellule vide en NaN. Sans cette
    conversion, les codes partent avec « .0 » dans la base et les cellules
    vides passent le test de vérité.
    """
    if valeur is None:
        return ""
    if isinstance(valeur, float):
        if valeur != valeur:  # NaN
            return ""
        if valeur.is_integer():
            return str(int(valeur))
        return str(valeur)
    return str(valeur).strip()


def _cell_entier(valeur, defaut=0):
    """Entier tolérant aux cellules Excel vides ou décimales (« 25 », 25.0)."""
    texte = _cell_texte(valeur).replace(",", ".")
    if not texte:
        return defaut
    try:
        return int(float(texte))
    except ValueError:
        return defaut


def _colonnes_emails(data):
    """Index des colonnes emails (CM, TD, TP) selon le format du fichier.

    Le template d'import a 12 colonnes (emails en 9-11) ; l'export de grille
    ajoute une colonne « Total » en 9, ce qui décale les enseignants en 10-12.
    Lire toujours en 9-11 faisait tomber sur la colonne Total (un float) et
    plantait l'import avec « 'float' object has no attribute 'split' ».
    """
    if len(data) >= 13:
        total = _cell_texte(data[9])
        suite = [_cell_texte(c) for c in data[10:13]]
        if any("@" in c for c in suite) and "@" not in total:
            return [10, 11, 12]
        if not total and any(suite):
            return [10, 11, 12]
        if isinstance(data[9], (int, float)) and data[9] == data[9]:
            return [10, 11, 12]
    return [9, 10, 11]


def _emails_par_type(data):
    """Adresses par type de cours : [(type CM, cellule), (type TD, …), (type TP, …)].

    Les cellules vides gardent leur position : un email en colonne TD ne sera
    jamais attribué au CM parce que la colonne CM était vide.
    """
    types = ("Cours Magistral (CM)", "Travaux Dirigés (TD)", "Travaux Pratique (TP)")
    return [
        (types[i], _cell_texte(data[col]))
        for i, col in enumerate(_colonnes_emails(data))
        if col < len(data)
    ]


#Todo 
# 1 - Rétirer les teaching units non utilisé d'une année  

@frappe.whitelist()
def get_academic_teaching_unit(academic_year,faculty,filiere,niveau,semestre):
    try:
        return _get_academic_teaching_unit_impl(academic_year,faculty,filiere,niveau,semestre)
    except (frappe.PermissionError, frappe.ValidationError):
        raise
    except Exception:
        frappe.log_error("teaching_grid get_academic_teaching_unit", traceback.format_exc())
        frappe.throw(_("Erreur lors du chargement de la grille pédagogique."))


def _get_academic_teaching_unit_impl(academic_year,faculty,filiere,niveau,semestre):
    planning_permission.assert_can_manage_grid(academic_year, faculty, filiere, niveau)
    if not (academic_year and filiere and niveau and semestre):
        return {
            "stats": {"ue_count": 0, "course_count": 0, "total_credits": 0, "total_hours": 0},
            "grid": [],
        }
    TeachingUnit = DocType("Teaching Unit")
    TeachingUnitValue = DocType("Teaching Unit Value")
    Course = DocType("Course")
    CourseTeacherItem = DocType("Course Teacher Item")
    CourseFieldOfStudyLevelItem = DocType("Course Field of study level item")
    CourseFieldOfStudy = DocType("Field of study")


    query = (
        frappe.qb.from_(TeachingUnit)
        .join(Course)
        .on(TeachingUnit.course==Course.name)
        .left_join(CourseTeacherItem)
        .on(CourseTeacherItem.parent == TeachingUnit.name)
        .join(CourseFieldOfStudyLevelItem)
        .on(CourseFieldOfStudyLevelItem.parent == TeachingUnit.name)
        .join(CourseFieldOfStudy)
        .on(CourseFieldOfStudy.name==CourseFieldOfStudyLevelItem.filiere)
        .left_join(TeachingUnitValue)
        .on(TeachingUnitValue.name == TeachingUnit.unite_de_valeur)
        .select(
            TeachingUnit.name,
            TeachingUnit.nombre_dheure_cm,
            TeachingUnit.nombre_dheure_tp,
            TeachingUnit.nombre_dheure_td,
            TeachingUnit.nombre_dheure_tpe,
            TeachingUnit.intitule_cours,
            TeachingUnit.course.as_("course_name"),
            TeachingUnit.semestre,
            CourseTeacherItem.enseignant,
            CourseTeacherItem.type_de_cours,
            CourseFieldOfStudyLevelItem.filiere,
            CourseFieldOfStudyLevelItem.niveau,
            CourseFieldOfStudyLevelItem.course_poid,
            CourseFieldOfStudy.faculte,
            TeachingUnitValue.code.as_("ue_code"),
            TeachingUnitValue.intitule.as_("ue_intitule")
        )
        .where(
            (TeachingUnit.academic_year == academic_year) &
            (CourseFieldOfStudy.faculte == faculty) &
            (CourseFieldOfStudyLevelItem.filiere==filiere) &
            ( TeachingUnit.semestre == semestre ) &
            ( CourseFieldOfStudyLevelItem.niveau == niveau )
        )	
    )
    result = {}
    filiere = frappe.get_doc("Field of study",filiere)

    stat_result = {
        'ue_count': 0,
        'course_count': 0,
        'total_credits': 0,
        'total_hours': 0
    }
    data = query.run(as_dict=True)
    for doc in data:
        ue_code = doc.ue_code

        if doc.ue_code in result:
            found_course = False
            for cours in result[ue_code]["courses"]:
                if cours["code"] == doc.course_name:
                    found_course=True
                    if doc.enseignant:
                        cours["teacher"].append({
                            "teacher":doc.enseignant,
                            "type_cours":doc.type_de_cours
                        })                
            if not found_course:
                result[ue_code]["courses"].append({
                    "code":doc.course_name,
                    "title": doc.intitule_cours,
                    "credits": doc.course_poid,
                    "type":"ENS",
                    "nombre_dheure_cm": doc.nombre_dheure_cm,
                    "nombre_dheure_td": doc.nombre_dheure_td,
                    "nombre_dheure_tp": doc.nombre_dheure_tp,
                    "nombre_dheure_tpe": doc.nombre_dheure_tpe,
                    "total_hours": int(doc.nombre_dheure_cm) + int(doc.nombre_dheure_td) + int(doc.nombre_dheure_tp) + int(doc.nombre_dheure_tpe),
                    "type_cours": doc.type_de_cours,
                    "filiere": doc.filiere,
                    "niveau": doc.niveau,
                    "ue_intitule": doc.ue_intitule,
                    "teaching_unit":doc.name,
                    "teacher":[]
                })
                if doc.enseignant:
                    result[ue_code]["courses"][len(result[ue_code]["courses"])-1]["teacher"].append({
                        "teacher":doc.enseignant,
                        "type_cours":doc.type_de_cours
                    })
                result[ue_code]["ue_credits"] += float(doc.course_poid) 
                stat_result["course_count"] +=1
                stat_result["total_credits"] +=float(doc.course_poid) 
                stat_result["total_hours"] +=int(doc.nombre_dheure_cm) + int(doc.nombre_dheure_td) + int(doc.nombre_dheure_tp) + int(doc.nombre_dheure_tpe)
        else:
            result[doc.ue_code] = {
                "ue_code":doc.ue_code,
                "ue_title":doc.ue_intitule,
                "ue_credits":float(doc.course_poid),
                "courses":[
                    {
                        "code":doc.course_name,
                        "title": doc.intitule_cours,
                        "credits": doc.course_poid,
                        "type":"ENS",
                        "nombre_dheure_cm": doc.nombre_dheure_cm,
                        "nombre_dheure_td": doc.nombre_dheure_td,
                        "nombre_dheure_tp": doc.nombre_dheure_tp,
                        "nombre_dheure_tpe": doc.nombre_dheure_tpe,
                        "total_hours": int(doc.nombre_dheure_cm) + int(doc.nombre_dheure_td) + int(doc.nombre_dheure_tp) + int(doc.nombre_dheure_tpe),
                        "type_cours": doc.type_de_cours,
                        "filiere": doc.filiere,
                        "niveau": doc.niveau,
                        "ue_intitule": doc.ue_intitule,
                        "teaching_unit":doc.name,
                        "teacher":[]
                    }
                ],
            }

            if doc.enseignant:
                result[ue_code]["courses"][len(result[ue_code]["courses"])-1]["teacher"].append({
                    "teacher":doc.enseignant,
                    "type_cours":doc.type_de_cours
                })
            stat_result["ue_count"] +=1
            stat_result["course_count"] +=1
            stat_result["total_credits"] +=float(doc.course_poid) 
            stat_result["total_hours"] +=int(doc.nombre_dheure_cm) + int(doc.nombre_dheure_td) + int(doc.nombre_dheure_tp) + int(doc.nombre_dheure_tpe)

    
    from udshed.utils import grille
    from udshed.utils.planning_conflits import cours_lies

    classe_courante = (filiere.name, str(niveau))
    libelles = {}

    def libelle_classe(f, n):
        if (f, n) not in libelles:
            nom = frappe.db.get_value("Field of study", f, "name_of_field") or f
            libelles[(f, n)] = f"{nom} — {grille.libelle_niveau(n)}"
        return libelles[(f, n)]

    for ue in result.keys():
        result[ue]["courses"] = sorted(
            result[ue]["courses"], key=lambda course: (_cle_alphabetique(course["title"]), course["code"])
        )
        for course in result[ue]["courses"]:
            # Tronc commun : autres classes qui partagent ce même cours.
            autres = sorted(c for c in grille.classes_du_cours(course["teaching_unit"]) if c != classe_courante)
            course["classes_partagees"] = len(autres)
            course["classes_partagees_libelles"] = [libelle_classe(f, n) for f, n in autres]
            # Liaison manuelle : cours d'autres grilles déclarés identiques, avec leurs classes.
            lies = []
            for tu in sorted(cours_lies(course["teaching_unit"])):
                info = frappe.db.get_value("Teaching Unit", tu, ["course", "intitule_cours"], as_dict=True) or {}
                lies.append({
                    "code": info.get("course") or tu,
                    "intitule": info.get("intitule_cours") or "",
                    "classes": [libelle_classe(f, n) for f, n in sorted(grille.classes_du_cours(tu))],
                })
            course["cours_lies"] = len(lies)
            course["cours_lies_details"] = lies
            course["avertissement"] = grille.coherence_credits(course["credits"], course)

    return {"stats":stat_result,"grid":list(dict(sorted(result.items(), key=lambda item: str(item[0]))).values())}







def _cell_nombre(valeur, defaut=0.0):
    """Nombre décimal tolérant (« 2,5 », 2.5, cellule vide) : les crédits peuvent être fractionnaires."""
    texte = _cell_texte(valeur).replace(",", ".")
    if not texte:
        return defaut
    try:
        return float(texte)
    except ValueError:
        return None


def _meme_valeur(actuelle, importee):
    """Compare une valeur en base et une valeur du fichier (nombres ou texte)."""
    if isinstance(importee, float):
        return frappe.utils.flt(actuelle) == importee
    return str(actuelle or "").strip() == str(importee or "").strip()


# Titres ignorés quand on compare des noms (« Dr Aline Fotso » = « FOTSO Aline »).
_TITRES = {"dr", "pr", "prof", "professeur", "docteur", "m", "mr", "mme", "mlle", "monsieur", "madame",
           "mademoiselle", "ing", "me"}


def _jetons(texte):
    texte = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode().lower()
    return [j for j in re.split(r"[^a-z0-9]+", texte) if j]


def _cle_nom(texte, titres):
    return tuple(sorted(j for j in _jetons(texte) if j not in titres))


def _index_enseignants():
    """Index des enseignants par e-mail et par nom normalisé (une seule requête par analyse)."""
    titres = set(_TITRES)
    champ_grade = frappe.get_meta("Teacher").get_field("grade")
    for option in (champ_grade.options or "").split("\n") if champ_grade else []:
        titres.update(_jetons(option))
    emails, noms = {}, {}
    for t in frappe.get_all("Teacher", fields=["name", "email", "autres_emails", "first_name", "last_name"]):
        for adresse in [t.email, *re.split(r"[,;\s]+", t.autres_emails or "")]:
            if adresse and "@" in adresse:
                emails.setdefault(adresse.strip().lower(), t.name)
        cle = _cle_nom(f"{t.first_name or ''} {t.last_name or ''}", titres)
        if cle:
            noms.setdefault(cle, []).append(t.name)
    return {"emails": emails, "noms": noms, "titres": titres}


def _resoudre_enseignant(entree, index=None):
    """(nom du Teacher, None) ou (None, message) — sans lever d'exception.

    Accepte l'adresse e-mail, l'identifiant de la fiche (« Dr Aline Fotso ») ou le
    nom seul, avec ou sans titre, dans n'importe quel ordre, sans tenir compte des
    majuscules ni des accents. Un nom porté par plusieurs enseignants n'est pas deviné.
    """
    index = index or _index_enseignants()
    texte = " ".join(str(entree or "").split())
    if "@" in texte:
        teacher = index["emails"].get(texte.lower())
        if teacher:
            return teacher, None
        return None, _("Enseignant « {0} » introuvable : case laissée vide (à assigner dans la grille).").format(texte)
    if frappe.db.exists("Teacher", texte):
        return frappe.db.get_value("Teacher", texte, "name"), None
    candidats = index["noms"].get(_cle_nom(texte, index["titres"]), [])
    if len(candidats) == 1:
        return candidats[0], None
    if candidats:
        return None, _("Plusieurs enseignants s'appellent « {0} » ({1}) : indiquez l'adresse e-mail. Case laissée vide.").format(
            texte, ", ".join(sorted(candidats))
        )
    return None, _("Enseignant « {0} » introuvable : case laissée vide (à assigner dans la grille).").format(texte)


def _cours_classe_actuels(academic_year, filiere, niveau, semestre):
    """Cours actuellement rattachés à la classe pour ce semestre : {code cours: Teaching Unit}."""
    rows = frappe.db.sql(
        """
        SELECT tu.name, tu.course
        FROM `tabTeaching Unit` tu
        INNER JOIN `tabCourse Field of study level item` l
            ON l.parent = tu.name AND l.parenttype = 'Teaching Unit'
        WHERE tu.academic_year = %s AND tu.semestre = %s AND l.filiere = %s AND l.niveau = %s
        """,
        (academic_year, semestre, filiere, niveau),
        as_dict=True,
    )
    return {r.course: r.name for r in rows}


# Colonnes du modèle d'import, par position (repli si les en-têtes ne sont pas reconnus).
_POSITIONS_MODELE = {"code_ue": 0, "code_cours": 1, "intitule": 2, "credits": 3, "type": 4,
                     "cm": 5, "td": 6, "tp": 7, "tpe": 8}
_COLONNES_REQUISES = ("code_ue", "code_cours", "intitule", "credits")
_LIBELLES_COLONNES = {
    "code_ue": "Code UE", "code_cours": "Code Cours", "intitule": "Intitulé", "credits": "Crédits",
    "type": "TYPE", "cm": "CM", "td": "TD", "tp": "TP", "tpe": "TPE",
    "ens_cm": "Enseignant CM", "ens_td": "Enseignant TD", "ens_tp": "Enseignant TP", "ens": "Enseignant",
}
_TYPES_COURS = {"cm": "Cours Magistral (CM)", "td": "Travaux Dirigés (TD)", "tp": "Travaux Pratique (TP)"}


def _cle_entete(entete):
    """« Intitulés des cours » -> « intitules des cours » (casse, accents, ponctuation)."""
    texte = re.sub(r"\.\d+$", "", str(entete or "").strip())  # suffixe pandas des doublons
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", texte).split())


def _role_colonne(entete):
    """Rôle d'une colonne d'après son en-tête, ou None si inconnue."""
    cle = _cle_entete(entete)
    mots = set(cle.split())
    if not cle:
        return None
    if "enseignant" in cle or "enseignants" in mots or "email" in mots or "e mail" in cle or "professeur" in cle:
        for t in ("cm", "td", "tp"):
            if t in mots:
                return f"ens_{t}"
        return "ens"
    if cle.startswith("code"):
        if "ue" in mots or "uv" in mots or "unite" in cle or "module" in mots:
            return "code_ue"
        return "code_cours"
    if cle in ("ue", "uv"):
        return "code_ue"
    if cle.startswith("intitule") or cle.startswith("libelle") or cle in ("cours", "matiere", "matieres"):
        return "intitule"
    if cle.startswith("credit") or cle in ("cr", "ects"):
        return "credits"
    if cle in ("type", "type ligne"):
        return "type"
    if cle in ("cm", "td", "tp", "tpe"):
        return cle
    # « Volume CM », « Heures TD », « Nb heures TP »…
    dernier = cle.split()[-1]
    if dernier in ("cm", "td", "tp", "tpe") and mots & {"volume", "heures", "heure", "nb", "nombre", "h"}:
        return dernier
    if cle.startswith("total"):
        return "total"
    return None


def _carte_colonnes(entetes, largeur):
    """{rôle: index de colonne} déduit des en-têtes, sinon la position du modèle.

    Les fichiers préparés à la main n'ont pas toujours la colonne TYPE ou ont
    une seule colonne « Enseignant » : lire par position décalait alors toutes
    les colonnes (heures fausses, email lu comme un nombre…).
    """
    carte = {}
    for index, entete in enumerate(entetes or []):
        role = _role_colonne(entete)
        if role and role not in carte:
            carte[role] = index
    if all(r in carte for r in _COLONNES_REQUISES):
        return carte, "entetes"
    # Repli : positions du modèle ; les emails sont alors repérés ligne par
    # ligne (_emails_par_type gère le modèle à 12 colonnes et l'export à 13).
    return dict(_POSITIONS_MODELE), "position"


def _lire_fichier_grille(file_url):
    """(lignes, en-têtes) : ordre des arguments attendu par _analyser_grille."""
    entetes, lignes = file_utils.read_excel_avec_entetes(file_url)
    return lignes, entetes


def _analyser_fichier(file_url, academic_year, filiere, niveau, semestre):
    lignes, entetes = _lire_fichier_grille(file_url)
    return _analyser_grille(lignes, academic_year, filiere, niveau, semestre, entetes=entetes)


def _type_par_heures(valeurs):
    """Type de séance d'un enseignant indiqué dans une colonne « Enseignant » unique."""
    for cle in ("cm", "td", "tp"):
        if (valeurs.get(f"nombre_dheure_{cle}") or 0) > 0:
            return _TYPES_COURS[cle]
    return _TYPES_COURS["cm"]


def _analyser_grille(data_grid, academic_year, filiere, niveau, semestre, entetes=None):
    """Analyse complète d'un fichier de grille, SANS aucune écriture.

    Sert à la prévisualisation et, à l'identique, à l'import réel : ce qui est
    affiché est exactement ce qui sera appliqué.
    """
    from udshed.utils import grille

    filiere_doc = frappe.get_doc("Field of study", filiere)
    avec_ue = bool(filiere_doc.has_uv_in_grid)
    ues, cours, erreurs = [], [], []
    ue_courante = None
    codes_vus = {}
    largeur = max((len(d) for d in data_grid), default=0)
    carte, mode = _carte_colonnes(entetes, largeur)
    index_enseignants = _index_enseignants()

    def cellule(data, role):
        index = carte.get(role)
        return data[index] if index is not None and index < len(data) else ""

    if not avec_ue:
        ue_courante = {"code": "UNKNOW", "intitule": _("(sans UE)"), "ligne": None, "cours": [],
                       "statut": "existante" if frappe.db.exists("Teaching Unit Value", {"code": "UNKNOW", "academic_year": academic_year}) else "nouvelle"}
        ues.append(ue_courante)

    for index, data in enumerate(data_grid):
        ligne = index + 2  # ligne Excel (la 1re ligne est l'en-tête)
        cellules = [_cell_texte(c) for c in data]
        if not any(cellules):
            continue
        code_ue = _cell_texte(cellule(data, "code_ue"))
        code_cours = _cell_texte(cellule(data, "code_cours"))
        type_ligne = _cell_texte(cellule(data, "type"))
        intitule = _cell_texte(cellule(data, "intitule"))
        if code_ue.lower().startswith("total") or code_ue.startswith("==="):
            continue
        if mode == "position" and len(cellules) < 9:
            erreurs.append({"ligne": ligne, "message": _("Colonnes non reconnues : utilisez les en-têtes du modèle (Code UE, Code Cours, Intitulés, Crédits, CM, TD, TP, TPE, Enseignant…).")})
            continue

        est_ue = bool(code_ue) and (type_ligne.upper() == "UE" or not code_cours)
        if est_ue:
            existante = frappe.db.exists("Teaching Unit Value", {"code": code_ue, "academic_year": academic_year})
            ue_courante = {"code": code_ue, "intitule": intitule, "ligne": ligne, "cours": [],
                           "statut": "existante" if existante else "nouvelle"}
            ues.append(ue_courante)
            continue
        if not code_cours:
            continue
        if ue_courante is None:
            erreurs.append({"ligne": ligne, "message": _("Le cours {0} n'a aucune UE au-dessus de lui : ajoutez une ligne UE (code en colonne A).").format(code_cours)})
            continue
        if code_cours in codes_vus:
            erreurs.append({"ligne": ligne, "message": _("Le cours {0} apparaît deux fois (déjà ligne {1}).").format(code_cours, codes_vus[code_cours])})
            continue
        codes_vus[code_cours] = ligne

        valeurs = {
            "intitule_cours": intitule,
            "credits": _cell_nombre(cellule(data, "credits")),
            "nombre_dheure_cm": _cell_nombre(cellule(data, "cm")),
            "nombre_dheure_td": _cell_nombre(cellule(data, "td")),
            "nombre_dheure_tp": _cell_nombre(cellule(data, "tp")),
            "nombre_dheure_tpe": _cell_nombre(cellule(data, "tpe")),
        }
        invalides = [k for k, v in valeurs.items() if v is None]
        if invalides:
            libelles = {"credits": "Crédits", "nombre_dheure_cm": "CM", "nombre_dheure_td": "TD",
                        "nombre_dheure_tp": "TP", "nombre_dheure_tpe": "TPE"}
            erreurs.append({"ligne": ligne, "message": _("Valeur numérique invalide pour le cours {0} (colonne {1}).").format(
                code_cours, ", ".join(libelles.get(k, k) for k in invalides))})
            continue
        if not valeurs["intitule_cours"]:
            erreurs.append({"ligne": ligne, "message": _("Intitulé manquant pour le cours {0}.").format(code_cours)})
            continue

        if mode == "position":
            cellules_enseignants = _emails_par_type(data)
        else:
            cellules_enseignants = [(_TYPES_COURS[t], _cell_texte(cellule(data, f"ens_{t}"))) for t in ("cm", "td", "tp")]
            if "ens" in carte:
                # Colonne « Enseignant » unique : type déduit des heures du cours.
                cellules_enseignants.append((_type_par_heures(valeurs), _cell_texte(cellule(data, "ens"))))

        enseignants, ignores = [], []
        for type_cours, cellule_ens in cellules_enseignants:
            for entree in [e.strip() for e in re.split(r"[,;/]", cellule_ens or "") if e.strip()]:
                teacher, message = _resoudre_enseignant(entree, index_enseignants)
                if message:
                    # L'enseignant n'existe pas (encore) : le cours est importé, la case reste vide.
                    ignores.append(message)
                else:
                    enseignants.append({"enseignant": teacher, "type_de_cours": type_cours})

        existant = frappe.db.get_value("Teaching Unit", {"course": code_cours, "academic_year": academic_year}, "name")
        element = {"ligne": ligne, "code": code_cours, "ue": ue_courante["code"], "teaching_unit": existant,
                   "enseignants": enseignants, "enseignants_ignores": ignores, "avertissements": list(ignores),
                   "autres_classes": [], "changements": [], **valeurs}
        avertissement = grille.coherence_credits(valeurs["credits"], valeurs)
        if avertissement:
            element["avertissements"].append(avertissement)

        if not existant:
            element["statut"] = "nouveau"
        else:
            classes = grille.classes_du_cours(existant)
            autres = sorted(c for c in classes if c != (filiere, str(niveau)))
            element["autres_classes"] = [f"{f} {grille.libelle_niveau(n)}" for f, n in autres]
            element["statut"] = "mis_a_jour" if (filiere, str(niveau)) in classes else "ajout_classe"
            if element["statut"] == "mis_a_jour":
                element["changements"] = _changements(existant, element, filiere, niveau, bool(autres))
            if autres:
                tu = frappe.get_doc("Teaching Unit", existant)
                differences = [
                    champ for champ in ("intitule_cours", *grille.CHAMPS_HEURES)
                    if not _meme_valeur(tu.get(champ), valeurs[champ])
                ]
                if differences:
                    element["avertissements"].append(
                        _("Cours partagé avec {0} : intitulé, heures et enseignants communs sont conservés ; seuls les crédits de cette classe sont importés.").format(
                            ", ".join(element["autres_classes"])
                        )
                    )
        ue_courante["cours"].append(element)
        cours.append(element)

    retraits = []
    actuels = _cours_classe_actuels(academic_year, filiere, niveau, semestre)
    for code, teaching_unit in sorted(actuels.items()):
        if code in codes_vus:
            continue
        deps = grille.dependances_cours_classe(teaching_unit, filiere, niveau)
        retraits.append({
            "code": code,
            "teaching_unit": teaching_unit,
            "intitule": frappe.db.get_value("Teaching Unit", teaching_unit, "intitule_cours") or code,
            "dependances": grille.decrire_dependances(deps),
            "bloque": bool(deps),
        })

    ues = [u for u in ues if u["cours"] or u["code"] != "UNKNOW"]
    stats = {
        "ues_nouvelles": sum(1 for u in ues if u["statut"] == "nouvelle"),
        "ues_existantes": sum(1 for u in ues if u["statut"] == "existante"),
        "cours_nouveaux": sum(1 for c in cours if c["statut"] == "nouveau"),
        "cours_mis_a_jour": sum(1 for c in cours if c["statut"] == "mis_a_jour"),
        "cours_ajoutes_a_la_classe": sum(1 for c in cours if c["statut"] == "ajout_classe"),
        "cours_retires": sum(1 for r in retraits if not r["bloque"]),
        "retraits_bloques": sum(1 for r in retraits if r["bloque"]),
        "avertissements": sum(len(c["avertissements"]) for c in cours),
        "enseignants_ignores": sum(len(c["enseignants_ignores"]) for c in cours),
        "cours_modifies": sum(1 for c in cours if c["changements"]),
        "erreurs": len(erreurs),
        "total_credits": sum(c["credits"] for c in cours),
        "total_heures": sum(grille.heures_face_a_face(c) + c["nombre_dheure_tpe"] for c in cours),
    }
    if not cours and not erreurs:
        erreurs.append({"ligne": None, "message": _("Aucun cours trouvé dans le fichier.")})
        stats["erreurs"] = 1
    colonnes = {
        _LIBELLES_COLONNES[role]: (entetes[index] if mode == "entetes" and entetes and index < len(entetes) else f"colonne {index + 1}")
        for role, index in sorted(carte.items(), key=lambda x: x[1])
        if role in _LIBELLES_COLONNES
    }
    return {"ues": ues, "cours": cours, "retraits": retraits, "erreurs": erreurs, "stats": stats,
            "colonnes": colonnes, "mode_colonnes": mode}


def _changements(teaching_unit, element, filiere, niveau, partage):
    """Avant / après d'un cours déjà dans la grille (ce que l'import va réellement changer)."""
    tu = frappe.get_doc("Teaching Unit", teaching_unit)
    ligne = next((r for r in tu.course_levels if r.filiere == filiere and str(r.niveau) == str(niveau)), None)
    resultat = []

    def comparer(libelle, avant, apres):
        if not _meme_valeur(avant, apres):
            resultat.append({"champ": libelle, "avant": avant, "apres": apres})

    comparer(_("Crédits"), ligne.course_poid if ligne else None, element["credits"])
    if partage:
        return resultat  # tronc commun : seuls les crédits de la classe sont importés
    comparer(_("Intitulé"), tu.intitule_cours, element["intitule_cours"])
    for champ, libelle in (("nombre_dheure_cm", "CM"), ("nombre_dheure_td", "TD"), ("nombre_dheure_tp", "TP"),
                           ("nombre_dheure_tpe", "TPE")):
        comparer(libelle, tu.get(champ), element[champ])
    ue_actuelle = frappe.db.get_value("Teaching Unit Value", tu.unite_de_valeur, "code") if tu.unite_de_valeur else ""
    if element["ue"] != "UNKNOW":
        comparer(_("UE"), ue_actuelle, element["ue"])
    court = {"Cours Magistral (CM)": "CM", "Travaux Dirigés (TD)": "TD", "Travaux Pratique (TP)": "TP"}

    def liste(lignes):
        return ", ".join(sorted(f"{e['enseignant']} ({court.get(e['type_de_cours'], e['type_de_cours'])})" for e in lignes))

    comparer(_("Enseignants"), liste([{"enseignant": r.enseignant, "type_de_cours": r.type_de_cours} for r in tu.table_enseignant]),
             liste(element["enseignants"]))
    return resultat


@frappe.whitelist()
def previsualiser_import_grille(file_url, academic_year, faculty, filiere, niveau, semestre):
    """Prévisualisation de l'import : ce qui sera créé, mis à jour, retiré ou
    bloqué, avec erreurs et avertissements. Aucune écriture."""
    planning_permission.assert_can_manage_grid(academic_year, faculty, filiere, niveau, semestre)
    return _analyser_fichier(file_url, academic_year, filiere, niveau, semestre)


def _appliquer_ue(ue, academic_year, semestre):
    nom = frappe.db.exists("Teaching Unit Value", {"code": ue["code"], "academic_year": academic_year})
    if nom:
        doc = frappe.get_doc("Teaching Unit Value", nom)
        if ue["code"] != "UNKNOW" and (doc.intitule != ue["intitule"] or doc.semestre != semestre):
            doc.intitule = ue["intitule"]
            doc.semestre = semestre
            doc.save(ignore_permissions=True)
        return doc.name
    return frappe.get_doc({
        "doctype": "Teaching Unit Value",
        "code": ue["code"],
        "intitule": "" if ue["code"] == "UNKNOW" else ue["intitule"],
        "semestre": semestre,
        "academic_year": academic_year,
    }).insert(ignore_permissions=True).name


def _appliquer_cours(element, ue_name, academic_year, filiere, niveau, semestre):
    credits = element["credits"]
    if element["teaching_unit"]:
        tu = frappe.get_doc("Teaching Unit", element["teaching_unit"])
        partage = bool(element["autres_classes"])
    else:
        if not frappe.db.exists("Course", element["code"]):
            frappe.get_doc({
                "doctype": "Course",
                "code": element["code"],
                "intitule": element["intitule_cours"],
                "semestre": semestre,
                **{champ: int(element[champ]) for champ in ("nombre_dheure_cm", "nombre_dheure_td", "nombre_dheure_tp", "nombre_dheure_tpe")},
            }).insert(ignore_permissions=True)
        tu = frappe.new_doc("Teaching Unit")
        tu.course = element["code"]
        tu.academic_year = academic_year
        partage = False

    if not partage:
        # Cours propre à la classe : la grille fait foi pour tout son contenu.
        tu.intitule_cours = element["intitule_cours"]
        tu.unite_de_valeur = ue_name
        tu.semestre = semestre
        tu.credits = int(round(credits))
        for champ in ("nombre_dheure_cm", "nombre_dheure_td", "nombre_dheure_tp", "nombre_dheure_tpe"):
            tu.set(champ, int(element[champ]))
        tu.set("table_enseignant", [])
        vus = set()
        for e in element["enseignants"]:
            cle = (e["enseignant"], e["type_de_cours"])
            if cle not in vus:
                vus.add(cle)
                tu.append("table_enseignant", e)

    # Crédits propres à la classe : ligne mise à jour ou ajoutée (jamais dupliquée).
    ligne = next((r for r in tu.course_levels if r.filiere == filiere and str(r.niveau) == str(niveau)), None)
    if ligne:
        ligne.course_poid = credits
    else:
        tu.append("course_levels", {"filiere": filiere, "niveau": niveau, "course_poid": credits})

    if tu.is_new():
        tu.insert(ignore_permissions=True)
    else:
        tu.save(ignore_permissions=True)
    return tu.name


@frappe.whitelist()
def import_grid(file_url, academic_year, faculty, filiere, niveau, semestre):
    """Importe la grille d'une classe pour un semestre.

    Même analyse que la prévisualisation. Tout ou rien : la moindre erreur
    annule l'import (aucune grille à moitié effacée). Les cours retirés du
    fichier ne sont détachés de la classe que s'ils n'ont aucune donnée
    (notes, inscriptions, séances…) pour elle ; sinon ils sont conservés et
    signalés.
    """
    from udshed.utils import grille

    planning_permission.assert_can_manage_grid(academic_year, faculty, filiere, niveau, semestre)
    analyse = _analyser_fichier(file_url, academic_year, filiere, niveau, semestre)
    if analyse["erreurs"]:
        details = "<br>".join(
            (_("Ligne {0} : ").format(e["ligne"]) if e["ligne"] else "") + e["message"]
            for e in analyse["erreurs"][:30]
        )
        frappe.throw(
            _("Import annulé, corrigez le fichier :") + "<br>" + details,
            title=_("Grille invalide"),
        )

    record_stat = {
        "ues_created": 0, "ues_updated": 0, "ues_deleted": 0,
        "courses_created": 0, "courses_updated": 0, "courses_deleted": 0,
        "courses_kept": 0,
    }
    try:
        for ue in analyse["ues"]:
            ue_name = _appliquer_ue(ue, academic_year, semestre)
            record_stat["ues_created" if ue["statut"] == "nouvelle" else "ues_updated"] += 1
            for element in ue["cours"]:
                _appliquer_cours(element, ue_name, academic_year, filiere, niveau, semestre)
                record_stat["courses_created" if element["statut"] == "nouveau" else "courses_updated"] += 1
        for retrait in analyse["retraits"]:
            if retrait["bloque"]:
                record_stat["courses_kept"] += 1
                continue
            resultat = grille.retirer_cours_de_classe(retrait["teaching_unit"], filiere, niveau, forcer=True)
            record_stat["courses_deleted"] += 1 if resultat["retire"] else 0
            record_stat["ues_deleted"] += 1 if resultat["ue_supprimee"] else 0
    except Exception:
        # Tout ou rien : l'ancienne version renvoyait {"status": False} sans
        # relancer, la requête était alors validée avec une grille partielle.
        frappe.db.rollback()
        frappe.log_error("teaching_grid import_grid", traceback.format_exc())
        raise

    return {"status": True, "data": record_stat, "analyse": analyse["stats"]}


@frappe.whitelist()
def export_grid(academic_year,faculty,filiere,niveau,semestre):
    """exporter au format excel la grille d'un semestre"""
    try:        
        grid_to_export = get_academic_teaching_unit(academic_year,faculty,filiere,niveau,semestre)
        exel_grid = []
        headers = [
                'Code UE', 'Code Cours', 'Intitulés', 'Crédits', 'TYPE', 
                'CM', 'TD', 'TP', 'TPE',"Total", 'Enseignant (CM)', 'Enseignant (TD)', 'Enseignant (TP)'
        ]
        exel_grid.append(headers)
        for ue in grid_to_export["grid"]:
            exel_grid.append([
                ue["ue_code"],"",ue["ue_title"],ue["ue_credits"],"UE","","","","","","",""
            ])
            for course in ue["courses"]:
                exel_grid.append([
                    "",course["code"],course["title"],course["credits"],course["type"],
                    course["nombre_dheure_cm"],course["nombre_dheure_td"],course["nombre_dheure_tp"],course["nombre_dheure_tpe"],course["total_hours"],
                    ", ".join([t["teacher"] for t in course["teacher"] if t["type_cours"]=="Cours Magistral (CM)"]),
                    ", ".join([t["teacher"] for t in course["teacher"] if t["type_cours"]=="Travaux Dirigés (TD)"]),
                    ", ".join([t["teacher"] for t in course["teacher"] if t["type_cours"]=="Travaux Pratique (TP)"])
                ])
        exel_grid.append([])
        exel_grid.append([])
        exel_grid.append([
            "Total UE",grid_to_export["stats"]["ue_count"],"","","","","","","","","","",""
        ])
        exel_grid.append([
            "Total Cours",grid_to_export["stats"]["course_count"],"","","","","","","","","","",""
        ])
        exel_grid.append([
            "Total Crédits",grid_to_export["stats"]["total_credits"],"","","","","","","","","","",""
        ])
        exel_grid.append([
            "Total Heures",grid_to_export["stats"]["total_hours"],"","","","","","","","","","",""
        ])
        
        # Créer le DataFrame
        df = pd.DataFrame(exel_grid)
        
        # Générer le nom du fichier
        filename = f"grille_{filiere}_{niveau}_{semestre}-{faculty}-{academic_year}.xlsx"
        file_path = get_site_path('public', 'files', 'templates', filename)
        
        # Créer le dossier s'il n'existe pas
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Sauvegarder le fichier
        df.to_excel(file_path, index=False, header=False)
        
        # Retourner l'URL
        return {
            'success': True,
            'file_url': f'/files/templates/{filename}'
        }
        
    except (frappe.PermissionError, frappe.ValidationError):
        raise
    except Exception as e:
        frappe.log_error("teaching_grid export_grid", traceback.format_exc())
        return {
            'success': False,
            'error': str(e)
        }


@frappe.whitelist()
def download_template():
    """Générer et télécharger un template Excel pour l'import"""
    try:        
        # Créer un template vide avec la structure attendue
        template_data = []
                
        headers = [
            'Code UE', 'Code Cours', 'Intitulés', 'Crédits', 'TYPE', 
            'CM', 'TD', 'TP', 'TPE', 'Enseignant (CM)', 'Enseignant (TD)', 'Enseignant (TP)'
        ]
        template_data.append(headers)
        
        # Exemple de ligne UE
        template_data.append([
            'IGL111', '', 'Outils Mathématiques I (exemple)', '6', 'UE',
            '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
        ])
        
        # Exemple de ligne cours
        template_data.append([
            '', 'IGL111a', 'Analyse Mathématiques I (exemple)', '3', 'ENS',
            '25', '15', '0', '40', 'Dr Paul Mbarga', 'Aline Fotso', 'jean.kamga@exemple.cm', 
        ])
        
        # Ligne vide pour séparer
        template_data.append([])
        
       
        
        # Instructions
        template_data.append([])
        template_data.append(['=== INSTRUCTIONS ===', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['1. Supprimez ces instructions avant import', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['2. Ne modifiez pas la structure des colonnes', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['3. Les codes UE doivent être dans la colonne A (ex: IGL111)', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['4. Les codes cours doivent être dans la colonne B (ex: IGL111a)', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['5. Les lignes UE doivent avoir TYPE = UE', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['6. Les lignes cours doivent avoir TYPE = ENS', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['7. Enseignants : nom (avec ou sans titre, dans n\'importe quel ordre) ou adresse e-mail. Un enseignant inconnu est ignoré : la case reste vide', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        template_data.append(['8. Plusieurs enseignants pour un même type (CM, TD, TP) : séparez-les par des virgules', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
        
        # Créer le DataFrame
        df = pd.DataFrame(template_data)
        
        # Générer le nom du fichier
        filename = f"teaching_grid_template.xlsx"
        file_path = get_site_path('public', 'files', 'templates', filename)
        
        # Créer le dossier s'il n'existe pas
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Sauvegarder le fichier
        df.to_excel(file_path, index=False, header=False)
        
        # Retourner l'URL
        return {
            'success': True,
            'file_url': f'/files/templates/{filename}'
        }
        
    except Exception as e:
        frappe.log_error(f"Erreur download_template: {str(e)}")
        # frappe.throw(e)
        return {
            'success': False,
            'error': str(e)
        }


# ====================================================================== #
#  Édition de la grille (codes et déplacements : voir api/grille_edition.py)
# ====================================================================== #
_CHAMPS_HEURES = ("nombre_dheure_cm", "nombre_dheure_td", "nombre_dheure_tp", "nombre_dheure_tpe")


def _classe_du_cours(teaching_unit, filiere, niveau):
    """Vérifie que le cours appartient à la classe et renvoie (doc, autres classes)."""
    from udshed.utils import grille

    if not frappe.db.exists("Teaching Unit", teaching_unit):
        frappe.throw(_("Cours introuvable."), frappe.DoesNotExistError)
    classes = grille.classes_du_cours(teaching_unit)
    if (filiere, str(niveau)) not in classes:
        frappe.throw(_("Ce cours n'appartient pas à la grille de cette classe."))
    autres = sorted(c for c in classes if c != (filiere, str(niveau)))
    return frappe.get_doc("Teaching Unit", teaching_unit), [f"{f} {grille.libelle_niveau(n)}" for f, n in autres]


def _nombre_positif(valeur, libelle, entier=False):
    try:
        nombre = float(str(valeur).replace(",", ".")) if valeur not in (None, "") else 0.0
    except ValueError:
        frappe.throw(_("{0} : valeur numérique attendue.").format(libelle))
    if nombre < 0:
        frappe.throw(_("{0} ne peut pas être négatif.").format(libelle))
    return int(round(nombre)) if entier else nombre


@frappe.whitelist()
def modifier_cours(teaching_unit, academic_year, faculty, filiere, niveau, semestre, valeurs, appliquer_au_tronc_commun=0):
    """Modifie un cours de la grille d'une classe.

    `valeurs` : intitule_cours, credits (crédits de CETTE classe), nombre_dheure_cm/td/tp/tpe.
    L'intitulé et les heures sont communs à toutes les classes d'un tronc commun :
    les modifier sur un cours partagé exige `appliquer_au_tronc_commun=1`.
    """
    from udshed.utils import grille

    planning_permission.assert_can_manage_grid(academic_year, faculty, filiere, niveau, semestre)
    valeurs = frappe.parse_json(valeurs) if isinstance(valeurs, str) else (valeurs or {})
    tu, autres = _classe_du_cours(teaching_unit, filiere, niveau)

    communs = {}
    if "intitule_cours" in valeurs:
        intitule = str(valeurs.get("intitule_cours") or "").strip()
        if not intitule:
            frappe.throw(_("L'intitulé ne peut pas être vide."))
        communs["intitule_cours"] = intitule
    for champ in _CHAMPS_HEURES:
        if champ in valeurs:
            communs[champ] = _nombre_positif(valeurs[champ], _("Heures"), entier=True)
    modifies = {k: v for k, v in communs.items() if tu.get(k) != v}
    if autres and modifies and not frappe.utils.cint(appliquer_au_tronc_commun):
        frappe.throw(
            _("Ce cours est partagé avec {0} : l'intitulé et les heures seront modifiés pour toutes ces classes.").format(
                ", ".join(autres)
            ),
            title=_("Cours de tronc commun"),
            exc=frappe.ValidationError,
        )
    for champ, valeur in modifies.items():
        tu.set(champ, valeur)

    ligne = next(r for r in tu.course_levels if r.filiere == filiere and str(r.niveau) == str(niveau))
    if "credits" in valeurs:
        ligne.course_poid = _nombre_positif(valeurs["credits"], _("Crédits"))
        if not autres:
            tu.credits = int(round(ligne.course_poid))
    tu.save(ignore_permissions=True)
    return {
        "teaching_unit": tu.name,
        "avertissement": grille.coherence_credits(ligne.course_poid, tu),
        "classes_partagees": autres,
    }


@frappe.whitelist()
def modifier_ue(ue_code, intitule, academic_year, faculty, filiere, niveau, semestre):
    """Renomme une UE (son code reste inchangé)."""
    planning_permission.assert_can_manage_grid(academic_year, faculty, filiere, niveau, semestre)
    intitule = str(intitule or "").strip()
    if not intitule:
        frappe.throw(_("L'intitulé de l'UE ne peut pas être vide."))
    nom = frappe.db.get_value("Teaching Unit Value", {"code": ue_code, "academic_year": academic_year}, "name")
    if not nom:
        frappe.throw(_("UE introuvable."), frappe.DoesNotExistError)
    frappe.db.set_value("Teaching Unit Value", nom, "intitule", intitule)
    return {"ue": nom}


@frappe.whitelist()
def lister_ues(academic_year, faculty, filiere, niveau, semestre):
    """UE de l'année (pour le choix de l'UE d'un nouveau cours)."""
    planning_permission.assert_can_manage_grid(academic_year, faculty, filiere, niveau, semestre)
    return frappe.get_all(
        "Teaching Unit Value",
        filters={"academic_year": academic_year, "code": ["!=", "UNKNOW"]},
        fields=["name", "code", "intitule", "semestre"],
        order_by="code asc",
    )


@frappe.whitelist()
def ajouter_cours(academic_year, faculty, filiere, niveau, semestre, code, credits, intitule_cours=None,
                  ue_code=None, ue_intitule=None, nombre_dheure_cm=0, nombre_dheure_td=0,
                  nombre_dheure_tp=0, nombre_dheure_tpe=0):
    """Ajoute un cours à la grille de la classe.

    - Si un cours de ce code existe déjà pour l'année, il est rattaché à la
      classe (tronc commun) avec ses propres crédits ; son contenu est conservé.
    - Sinon il est créé dans l'UE `ue_code` (créée si besoin avec `ue_intitule`).
    """
    from udshed.utils import grille

    planning_permission.assert_can_manage_grid(academic_year, faculty, filiere, niveau, semestre)
    code = str(code or "").strip()
    if not code:
        frappe.throw(_("Le code du cours est obligatoire."))
    poids = _nombre_positif(credits, _("Crédits"))

    existant = frappe.db.get_value("Teaching Unit", {"course": code, "academic_year": academic_year}, "name")
    if existant:
        tu = frappe.get_doc("Teaching Unit", existant)
        if (filiere, str(niveau)) in grille.classes_du_cours(existant):
            frappe.throw(_("Le cours {0} est déjà dans la grille de cette classe.").format(code))
        tu.append("course_levels", {"filiere": filiere, "niveau": niveau, "course_poid": poids})
        tu.save(ignore_permissions=True)
        return {"teaching_unit": tu.name, "rattache": True, "avertissement": grille.coherence_credits(poids, tu)}

    intitule = str(intitule_cours or "").strip()
    if not intitule:
        frappe.throw(_("L'intitulé du cours est obligatoire."))
    heures = {
        "nombre_dheure_cm": _nombre_positif(nombre_dheure_cm, "CM", entier=True),
        "nombre_dheure_td": _nombre_positif(nombre_dheure_td, "TD", entier=True),
        "nombre_dheure_tp": _nombre_positif(nombre_dheure_tp, "TP", entier=True),
        "nombre_dheure_tpe": _nombre_positif(nombre_dheure_tpe, "TPE", entier=True),
    }

    if frappe.db.get_value("Field of study", filiere, "has_uv_in_grid"):
        ue_code = str(ue_code or "").strip()
        if not ue_code:
            frappe.throw(_("Choisissez l'UE du cours."))
    else:
        ue_code = "UNKNOW"
    # UE existante réutilisée telle quelle ; sinon créée avec l'intitulé fourni.
    ue_name = frappe.db.get_value("Teaching Unit Value", {"code": ue_code, "academic_year": academic_year}, "name")
    if not ue_name:
        ue_name = _appliquer_ue(
            {"code": ue_code, "intitule": str(ue_intitule or "").strip() or ue_code}, academic_year, semestre
        )

    if not frappe.db.exists("Course", code):
        frappe.get_doc({"doctype": "Course", "code": code, "intitule": intitule, "semestre": semestre, **heures}).insert(
            ignore_permissions=True
        )
    tu = frappe.get_doc({
        "doctype": "Teaching Unit",
        "course": code,
        "academic_year": academic_year,
        "intitule_cours": intitule,
        "unite_de_valeur": ue_name,
        "semestre": semestre,
        "credits": int(round(poids)),
        **heures,
        "course_levels": [{"filiere": filiere, "niveau": niveau, "course_poid": poids}],
    }).insert(ignore_permissions=True)
    return {"teaching_unit": tu.name, "rattache": False, "avertissement": grille.coherence_credits(poids, tu)}


@frappe.whitelist()
def dependances_suppression(teaching_unit, academic_year, faculty, filiere, niveau, semestre):
    """Ce qui empêcherait de retirer le cours de la classe (affiché avant confirmation)."""
    from udshed.utils import grille

    planning_permission.assert_can_manage_grid(academic_year, faculty, filiere, niveau, semestre)
    _tu, autres = _classe_du_cours(teaching_unit, filiere, niveau)
    deps = grille.dependances_cours_classe(teaching_unit, filiere, niveau)
    return {"bloque": bool(deps), "dependances": grille.decrire_dependances(deps), "classes_partagees": autres}


@frappe.whitelist()
def supprimer_cours(teaching_unit, academic_year, faculty, filiere, niveau, semestre):
    """Retire le cours de la grille de la classe (refusé s'il a des données pour elle).

    Le cours est supprimé définitivement s'il n'appartient plus à aucune classe et
    n'est référencé nulle part ; son UE l'est aussi si elle devient vide.
    """
    from udshed.utils import grille

    planning_permission.assert_can_manage_grid(academic_year, faculty, filiere, niveau, semestre)
    _classe_du_cours(teaching_unit, filiere, niveau)
    return grille.retirer_cours_de_classe(teaching_unit, filiere, niveau)
