"""
Couche d'accès aux données de la plateforme GRC.

Base de données : SQLite (fichier db/grc.db), créée et amorcée (seed)
automatiquement au premier lancement à partir des fichiers JSON du dossier
`data/` (extraits des classeurs Excel transmis par l'utilisateur).
"""
import json
import os
from datetime import date

from grc_core import dbengine
from grc_core.dbengine import get_connection, backend  # noqa: F401 (ré-exportés pour compat)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = dbengine.SQLITE_DB_PATH  # conservé pour compat (utilisé uniquement en mode SQLite)
DATA_DIR = os.path.join(BASE_DIR, "data")

# Échelle de maturité CMMI utilisée par le questionnaire PSSI-ES.
# (reprise telle quelle du modèle Excel transmis)
NIVEAUX_MATURITE = [
    ("AUCUN", 0, "Non conforme"),
    ("INITIAL", 1, "Héroïque"),
    ("GERE", 2, "Partielle"),
    ("DEFINI", 3, "Partielle"),
    ("QUANTIFIE", 4, "Totale"),
    ("OPTIMISE", 5, "Totale"),
]
NIVEAU_TO_POIDS = {n: p for n, p, _ in NIVEAUX_MATURITE}
NIVEAU_TO_CONFORMITE = {n: c for n, _, c in NIVEAUX_MATURITE}
POIDS_TO_NIVEAU = {p: n for n, p, _ in NIVEAUX_MATURITE}

# Intitulés des 11 chapitres PSSI-ES avec une casse et une accentuation correctes
# (le classeur Excel source les stocke en majuscules non accentuées ; ces libellés
# reprennent la formulation telle qu'utilisée dans les rapports ANAQ-Sup / COUD).
CHAPITRE_NOMS = {
    1: "Politique d'organisation de la sécurité des systèmes d'information de l'État du Sénégal",
    2: "Sécurité du personnel",
    3: "Acquisition et développement des systèmes d'information de l'État du Sénégal",
    4: "Gestion des actifs",
    5: "Relation avec les fournisseurs",
    6: "Sécurité physique",
    7: "Sécurité logique",
    8: "Sécurité de l'exploitation",
    9: "Cloud computing, appareils mobiles et télétravail",
    10: "Gestion des incidents",
    11: "Audit et conformité",
}


def nom_chapitre_affichage(chapitre_num, fallback=None):
    return CHAPITRE_NOMS.get(chapitre_num, (fallback or "").title())

# Échelles ISO/IEC 27005 (reprises du classeur "Framework_Appreciation_Risques_ISO27005.xlsx")
ECHELLE_DICT = {
    1: "Minime", 2: "Nécessaire", 3: "Critique / Essentielle / Confidentiel", 4: "Vital / Prouvée / Secret / Opposable",
}
ECHELLE_GRAVITE = {1: "Négligeable", 2: "Limitée", 3: "Importante", 4: "Critique"}
ECHELLE_VRAISEMBLANCE = {1: "Très peu probable", 2: "Peu probable", 3: "Probable", 4: "Très probable"}
SEUIL_APPETENCE = 8  # niveau de risque résiduel max accepté sans validation de la Direction


def niveau_risque_qualitatif(score):
    if score is None:
        return None
    if score <= 4:
        return "Faible"
    if score <= 8:
        return "Modéré"
    if score <= 12:
        return "Majeur"
    return "Critique"


