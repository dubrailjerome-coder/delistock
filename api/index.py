#!/usr/bin/env python3
"""
DeliStock – Version Vercel + PostgreSQL + Google Vision OCR
"""
from flask import Flask, request, jsonify, send_from_directory
import os, json, psycopg2, psycopg2.extras
from datetime import datetime, date

app = Flask(__name__, static_folder='../static', template_folder='../templates')

# ─── CONFIG ────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")
GOOGLE_VISION_KEY = os.environ.get("GOOGLE_VISION_KEY", "")

# ─── DB ────────────────────────────────────────────────────
def db():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    conn.autocommit = False
    return conn

def rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

def row(cur):
    cols = [d[0] for d in cur.description]
    r = cur.fetchone()
    return dict(zip(cols, r)) if r else None

# ─── INIT DB ───────────────────────────────────────────────
def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS fournisseurs (
        id SERIAL PRIMARY KEY,
        nom TEXT NOT NULL,
        type TEXT DEFAULT 'magasin',
        url TEXT, adresse TEXT, telephone TEXT, email TEXT, notes TEXT,
        cree_le TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS categories (
        id SERIAL PRIMARY KEY,
        nom TEXT NOT NULL UNIQUE,
        couleur TEXT DEFAULT '#1A5FA8'
    );
    CREATE TABLE IF NOT EXISTS ingredients (
        id SERIAL PRIMARY KEY,
        nom TEXT NOT NULL, marque TEXT,
        categorie_id INTEGER REFERENCES categories(id),
        unite TEXT DEFAULT 'g',
        stock_actuel REAL DEFAULT 0,
        stock_minimum REAL DEFAULT 0,
        prix_achat_actuel REAL DEFAULT 0,
        fournisseur_habituel_id INTEGER REFERENCES fournisseurs(id),
        emplacement TEXT, conditionnement TEXT,
        actif INTEGER DEFAULT 1, notes TEXT,
        cree_le TIMESTAMP DEFAULT NOW(),
        modifie_le TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS lots (
        id SERIAL PRIMARY KEY,
        ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
        numero_lot TEXT, date_achat TEXT NOT NULL,
        date_peremption TEXT,
        quantite_achetee REAL NOT NULL, quantite_restante REAL NOT NULL,
        prix_unitaire REAL NOT NULL, prix_total REAL,
        fournisseur_id INTEGER REFERENCES fournisseurs(id),
        facture_ref TEXT, notes TEXT,
        cree_le TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS mouvements_stock (
        id SERIAL PRIMARY KEY,
        ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
        lot_id INTEGER REFERENCES lots(id),
        type_mouvement TEXT NOT NULL,
        quantite REAL NOT NULL, stock_avant REAL, stock_apres REAL,
        motif TEXT, production_id INTEGER,
        date_mouvement TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS recettes (
        id SERIAL PRIMARY KEY,
        nom TEXT NOT NULL, description TEXT,
        nb_portions INTEGER DEFAULT 1,
        temps_preparation_min INTEGER, temps_cuisson_min INTEGER,
        categorie TEXT, actif INTEGER DEFAULT 1,
        cree_le TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS recette_ingredients (
        id SERIAL PRIMARY KEY,
        recette_id INTEGER NOT NULL REFERENCES recettes(id) ON DELETE CASCADE,
        ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
        quantite REAL NOT NULL, unite TEXT, notes TEXT
    );
    CREATE TABLE IF NOT EXISTS productions (
        id SERIAL PRIMARY KEY,
        recette_id INTEGER NOT NULL REFERENCES recettes(id),
        nb_lots_produits INTEGER DEFAULT 1,
        date_production TIMESTAMP DEFAULT NOW(),
        notes TEXT, cout_reel REAL
    );
    CREATE TABLE IF NOT EXISTS alertes (
        id SERIAL PRIMARY KEY,
        type_alerte TEXT NOT NULL,
        ingredient_id INTEGER REFERENCES ingredients(id),
        lot_id INTEGER REFERENCES lots(id),
        message TEXT NOT NULL, lue INTEGER DEFAULT 0,
        cree_le TIMESTAMP DEFAULT NOW()
    );
    """)

    # Données initiales si vide
    cur.execute("SELECT COUNT(*) FROM categories")
    if cur.fetchone()[0] == 0:
        cur.executemany("INSERT INTO categories (nom, couleur) VALUES (%s, %s)", [
            ("Chocolat","#7C3AED"),("Farine & poudres","#D97706"),
            ("Sucres","#10B981"),("Matières grasses","#F59E0B"),
            ("Fruits secs","#EF4444"),("Oeufs & laitiers","#3B82F6"),
            ("Levants","#8B5CF6"),("Sirops & gélatines","#EC4899"),
        ])
        cur.executemany("INSERT INTO fournisseurs (nom,type,adresse) VALUES (%s,%s,%s)", [
            ("Valrhona Pro Shop","site_internet","valrhona.com"),
            ("Métro Cash & Carry","grossiste","Paris 13e"),
            ("G. Detou Paris","magasin","58 Rue Tiquetonne, Paris 2e"),
            ("Épicerie Orient","magasin","Paris 11e"),
            ("Lidl","magasin","Paris"),
        ])

    conn.commit()
    cur.close()
    conn.close()

def generer_alertes():
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM alertes WHERE lue=0")
    cur.execute("""
        SELECT id,nom,stock_actuel,stock_minimum,unite FROM ingredients
        WHERE actif=1 AND stock_actuel<=stock_minimum AND stock_minimum>0
    """)
    for i in rows(cur):
        t = "rupture" if i["stock_actuel"] <= 0 else "stock_faible"
        cur.execute("INSERT INTO alertes (type_alerte,ingredient_id,message) VALUES (%s,%s,%s)",
            (t, i["id"], f"{'🔴' if t=='rupture' else '⚠️'} {i['nom']} : {i['stock_actuel']:.0f}{i['unite']} (min. {i['stock_minimum']:.0f}{i['unite']})"))
    cur.execute("""
        SELECT l.id, i.nom, i.id iid, l.numero_lot, l.date_peremption,
               (TO_DATE(l.date_peremption,'YYYY-MM-DD') - CURRENT_DATE) AS jours
        FROM lots l JOIN ingredients i ON i.id=l.ingredient_id
        WHERE l.quantite_restante>0 AND l.date_peremption IS NOT NULL
          AND TO_DATE(l.date_peremption,'YYYY-MM-DD') - CURRENT_DATE <= 30
    """)
    for d in rows(cur):
        cur.execute("INSERT INTO alertes (type_alerte,ingredient_id,lot_id,message) VALUES (%s,%s,%s,%s)",
            ("dlc_proche", d["iid"], d["id"],
             f"🗓️ {d['nom']} – lot {d['numero_lot'] or 'N/A'} : expire le {d['date_peremption']} ({d['jours']}j)"))
    conn.commit()
    cur.close()
    conn.close()

# ─── ROUTES PRINCIPALES ────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory('../templates', 'index.html')

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory('../static', filename)

@app.route("/api/dashboard")
def dashboard():
    conn = db(); cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) total,
               SUM(CASE WHEN stock_actuel<=0 THEN 1 ELSE 0 END) ruptures,
               SUM(CASE WHEN stock_actuel>0 AND stock_actuel<=stock_minimum THEN 1 ELSE 0 END) critiques,
               ROUND(CAST(SUM(stock_actuel*prix_achat_actuel/1000.0) AS numeric),2) valeur
        FROM ingredients WHERE actif=1
    """)
    s = row(cur)
    cur.execute("""
        SELECT i.nom, l.date_peremption,
               (TO_DATE(l.date_peremption,'YYYY-MM-DD') - CURRENT_DATE) AS jours,
               l.quantite_restante, i.unite
        FROM lots l JOIN ingredients i ON i.id=l.ingredient_id
        WHERE l.quantite_restante>0 AND l.date_peremption IS NOT NULL
          AND TO_DATE(l.date_peremption,'YYYY-MM-DD') - CURRENT_DATE <= 30
        ORDER BY l.date_peremption
    """)
    alertes_dlc = rows(cur)
    cur.execute("SELECT nom,stock_actuel,stock_minimum,unite FROM ingredients WHERE actif=1 AND stock_actuel<=stock_minimum ORDER BY stock_actuel/NULLIF(stock_minimum,0)")
    stocks_crit = rows(cur)
    cur.execute("""
        SELECT i.nom, l.date_achat, l.prix_unitaire, l.prix_total, f.nom fournisseur
        FROM lots l JOIN ingredients i ON i.id=l.ingredient_id
        LEFT JOIN fournisseurs f ON f.id=l.fournisseur_id
        ORDER BY l.date_achat DESC LIMIT 6
    """)
    derniers = rows(cur)
    cur.close(); conn.close()
    return jsonify(stats=s, alertes_dlc=alertes_dlc, stocks_critiques=stocks_crit, derniers_achats=derniers)

@app.route("/api/ingredients", methods=["GET"])
def get_ingredients():
    conn = db(); cur = conn.cursor()
    cur.execute("""
        SELECT i.*, c.nom categorie, c.couleur, f.nom fournisseur_nom
        FROM ingredients i
        LEFT JOIN categories c ON c.id=i.categorie_id
        LEFT JOIN fournisseurs f ON f.id=i.fournisseur_habituel_id
        WHERE i.actif=1 ORDER BY c.nom, i.nom
    """)
    data = rows(cur); cur.close(); conn.close()
    return jsonify(data)

@app.route("/api/ingredients", methods=["POST"])
def add_ingredient():
    d = request.json; conn = db(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO ingredients (nom,marque,categorie_id,unite,stock_actuel,stock_minimum,
        prix_achat_actuel,fournisseur_habituel_id,emplacement,conditionnement,notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (d.get("nom"),d.get("marque"),d.get("categorie_id"),d.get("unite","g"),
          d.get("stock_actuel",0),d.get("stock_minimum",0),d.get("prix_achat_actuel",0),
          d.get("fournisseur_habituel_id"),d.get("emplacement"),d.get("conditionnement"),d.get("notes")))
    nid = cur.fetchone()[0]
    if d.get("stock_actuel", 0) > 0:
        cur.execute("INSERT INTO mouvements_stock (ingredient_id,type_mouvement,quantite,stock_avant,stock_apres,motif) VALUES (%s,%s,%s,0,%s,%s)",
                    (nid,"entree",d["stock_actuel"],d["stock_actuel"],"Stock initial"))
    conn.commit(); cur.close(); conn.close()
    generer_alertes()
    return jsonify({"ok": True, "id": nid})

@app.route("/api/ingredients/<int:iid>", methods=["PUT"])
def update_ingredient(iid):
    d = request.json; conn = db(); cur = conn.cursor()
    cur.execute("SELECT stock_actuel FROM ingredients WHERE id=%s", (iid,))
    avant = cur.fetchone()
    cur.execute("""
        UPDATE ingredients SET nom=%s,marque=%s,categorie_id=%s,unite=%s,stock_actuel=%s,
        stock_minimum=%s,prix_achat_actuel=%s,fournisseur_habituel_id=%s,
        emplacement=%s,conditionnement=%s,notes=%s,modifie_le=NOW() WHERE id=%s
    """, (d.get("nom"),d.get("marque"),d.get("categorie_id"),d.get("unite","g"),
          d.get("stock_actuel",0),d.get("stock_minimum",0),d.get("prix_achat_actuel",0),
          d.get("fournisseur_habituel_id"),d.get("emplacement"),d.get("conditionnement"),
          d.get("notes"),iid))
    if avant and avant[0] != d.get("stock_actuel"):
        diff = abs(d["stock_actuel"] - avant[0])
        cur.execute("INSERT INTO mouvements_stock (ingredient_id,type_mouvement,quantite,stock_avant,stock_apres,motif) VALUES (%s,%s,%s,%s,%s,%s)",
                    (iid,"ajustement",diff,avant[0],d["stock_actuel"],"Modification manuelle"))
    conn.commit(); cur.close(); conn.close()
    generer_alertes()
    return jsonify({"ok": True})

@app.route("/api/ingredients/<int:iid>", methods=["DELETE"])
def delete_ingredient(iid):
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE ingredients SET actif=0 WHERE id=%s", (iid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/api/lots", methods=["GET"])
def get_lots():
    conn = db(); cur = conn.cursor()
    cur.execute("""
        SELECT l.*, i.nom ingredient_nom, i.unite, f.nom fournisseur_nom,
               (TO_DATE(l.date_peremption,'YYYY-MM-DD') - CURRENT_DATE) AS jours_dlc
        FROM lots l JOIN ingredients i ON i.id=l.ingredient_id
        LEFT JOIN fournisseurs f ON f.id=l.fournisseur_id
        ORDER BY l.date_achat DESC
    """)
    data = rows(cur); cur.close(); conn.close()
    return jsonify(data)

@app.route("/api/lots", methods=["POST"])
def add_lot():
    d = request.json; conn = db(); cur = conn.cursor()
    prix_total = round(float(d["prix_unitaire"]) * float(d["quantite_achetee"]), 2)
    cur.execute("""
        INSERT INTO lots (ingredient_id,numero_lot,date_achat,date_peremption,
        quantite_achetee,quantite_restante,prix_unitaire,prix_total,fournisseur_id,facture_ref,notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (d["ingredient_id"],d.get("numero_lot"),d["date_achat"],d.get("date_peremption"),
          d["quantite_achetee"],d["quantite_achetee"],d["prix_unitaire"],prix_total,
          d.get("fournisseur_id"),d.get("facture_ref"),d.get("notes")))
    lid = cur.fetchone()[0]
    cur.execute("SELECT stock_actuel FROM ingredients WHERE id=%s", (d["ingredient_id"],))
    avant = cur.fetchone()[0] or 0
    ns = avant + float(d["quantite_achetee"])
    cur.execute("UPDATE ingredients SET stock_actuel=%s,prix_achat_actuel=%s,modifie_le=NOW() WHERE id=%s",
                (ns, d["prix_unitaire"], d["ingredient_id"]))
    cur.execute("INSERT INTO mouvements_stock (ingredient_id,lot_id,type_mouvement,quantite,stock_avant,stock_apres,motif) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (d["ingredient_id"],lid,"entree",d["quantite_achetee"],avant,ns,f"Achat – {d.get('facture_ref','')}"))
    conn.commit(); cur.close(); conn.close()
    generer_alertes()
    return jsonify({"ok": True, "id": lid})

@app.route("/api/fournisseurs", methods=["GET"])
def get_fournisseurs():
    conn = db(); cur = conn.cursor()
    cur.execute("""
        SELECT f.*, COUNT(DISTINCT l.ingredient_id) nb_ingredients,
               COUNT(l.id) nb_achats,
               ROUND(CAST(SUM(l.prix_total) AS numeric),2) total_achats,
               MAX(l.date_achat) dernier_achat
        FROM fournisseurs f LEFT JOIN lots l ON l.fournisseur_id=f.id
        GROUP BY f.id ORDER BY f.nom
    """)
    data = rows(cur); cur.close(); conn.close()
    return jsonify(data)

@app.route("/api/fournisseurs", methods=["POST"])
def add_fournisseur():
    d = request.json; conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO fournisseurs (nom,type,url,adresse,telephone,email,notes) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (d.get("nom"),d.get("type","magasin"),d.get("url"),d.get("adresse"),d.get("telephone"),d.get("email"),d.get("notes")))
    nid = cur.fetchone()[0]; conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True, "id": nid})

@app.route("/api/fournisseurs/<int:fid>", methods=["PUT"])
def update_fournisseur(fid):
    d = request.json; conn = db(); cur = conn.cursor()
    cur.execute("UPDATE fournisseurs SET nom=%s,type=%s,url=%s,adresse=%s,telephone=%s,email=%s,notes=%s WHERE id=%s",
                (d.get("nom"),d.get("type"),d.get("url"),d.get("adresse"),d.get("telephone"),d.get("email"),d.get("notes"),fid))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/api/fournisseurs/<int:fid>", methods=["DELETE"])
def delete_fournisseur(fid):
    conn = db(); cur = conn.cursor()
    cur.execute("DELETE FROM fournisseurs WHERE id=%s", (fid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/api/categories")
def get_categories():
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM categories ORDER BY nom")
    data = rows(cur); cur.close(); conn.close()
    return jsonify(data)

@app.route("/api/recettes", methods=["GET"])
def get_recettes():
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM recettes WHERE actif=1 ORDER BY nom")
    rl = rows(cur)
    for r in rl:
        cur.execute("""
            SELECT ri.*, i.nom ingredient_nom, i.stock_actuel, i.unite, i.prix_achat_actuel,
                   CASE WHEN i.stock_actuel >= ri.quantite THEN 1 ELSE 0 END stock_ok
            FROM recette_ingredients ri JOIN ingredients i ON i.id=ri.ingredient_id
            WHERE ri.recette_id=%s
        """, (r["id"],))
        r["ingredients"] = rows(cur)
        r["stock_ok"] = all(ing["stock_ok"] for ing in r["ingredients"])
        r["cout_total"] = round(sum(ing["quantite"] * ing["prix_achat_actuel"] / 1000.0 for ing in r["ingredients"]), 2)
    cur.close(); conn.close()
    return jsonify(rl)

@app.route("/api/recettes", methods=["POST"])
def add_recette():
    d = request.json; ings = d.pop("ingredients", []); conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO recettes (nom,description,nb_portions,temps_preparation_min,temps_cuisson_min,categorie) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (d.get("nom"),d.get("description"),d.get("nb_portions",1),d.get("temps_preparation_min"),d.get("temps_cuisson_min"),d.get("categorie")))
    rid = cur.fetchone()[0]
    for ing in ings:
        cur.execute("INSERT INTO recette_ingredients (recette_id,ingredient_id,quantite,unite,notes) VALUES (%s,%s,%s,%s,%s)",
                    (rid,ing["ingredient_id"],ing["quantite"],ing.get("unite"),ing.get("notes")))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True, "id": rid})

@app.route("/api/recettes/<int:rid>", methods=["DELETE"])
def delete_recette(rid):
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE recettes SET actif=0 WHERE id=%s", (rid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/api/productions", methods=["POST"])
def lancer_production():
    d = request.json; rid = d["recette_id"]; nb = d.get("nb_lots", 1)
    conn = db(); cur = conn.cursor()
    cur.execute("""
        SELECT ri.ingredient_id, ri.quantite, i.nom, i.stock_actuel, i.unite, i.prix_achat_actuel
        FROM recette_ingredients ri JOIN ingredients i ON i.id=ri.ingredient_id WHERE ri.recette_id=%s
    """, (rid,))
    ings = rows(cur)
    for ing in ings:
        if ing["stock_actuel"] < ing["quantite"] * nb:
            cur.close(); conn.close()
            return jsonify({"ok": False, "erreur": f"Stock insuffisant : {ing['nom']}"})
    cout = sum(ing["quantite"] * nb * ing["prix_achat_actuel"] / 1000.0 for ing in ings)
    cur.execute("INSERT INTO productions (recette_id,nb_lots_produits,notes,cout_reel) VALUES (%s,%s,%s,%s) RETURNING id",
                (rid, nb, d.get("notes"), round(cout,2)))
    pid = cur.fetchone()[0]
    for ing in ings:
        besoin = ing["quantite"] * nb; ns = ing["stock_actuel"] - besoin
        cur.execute("UPDATE ingredients SET stock_actuel=%s,modifie_le=NOW() WHERE id=%s", (ns, ing["ingredient_id"]))
        cur.execute("INSERT INTO mouvements_stock (ingredient_id,type_mouvement,quantite,stock_avant,stock_apres,motif,production_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (ing["ingredient_id"],"sortie",besoin,ing["stock_actuel"],ns,f"Production #{pid} (x{nb})",pid))
    conn.commit(); cur.close(); conn.close()
    generer_alertes()
    return jsonify({"ok": True, "production_id": pid, "cout": round(cout,2)})

@app.route("/api/historique")
def historique():
    conn = db(); cur = conn.cursor()
    cur.execute("""
        SELECT l.*, i.nom ingredient_nom, i.unite, f.nom fournisseur_nom
        FROM lots l JOIN ingredients i ON i.id=l.ingredient_id
        LEFT JOIN fournisseurs f ON f.id=l.fournisseur_id
        ORDER BY l.date_achat DESC
    """)
    data = rows(cur); cur.close(); conn.close()
    return jsonify(data)

@app.route("/api/dlc")
def get_dlc():
    conn = db(); cur = conn.cursor()
    cur.execute("""
        SELECT l.*, i.nom ingredient_nom, i.marque, i.unite, f.nom fournisseur_nom,
               (TO_DATE(l.date_peremption,'YYYY-MM-DD') - CURRENT_DATE) AS jours_restants
        FROM lots l JOIN ingredients i ON i.id=l.ingredient_id
        LEFT JOIN fournisseurs f ON f.id=l.fournisseur_id
        WHERE l.quantite_restante>0 AND l.date_peremption IS NOT NULL
        ORDER BY l.date_peremption ASC
    """)
    data = rows(cur); cur.close(); conn.close()
    return jsonify(data)

@app.route("/api/alertes")
def get_alertes():
    conn = db(); cur = conn.cursor()
    cur.execute("""
        SELECT a.*, i.nom ingredient_nom FROM alertes a
        LEFT JOIN ingredients i ON i.id=a.ingredient_id
        WHERE a.lue=0 ORDER BY a.cree_le DESC
    """)
    data = rows(cur); cur.close(); conn.close()
    return jsonify(data)

@app.route("/api/alertes/<int:aid>/lue", methods=["POST"])
def marquer_lue(aid):
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE alertes SET lue=1 WHERE id=%s", (aid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/api/stats/general")
def stats_general():
    conn = db(); cur = conn.cursor()
    cur.execute("""
        SELECT c.nom categorie, c.couleur,
               COUNT(i.id) nb,
               ROUND(CAST(SUM(i.stock_actuel*i.prix_achat_actuel/1000.0) AS numeric),2) valeur
        FROM ingredients i JOIN categories c ON c.id=i.categorie_id
        WHERE i.actif=1 GROUP BY c.id, c.nom, c.couleur ORDER BY valeur DESC
    """)
    par_cat = rows(cur)
    cur.execute("""
        SELECT f.nom, f.type, ROUND(CAST(SUM(l.prix_total) AS numeric),2) total, COUNT(l.id) nb_achats
        FROM lots l JOIN fournisseurs f ON f.id=l.fournisseur_id
        GROUP BY f.id, f.nom, f.type ORDER BY total DESC
    """)
    par_fourn = rows(cur)
    cur.execute("""
        SELECT m.*, i.nom ingredient_nom FROM mouvements_stock m
        JOIN ingredients i ON i.id=m.ingredient_id
        ORDER BY m.date_mouvement DESC LIMIT 15
    """)
    mouvs = rows(cur)
    cur.close(); conn.close()
    return jsonify(par_categorie=par_cat, par_fournisseur=par_fourn, mouvements=mouvs)

# ═══════════════════════════════════════════════════════════
# OCR GOOGLE VISION – SCAN TICKET GRATUIT (1000/mois)
# ═══════════════════════════════════════════════════════════
@app.route("/api/ocr/google", methods=["POST"])
def ocr_google():
    import requests as req, base64, re, difflib

    if not GOOGLE_VISION_KEY:
        return jsonify({"ok": False, "erreur": "Clé Google Vision manquante dans les variables d'environnement Vercel"})

    data = request.json
    image_b64 = data.get("image")
    if not image_b64:
        return jsonify({"ok": False, "erreur": "Aucune image reçue"})

    # Appel Google Vision API
    vision_url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_KEY}"
    payload = {
        "requests": [{
            "image": {"content": image_b64},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}]
        }]
    }

    try:
        resp = req.post(vision_url, json=payload, timeout=15)
        result = resp.json()
        if "error" in result:
            return jsonify({"ok": False, "erreur": result["error"].get("message","Erreur Google Vision")})
        texte = result["responses"][0].get("fullTextAnnotation", {}).get("text", "")
        if not texte:
            return jsonify({"ok": False, "erreur": "Aucun texte détecté dans l'image"})
    except Exception as e:
        return jsonify({"ok": False, "erreur": f"Erreur connexion Google Vision : {str(e)}"})

    # Récupérer les ingrédients connus
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT id, nom, marque, unite, prix_achat_actuel FROM ingredients WHERE actif=1")
    ings_connus = rows(cur); cur.close(); conn.close()

    # Parser le texte
    lignes_ticket = [l.strip() for l in texte.split('\n') if l.strip() and len(l.strip()) > 2]
    prix_pattern = re.compile(r'(\d+[,\.]\d{2})\s*€?')
    qte_pattern  = re.compile(r'(\d+(?:[,\.]\d+)?)\s*(kg|g|l|ml|pcs|x)\b', re.IGNORECASE)
    date_pattern = re.compile(r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})')

    fournisseur_detecte = ""
    date_detecte = None
    for ligne in lignes_ticket[:6]:
        if not fournisseur_detecte and any(c.isalpha() for c in ligne) and len(ligne) > 3:
            fournisseur_detecte = ligne
        m = date_pattern.search(ligne)
        if m and not date_detecte:
            j, mo, an = m.group(1), m.group(2), m.group(3)
            if len(an) == 2: an = "20" + an
            try: date_detecte = f"{an}-{mo.zfill(2)}-{j.zfill(2)}"
            except: pass

    # Mots-clés pour matching
    mots_cles_ings = {}
    for ing in ings_connus:
        mots = [m for m in ing['nom'].lower().split() if len(m) > 3]
        if ing.get('marque'):
            mots += [m for m in ing['marque'].lower().split() if len(m) > 3]
        for mot in mots:
            mots_cles_ings.setdefault(mot, []).append(ing)
    noms_ings = [i['nom'].lower() for i in ings_connus]

    lignes_result = []
    total_detecte = None

    for ligne_txt in lignes_ticket:
        ligne_lower = ligne_txt.lower()
        prix_matches = prix_pattern.findall(ligne_txt)
        if not prix_matches: continue
        prix = float(prix_matches[-1].replace(',', '.'))
        if prix <= 0 or len(ligne_txt) < 4: continue

        # Détecter total
        if any(w in ligne_lower for w in ['total', 'ttc', 'montant']):
            total_detecte = prix
            continue

        qte_match = qte_pattern.search(ligne_txt)
        quantite = float(qte_match.group(1).replace(',','.')) if qte_match else 1
        unite_txt = qte_match.group(2).lower() if qte_match else 'pcs'
        if unite_txt == 'kg': quantite *= 1000; unite_txt = 'g'
        if unite_txt == 'l': quantite *= 1000; unite_txt = 'mL'

        # Matching ingrédient
        ing_trouve = None; score_max = 0
        for mot, ings in mots_cles_ings.items():
            if mot in ligne_lower:
                for ing in ings:
                    score = len(mot) / max(len(ing['nom']), 1)
                    if score > score_max:
                        score_max = score; ing_trouve = ing
        if not ing_trouve:
            matches = difflib.get_close_matches(ligne_lower, noms_ings, n=1, cutoff=0.45)
            if matches:
                ing_trouve = next((i for i in ings_connus if i['nom'].lower() == matches[0]), None)

        lignes_result.append({
            "nom_detecte": ligne_txt,
            "nom_normalise": ing_trouve['nom'] if ing_trouve else ligne_txt,
            "ingredient_id": ing_trouve['id'] if ing_trouve else None,
            "quantite": quantite,
            "unite": unite_txt,
            "prix_unitaire": prix,
            "prix_total_ligne": prix,
            "correspond": ing_trouve is not None
        })

    return jsonify({
        "ok": True,
        "methode": "google_vision",
        "resultat": {
            "fournisseur": fournisseur_detecte,
            "date": date_detecte,
            "reference_facture": None,
            "total_facture": total_detecte,
            "lignes": lignes_result,
            "texte_brut": texte
        }
    })

@app.route("/api/ocr/confirmer", methods=["POST"])
def ocr_confirmer():
    d = request.json; lignes = d.get("lignes", [])
    fournisseur_nom = d.get("fournisseur","")
    date_achat = d.get("date") or date.today().isoformat()
    ref_facture = d.get("reference_facture","")
    conn = db(); cur = conn.cursor()

    fournisseur_id = None
    if fournisseur_nom:
        cur.execute("SELECT id FROM fournisseurs WHERE LOWER(nom) LIKE %s LIMIT 1", (f"%{fournisseur_nom.lower()}%",))
        r = cur.fetchone()
        if r: fournisseur_id = r[0]
        else:
            cur.execute("INSERT INTO fournisseurs (nom,type) VALUES (%s,'magasin') RETURNING id", (fournisseur_nom,))
            fournisseur_id = cur.fetchone()[0]

    importes = []; erreurs = []
    for ligne in lignes:
        if not ligne.get("valide", True): continue
        ing_id = ligne.get("ingredient_id")
        if not ing_id: erreurs.append(f"Non trouvé : {ligne.get('nom_detecte')}"); continue
        qte = float(ligne.get("quantite") or 0); prix = float(ligne.get("prix_unitaire") or 0)
        if qte <= 0 or prix <= 0: continue
        cur.execute("INSERT INTO lots (ingredient_id,date_achat,date_peremption,quantite_achetee,quantite_restante,prix_unitaire,prix_total,fournisseur_id,facture_ref,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (ing_id,date_achat,ligne.get("date_peremption"),qte,qte,prix,
                     ligne.get("prix_total_ligne") or round(qte*prix/1000,2),
                     fournisseur_id,ref_facture,f"OCR – {ligne.get('nom_detecte')}"))
        lid = cur.fetchone()[0]
        cur.execute("SELECT stock_actuel FROM ingredients WHERE id=%s", (ing_id,))
        avant = cur.fetchone()[0] or 0; ns = avant + qte
        cur.execute("UPDATE ingredients SET stock_actuel=%s,prix_achat_actuel=%s,modifie_le=NOW() WHERE id=%s", (ns,prix,ing_id))
        cur.execute("INSERT INTO mouvements_stock (ingredient_id,lot_id,type_mouvement,quantite,stock_avant,stock_apres,motif) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (ing_id,lid,"entree",qte,avant,ns,f"OCR – {ref_facture or fournisseur_nom}"))
        importes.append(ligne.get("nom_normalise"))

    conn.commit(); cur.close(); conn.close()
    generer_alertes()
    return jsonify({"ok": True, "importes": importes, "erreurs": erreurs, "nb_importes": len(importes)})

# ─── INIT AU DÉMARRAGE ─────────────────────────────────────
try:
    if DATABASE_URL:
        init_db()
        generer_alertes()
except Exception as e:
    print(f"Init DB error: {e}")

if __name__ == "__main__":
    init_db(); generer_alertes()
    print("\n🍰 DeliStock Vercel – http://localhost:5000")
    app.run(host='0.0.0.0', debug=False, port=5000)
