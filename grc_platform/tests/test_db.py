"""Tests de la couche base de données : amorçage (seed), ré-initialisation,
et abstraction double-backend SQLite/PostgreSQL (grc_core.db / grc_core.dbengine)."""
import os

from grc_core import dbengine
from grc_core import db as db_module


def test_backend_defaults_to_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert dbengine.backend() == "sqlite"


def test_backend_detects_postgres_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pwd@host:5432/dbname")
    assert dbengine.backend() == "postgres"
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pwd@host:5432/dbname")
    assert dbengine.backend() == "postgres"


def test_to_pg_sql_translates_placeholders():
    sql = "SELECT * FROM t WHERE a=? AND b=?"
    assert dbengine._to_pg_sql(sql) == "SELECT * FROM t WHERE a=%s AND b=%s"


def test_adapt_schema_for_postgres_replaces_autoincrement():
    sqlite_schema = "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, x TEXT);"
    pg_schema = dbengine.adapt_schema_for_postgres(sqlite_schema)
    assert "SERIAL PRIMARY KEY" in pg_schema
    assert "AUTOINCREMENT" not in pg_schema


def test_init_db_creates_sqlite_file(temp_db_path):
    assert not os.path.exists(temp_db_path)
    db_module.init_db()
    assert os.path.exists(temp_db_path)


def test_init_db_seeds_referentiel_pssi_es(conn):
    n = conn.execute("SELECT COUNT(*) AS n FROM pssi_referentiel").fetchone()["n"]
    assert n == 228
    n_chap = conn.execute("SELECT COUNT(DISTINCT chapitre_num) AS n FROM pssi_referentiel").fetchone()["n"]
    assert n_chap == 11
    n_obj = conn.execute("SELECT COUNT(DISTINCT objectif_num) AS n FROM pssi_referentiel").fetchone()["n"]
    assert n_obj == 30


def test_init_db_seeds_mapping_referentiels(conn):
    n = conn.execute("SELECT COUNT(*) AS n FROM referentiel_mapping").fetchone()["n"]
    assert n == 11


def test_init_db_seeds_recommandations_pour_30_objectifs(conn):
    n = conn.execute("SELECT COUNT(*) AS n FROM recommandations").fetchone()["n"]
    assert n == 30


def test_init_db_seeds_demo_entite_et_reconstitutions(conn):
    noms = [r["nom"] for r in conn.execute("SELECT nom FROM entites").fetchall()]
    assert "Entité de démonstration" in noms
    # Les entités reconstituées ANAQ-Sup / COUD doivent être présentes (voir
    # data/rapports_existants.json) avec un contrôle marqué "reconstitution".
    reconstitues = conn.execute(
        "SELECT COUNT(*) AS n FROM controles WHERE source_donnees='reconstitution'"
    ).fetchone()["n"]
    assert reconstitues >= 1


def test_init_db_creates_initial_admin_account(conn):
    admin = conn.execute("SELECT * FROM utilisateurs WHERE identifiant='admin'").fetchone()
    assert admin is not None
    assert admin["role"] == "administrateur"


def test_init_db_second_call_does_not_reseed(seeded_db):
    """Un second appel à init_db() (ex: rechargement de l'appli) ne doit ni
    dupliquer le référentiel, ni écraser un contrôle déjà saisi par l'utilisateur."""
    c = dbengine.get_connection()
    c.execute(
        "INSERT INTO entites (nom, secteur, date_creation) VALUES (?, ?, ?)",
        ("Entité saisie par l'utilisateur", "Test", "2026-01-01"),
    )
    c.commit()
    c.close()

    first_time, admin_creds = db_module.init_db()
    assert first_time is False
    assert admin_creds is None  # le compte admin existe déjà, pas de recréation

    c = dbengine.get_connection()
    n_referentiel = c.execute("SELECT COUNT(*) AS n FROM pssi_referentiel").fetchone()["n"]
    assert n_referentiel == 228  # pas dupliqué
    noms = [r["nom"] for r in c.execute("SELECT nom FROM entites").fetchall()]
    assert "Entité saisie par l'utilisateur" in noms  # conservée
    c.close()


def test_init_db_force_reseed_wipes_and_recreates(seeded_db):
    c = dbengine.get_connection()
    c.execute(
        "INSERT INTO entites (nom, secteur, date_creation) VALUES (?, ?, ?)",
        ("Entité à effacer", "Test", "2026-01-01"),
    )
    c.commit()
    c.close()

    first_time, admin_creds = db_module.init_db(force_reseed=True)
    assert first_time is True
    assert admin_creds is not None  # nouveau compte admin recréé

    c = dbengine.get_connection()
    noms = [r["nom"] for r in c.execute("SELECT nom FROM entites").fetchall()]
    assert "Entité à effacer" not in noms
    assert "Entité de démonstration" in noms
    n_referentiel = c.execute("SELECT COUNT(*) AS n FROM pssi_referentiel").fetchone()["n"]
    assert n_referentiel == 228
    c.close()


def test_nom_chapitre_affichage_utilise_libelles_officiels():
    assert db_module.nom_chapitre_affichage(1).startswith("Politique d'organisation")
    # Un numéro inconnu retombe sur le fallback fourni (title-case).
    assert db_module.nom_chapitre_affichage(999, "un chapitre inconnu") == "Un Chapitre Inconnu"


def test_niveau_et_poids_coherents():
    from grc_core.db import NIVEAU_TO_POIDS, POIDS_TO_NIVEAU
    for niveau, poids in NIVEAU_TO_POIDS.items():
        assert POIDS_TO_NIVEAU[poids] == niveau


def test_repartir_niveaux_pour_moyenne_reproduit_la_cible():
    from grc_core.db import _repartir_niveaux_pour_moyenne
    for cible, n in [(2.5, 10), (0.75, 4), (3.2, 25), (5.0, 6), (0.0, 6)]:
        poids = _repartir_niveaux_pour_moyenne(cible, n)
        assert len(poids) == n
        assert all(0 <= p <= 5 for p in poids)
        moyenne_obtenue = sum(poids) / n
        # L'écart doit rester dans la marge de quantification pour n petit
        # (au plus un demi-niveau divisé par n).
        assert abs(moyenne_obtenue - cible) <= (1.0 / n) + 1e-9


def test_repartir_niveaux_choisit_le_meilleur_arrondi():
    """Cas concret (n petit, cible ne se répartissant pas exactement) : la
    fonction doit choisir, entre l'arrondi inférieur et supérieur du nombre de
    règles au niveau haut, celui qui minimise l'écart à la moyenne cible —
    et non un arrondi bancaire naïf qui peut choisir le pire des deux."""
    from grc_core.db import _repartir_niveaux_pour_moyenne

    poids = _repartir_niveaux_pour_moyenne(0.75, 3)
    moyenne = sum(poids) / 3
    # floor(0.75*3)=2 règles à 1 -> moyenne 2/3≈0.667 (écart 0.083)
    # ceil                =3 règles à 1 -> moyenne 1.0 (écart 0.25)
    # Le floor est strictement meilleur : c'est celui qui doit être retenu.
    assert abs(moyenne - 2 / 3) < 1e-9
    assert abs(moyenne - 0.75) < abs(1.0 - 0.75)