SCHEMA = """
CREATE TABLE IF NOT EXISTS utilisateurs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identifiant TEXT NOT NULL UNIQUE,
    nom_complet TEXT,
    mot_de_passe_hash TEXT NOT NULL,
    sel TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'lecture_seule',
    actif INTEGER NOT NULL DEFAULT 1,
    doit_changer_mdp INTEGER NOT NULL DEFAULT 0,
    date_creation TEXT,
    derniere_connexion TEXT
);

CREATE TABLE IF NOT EXISTS journal_activite (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    horodatage TEXT NOT NULL,
    utilisateur TEXT,
    action TEXT NOT NULL,
    details TEXT
);

CREATE TABLE IF NOT EXISTS pssi_referentiel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapitre_num INTEGER NOT NULL,
    chapitre_nom TEXT NOT NULL,
    objectif_num INTEGER NOT NULL,
    objectif_texte TEXT NOT NULL,
    regle_id TEXT NOT NULL UNIQUE,
    poids_max INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS referentiel_mapping (
    chapitre_num INTEGER PRIMARY KEY,
    chapitre_nom TEXT,
    iso27001 TEXT,
    nist_csf TEXT,
    dora TEXT
);

CREATE TABLE IF NOT EXISTS recommandations (
    objectif_num INTEGER PRIMARY KEY,
    recommandations_json TEXT
);

CREATE TABLE IF NOT EXISTS entites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    secteur TEXT,
    date_creation TEXT
);

CREATE TABLE IF NOT EXISTS controles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entite_id INTEGER NOT NULL REFERENCES entites(id) ON DELETE CASCADE,
    date_controle TEXT,
    responsable TEXT,
    statut TEXT DEFAULT 'En cours',
    commentaire_general TEXT,
    source_donnees TEXT DEFAULT 'saisie'
);

CREATE TABLE IF NOT EXISTS controle_reponses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    controle_id INTEGER NOT NULL REFERENCES controles(id) ON DELETE CASCADE,
    ref_id INTEGER NOT NULL REFERENCES pssi_referentiel(id),
    niveau TEXT,
    non_applicable INTEGER DEFAULT 0,
    justification TEXT,
    commentaire TEXT,
    UNIQUE(controle_id, ref_id)
);

CREATE TABLE IF NOT EXISTS risk_biens_essentiels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entite_id INTEGER NOT NULL REFERENCES entites(id) ON DELETE CASCADE,
    code TEXT,
    nom TEXT,
    description TEXT,
    processus TEXT,
    proprietaire TEXT,
    d INTEGER, i INTEGER, c INTEGER, t INTEGER,
    niveau_classification INTEGER,
    commentaire TEXT
);

CREATE TABLE IF NOT EXISTS risk_biens_supports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entite_id INTEGER NOT NULL REFERENCES entites(id) ON DELETE CASCADE,
    code TEXT,
    nom TEXT,
    type_bien TEXT,
    bien_essentiel_id INTEGER REFERENCES risk_biens_essentiels(id),
    proprietaire TEXT,
    localisation TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS risk_menaces_vuln (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    source_menace TEXT,
    menace TEXT,
    vulnerabilite TEXT,
    type_bien_support TEXT
);

CREATE TABLE IF NOT EXISTS risk_register (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entite_id INTEGER NOT NULL REFERENCES entites(id) ON DELETE CASCADE,
    code TEXT,
    bien_essentiel_id INTEGER REFERENCES risk_biens_essentiels(id),
    bien_support_id INTEGER REFERENCES risk_biens_supports(id),
    critere_dict TEXT,
    source_menace TEXT,
    menace TEXT,
    vulnerabilite TEXT,
    description_scenario TEXT,
    vraisemblance_brute INTEGER,
    gravite_brute INTEGER,
    mesures_existantes TEXT,
    vraisemblance_residuelle INTEGER,
    gravite_residuelle INTEGER,
    risque_acceptable TEXT,
    proprietaire_risque TEXT,
    categorie TEXT
);

CREATE TABLE IF NOT EXISTS risk_traitement (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    risque_id INTEGER NOT NULL REFERENCES risk_register(id) ON DELETE CASCADE,
    strategie TEXT,
    mesure TEXT,
    type_mesure TEXT,
    responsable TEXT,
    echeance TEXT,
    cout_estime REAL,
    statut TEXT
);
"""


