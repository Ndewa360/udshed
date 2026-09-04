import os
from PIL import Image, ImageDraw, ImageFont

OUT = r"/mnt/c/Users/Admin/Desktop/Diagramme_deploiement_Gestion_Notes_Evaluation.png"

W, H = 2100, 1500
IMG = Image.new("RGB", (W, H), "#ffffff")
D = ImageDraw.Draw(IMG)

def font(size, bold=False):
    paths = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        r"C:\Windows\Fonts\calibrib.ttf",
    ]
    if bold:
        paths = [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\calibrib.ttf"]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

F_TITLE = font(40, True)
F_NODE_H = font(24, True)
F_NODE = font(20)
F_SMALL = font(16)

def box(x, y, w, h, title, lines=(), fill="#eef4fa", edge="#1a5276", title_fill="#1a5276", dashed=False):
    D.rectangle([x, y, x + w, y + h], fill=fill, outline=edge, width=3 if not dashed else 2)
    if dashed:
        pass
    cw = D.textlength(title, font=F_NODE_H)
    D.text((x + (w - cw) / 2, y + 10), title, fill=title_fill, font=F_NODE_H)
    ty = y + 46
    for ln in lines:
        tl = D.textlength(ln, font=F_NODE)
        D.text((x + (w - tl) / 2, ty), ln, fill="#333333", font=F_NODE)
        ty += 26
    return (x, y, x + w, y + h)

def arrow(x1, y1, x2, y2, label=None, label_pos="mid"):
    D.line([x1, y1, x2, y2], fill="#555555", width=3)
    # arrowhead
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    ah = 12
    for a in (ang + math.radians(20), ang - math.radians(20)):
        D.line([x2, y2, x2 - ah * math.cos(a), y2 - ah * math.sin(a)], fill="#555555", width=3)
    if label:
        tl = D.textlength(label, font=F_SMALL)
        if label_pos == "mid":
            lx = (x1 + x2) / 2 - tl / 2
            ly = (y1 + y2) / 2 - 10
        else:
            lx = (x1 + x2) / 2 - tl / 2
            ly = (y1 + y2) / 2 + 4
        D.text((lx, ly), label, fill="#7f8c8d", font=F_SMALL)

# Title
D.text(((W - D.textlength("Diagramme de Déploiement — Gestion des Notes et Évaluation", font=F_TITLE)) / 2, 30),
       "Diagramme de Déploiement — Gestion des Notes et Évaluation", fill="#1a5276", font=F_TITLE)
D.text(((W - D.textlength("Module « Gestion Des Notes » — App udshed (Frappe) — UDSHED", font=F_NODE)) / 2, 82),
       "Module « Gestion Des Notes » — App udshed (Frappe) — UDSHED", fill="#555555", font=F_NODE)

# ---- Client nodes (top) ----
y_clients = 140
# Enseignant
cx1, cy1, cx1b, cy1b = box(60, y_clients, 300, 150, "👨‍🏫 Enseignant", [
    "Navigateur Web",
    "Saisie des notes (CC/Exam)",
    "API saisie_notes.py",
], fill="#fdf2e9", edge="#d35400", title_fill="#d35400")
# Scolarité / Coordonnateur
cx2 = 400
box(cx2, y_clients, 320, 150, "🗂 Scolarité / Coordonnateur", [
    "Navigateur Web (Desk)",
    "Validation, PV, relevés",
    "Évaluation & réinscriptions",
], fill="#eafaf1", edge="#27ae60", title_fill="#27ae60")
# Étudiant
cx3 = 760
box(cx3, y_clients, 300, 150, "🎓 Étudiant", [
    "Navigateur Web",
    "Consultation notes",
    "Babillard (www)",
], fill="#eaf2f8", edge="#2980b9", title_fill="#2980b9")

# ---- Web tier ----
y_web = 380
box(250, y_web, 1300, 120, "Couche Web (Internet / Réseau)", [
    "HTTPS :80/443  →  Reverse Proxy Nginx → Gunicorn (WSGI)",
], fill="#f4f6f7", edge="#5d6d7e")

# ---- Frappe application tier ----
y_app = 580
# App server node
box(250, y_app, 1300, 300, "Serveur d'application — Frappe Bench (app udshed)", [
    "Module « Gestion Des Notes » · site: site.local · port 8000",
    "",
    "API: saisie_notes · resultat_academique · resultats_page",
    "API: releve_notes · proces_verbal · transcript · retake",
    "Print (WeasyPrint): proces_verbal.html · releve_notes.html",
    "Doctypes: Session Examen · Session Examen Note · Resultat Academique",
    "Doctypes: Grade Formula · Grade Config · Teaching Unit · Note Item",
], fill="#eef4fa", edge="#1a5276", title_fill="#1a5276")

# ---- Data tier ----
y_data = 980
box(250, y_data, 420, 160, "Base de données", [
    "MariaDB / MySQL",
    "Tables : session_examen_note, resultat_academique…",
], fill="#fdecea", edge="#c0392b", title_fill="#c0392b")
box(820, y_data, 320, 160, "Caches & files", [
    "Redis (cache/queue)",
    "Sites / files (uploads)",
], fill="#fcf3cf", edge="#b7950b", title_fill="#b7950b")
box(1290, y_data, 260, 160, "Rendu PDF/IMG", [
    "WeasyPrint",
    "Cairo / fonts TNR",
], fill="#e8daef", edge="#7d3c98", title_fill="#7d3c98")

# ---- Arrows ----
# Clients -> web
arrow(cx1b, cy1b, 530, y_web, "HTTPS")
arrow(cx2 + 160, 290, 615, y_web, "HTTPS")
arrow(cx3 + 150, 290, 700, y_web, "HTTPS")
# web -> app
arrow(600, y_web + 120, 600, y_app, "HTTP → WSGI 8000")
# app -> data
arrow(600, y_app + 300, 460, y_data, "SQL (ORM)")
arrow(780, y_app + 300, 980, y_data, "Redis/Files")
arrow(1100, y_app + 300, 1420, y_data, "WeasyPrint")

IMG.save(OUT)
print("OK saved:", OUT, os.path.getsize(OUT), "bytes")