def init_db(force_reseed=False):
    """Crée les tables si nécessaire et amorce les données de référence.
    N'écrase jamais les contrôles/risques déjà saisis par l'utilisateur,
    sauf si force_reseed=True (réinitialisation complète).
    Fonctionne indifféremment sur SQLite (par défaut) ou PostgreSQL (si la
    variable d'environnement DATABASE_URL est définie)."""
    conn = get_connection()
    schema_sql = SCHEMA if backend() == "sqlite" else dbengine.adapt_schema_for_postgres(SCHEMA)
    conn.executescript(schema_sql)
    conn.commit()

    if force_reseed:
        for t in ["controle_reponses", "controles", "risk_traitement", "risk_register",
                  "risk_biens_supports", "risk_biens_essentiels", "risk_menaces_vuln",
                  "entites", "pssi_referentiel", "referentiel_mapping", "recommandations",
                  "journal_activite", "utilisateurs"]:
            conn.execute(f"DELETE FROM {t}")
        conn.commit()

    cur = conn.execute("SELECT COUNT(*) AS n FROM pssi_referentiel")
    first_time = cur.fetchone()["n"] == 0
    if first_time:
        _seed_referentiel(conn)
        _seed_mapping(conn)
        _seed_recommandations(conn)
        _seed_demo_entite_et_controle(conn)
        _seed_menaces_vuln(conn)
        _seed_demo_risques(conn)
        _seed_entites_reconstituees(conn)
        conn.commit()

    identifiant_admin_initial = None
    cur = conn.execute("SELECT COUNT(*) AS n FROM utilisateurs")
    if cur.fetchone()["n"] == 0:
        from grc_core import auth
        identifiant_admin_initial = auth.seed_admin_par_defaut(conn)
        conn.commit()

    conn.close()
    return first_time, identifiant_admin_initial


def _load_json(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def _seed_referentiel(conn):
    rows = _load_json("pssi_referentiel.json")
    conn.executemany(
        "INSERT INTO pssi_referentiel (chapitre_num, chapitre_nom, objectif_num, objectif_texte, regle_id, poids_max) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (r["chapitre_num"], r["chapitre_nom"], r["objectif_num"], r["objectif_texte"],
             r["regle_id"], r["poids_max"])
            for r in rows
        ],
    )


def _seed_mapping(conn):
    rows = _load_json("mapping_referentiels.json")
    conn.executemany(
        "INSERT INTO referentiel_mapping (chapitre_num, chapitre_nom, iso27001, nist_csf, dora) "
        "VALUES (:chapitre_num, :chapitre_nom, :iso27001, :nist_csf, :dora)",
        rows,
    )


def _seed_recommandations(conn):
    data = _load_json("recommandations.json")
    for k, v in data.items():
        conn.execute(
            "INSERT INTO recommandations (objectif_num, recommandations_json) VALUES (?, ?)",
            (int(k), json.dumps(v, ensure_ascii=False)),
        )


def _seed_demo_entite_et_controle(conn):
    cur = conn.execute(
        "INSERT INTO entites (nom, secteur, date_creation) VALUES (?, ?, ?)",
        ("Entité de démonstration", "Administration publique", str(date.today())),
    )
    entite_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO controles (entite_id, date_controle, responsable, statut, commentaire_general) "
        "VALUES (?, ?, ?, ?, ?)",
        (entite_id, str(date.today()), "Équipe DCSSI", "En cours",
         "Contrôle de démonstration pré-chargé pour explorer la plateforme."),
    )
    controle_id = cur.lastrowid

    rows = _load_json("pssi_referentiel.json")
    ref_rows = conn.execute("SELECT id, regle_id FROM pssi_referentiel").fetchall()
    id_by_regle = {r["regle_id"]: r["id"] for r in ref_rows}

    for r in rows:
        niveau = r.get("demo_niveau")
        if niveau:
            conn.execute(
                "INSERT INTO controle_reponses (controle_id, ref_id, niveau, non_applicable, justification) "
                "VALUES (?, ?, ?, 0, ?)",
                (controle_id, id_by_regle[r["regle_id"]], niveau, r.get("demo_justif")),
            )


def _seed_menaces_vuln(conn):
    data = _load_json("iso27005_example.json")
    rows = data.get("menaces_vuln", [])
    for r in rows:
        conn.execute(
            "INSERT INTO risk_menaces_vuln (code, source_menace, menace, vulnerabilite, type_bien_support) "
            "VALUES (?, ?, ?, ?, ?)",
            (r.get("ID"), r.get("Source de menace"), r.get("Menace"),
             r.get("Vulnérabilité exploitée"), r.get("Type de bien support concerné")),
        )


def _seed_demo_risques(conn):
    data = _load_json("iso27005_example.json")
    entite = conn.execute("SELECT id FROM entites LIMIT 1").fetchone()
    entite_id = entite["id"]

    be_id_map = {}
    for be in data.get("biens_essentiels", []):
        cur = conn.execute(
            "INSERT INTO risk_biens_essentiels (entite_id, code, nom, description, processus, proprietaire, d, i, c, t, niveau_classification, commentaire) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entite_id, be.get("ID"), be.get("Bien essentiel"), be.get("Description"),
             be.get("Processus métier / Activité"), be.get("Propriétaire"),
             be.get("D"), be.get("I"), be.get("C"), be.get("T"),
             be.get("Niveau de classification"), be.get("Commentaire")),
        )
        be_id_map[be.get("ID")] = cur.lastrowid

    bs_id_map = {}
    for bs in data.get("biens_supports", []):
        be_ref = be_id_map.get(bs.get("Bien essentiel associé"))
        cur = conn.execute(
            "INSERT INTO risk_biens_supports (entite_id, code, nom, type_bien, bien_essentiel_id, proprietaire, localisation, description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (entite_id, bs.get("ID"), bs.get("Bien support"), bs.get("Type de bien"),
             be_ref, bs.get("Propriétaire / Gestionnaire"), bs.get("Localisation"), bs.get("Description")),
        )
        bs_id_map[bs.get("ID")] = cur.lastrowid

    risk_id_map = {}
    for ap in data.get("appreciation", []):
        cur = conn.execute(
            "INSERT INTO risk_register (entite_id, code, bien_essentiel_id, bien_support_id, critere_dict, "
            "source_menace, menace, vulnerabilite, description_scenario, vraisemblance_brute, gravite_brute, "
            "mesures_existantes, vraisemblance_residuelle, gravite_residuelle, risque_acceptable, proprietaire_risque, categorie) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entite_id, ap.get("ID Risque"),
             be_id_map.get(ap.get("Bien essentiel concerné")),
             bs_id_map.get(ap.get("Bien support concerné")),
             ap.get("Critère DICT affecté"), ap.get("Source de menace"), ap.get("Menace"),
             ap.get("Vulnérabilité exploitée"), ap.get("Description du scénario de risque"),
             ap.get("Vraisem- blance brute"), ap.get("Gravité brute"),
             ap.get("Mesures de sécurité existantes / prévues"),
             ap.get("Vraisem- blance résiduelle"), ap.get("Gravité résiduelle"),
             ap.get("Risque acceptable"), ap.get("Propriétaire du risque"),
             "Sécurité de l'information"),
        )
        risk_id_map[ap.get("ID Risque")] = cur.lastrowid

    for pt in data.get("plan_traitement", []):
        rid = risk_id_map.get(pt.get("ID Risque"))
        if rid is None:
            continue
        conn.execute(
            "INSERT INTO risk_traitement (risque_id, strategie, mesure, type_mesure, responsable, echeance, cout_estime, statut) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (rid, pt.get("Stratégie"), pt.get("Mesure / Action de sécurité"), pt.get("Type de mesure"),
             pt.get("Responsable"), pt.get("Échéance"), pt.get("Coût estimé (FCFA)"), pt.get("Statut")),
        )


def _repartir_niveaux_pour_moyenne(score_cible, n_regles):
    """Répartit n_regles niveaux entiers (0 à 5) de façon à approcher au plus près
    la moyenne cible, par interpolation entre les deux niveaux entiers encadrants.
    Teste les deux arrondis possibles du nombre de règles au niveau supérieur et
    retient celui qui minimise l'écart à la moyenne cible.
    Retourne la liste des poids (int) à assigner, dans un ordre déterministe."""
    import math

    base = int(score_cible)
    base = max(0, min(5, base))
    frac = score_cible - base
    if base >= 5 or frac <= 0:
        return [min(base, 5)] * n_regles

    k_floor = max(0, min(n_regles, math.floor(frac * n_regles)))
    k_ceil = max(0, min(n_regles, k_floor + 1))

    def moyenne_pour(k):
        return (k * (base + 1) + (n_regles - k) * base) / n_regles

    k_hauts = min([k_floor, k_ceil], key=lambda k: abs(moyenne_pour(k) - score_cible))
    return [base + 1] * k_hauts + [base] * (n_regles - k_hauts)


def _seed_entites_reconstituees(conn):
    """Recharge, à titre d'illustration, les évaluations ANAQ-Sup et COUD déjà
    réalisées par la DCSSI (rapports Word transmis), en reconstituant une réponse
    par règle à partir des scores moyens publiés par objectif (Table 6 des
    rapports). Les rapports Word ne conservent que des moyennes agrégées : cette
    reconstitution est donc une APPROXIMATION qui reproduit fidèlement les scores
    par objectif/chapitre/global publiés, mais pas nécessairement le niveau
    attribué à chaque règle individuelle d'origine (information non disponible)."""
    try:
        data = _load_json("rapports_existants.json")
    except FileNotFoundError:
        return

    ref_rows = conn.execute(
        "SELECT id, regle_id, objectif_num FROM pssi_referentiel ORDER BY objectif_num, regle_id"
    ).fetchall()
    regles_par_objectif = {}
    for r in ref_rows:
        regles_par_objectif.setdefault(r["objectif_num"], []).append(r)

    for nom_entite, contenu in data.items():
        objectifs_scores = {int(k): v for k, v in contenu["objectifs"].items()}
        na_overrides = {int(k): v for k, v in contenu.get("na_overrides", {}).items()}

        cur = conn.execute(
            "INSERT INTO entites (nom, secteur, date_creation) VALUES (?, ?, ?)",
            (nom_entite, "Administration publique", str(date.today())),
        )
        entite_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO controles (entite_id, date_controle, responsable, statut, commentaire_general, source_donnees) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (entite_id, str(date.today()), "DCSSI",
             "Terminé",
             "Données reconstituées à partir du rapport d'évaluation DCSSI déjà produit pour cette entité "
             "(moyennes par objectif). Les rapports Word d'origine ne conservent que des scores agrégés : "
             "le niveau attribué ici à chaque règle est une approximation qui reproduit les scores par "
             "objectif/chapitre/global publiés, mais ne reflète pas nécessairement la réponse individuelle "
             "d'origine règle par règle.",
             "reconstitution"),
        )
        controle_id = cur.lastrowid

        for obj_num, regles in regles_par_objectif.items():
            score = objectifs_scores.get(obj_num)
            n_na = na_overrides.get(obj_num, 0)
            regles_na = regles[:n_na]
            regles_applicables = regles[n_na:]

            for r in regles_na:
                conn.execute(
                    "INSERT INTO controle_reponses (controle_id, ref_id, niveau, non_applicable, justification) "
                    "VALUES (?, ?, NULL, 1, ?)",
                    (controle_id, r["id"], "Déclaré non applicable dans le rapport DCSSI d'origine."),
                )

            if score is None or not regles_applicables:
                continue

            poids_list = _repartir_niveaux_pour_moyenne(score, len(regles_applicables))
            for r, poids in zip(regles_applicables, poids_list):
                niveau_code = POIDS_TO_NIVEAU[poids]
                conn.execute(
                    "INSERT INTO controle_reponses (controle_id, ref_id, niveau, non_applicable) "
                    "VALUES (?, ?, ?, 0)",
                    (controle_id, r["id"], niveau_code),
                )
