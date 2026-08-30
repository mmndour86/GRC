"""Test d'intégration du script de migration SQLite -> PostgreSQL.

Ce test est ignoré (skip) par défaut : il ne s'exécute que si une base
PostgreSQL de test est joignable via la variable d'environnement
GRC_TEST_POSTGRES_URL (ex: postgresql://user:pwd@localhost:5432/grc_test_db).
Cette base doit exister et être vide (ou vidable) : elle est écrasée avec
--force par ce test.

Exemple pour lancer ce test spécifiquement :
    createdb grc_test_db
    export GRC_TEST_POSTGRES_URL=postgresql://user:pwd@localhost:5432/grc_test_db
    pytest tests/test_migration.py -v
"""
import os
import subprocess
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

POSTGRES_TEST_URL = os.environ.get("GRC_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="GRC_TEST_POSTGRES_URL non défini : test de migration PostgreSQL ignoré "
           "(voir la docstring de ce fichier pour l'activer).",
)


def test_migration_copie_toutes_les_lignes(seeded_db):
    sqlite_path, _, _ = seeded_db

    result = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, "scripts", "migrate_sqlite_to_postgres.py"),
         "--sqlite-path", sqlite_path, "--postgres-url", POSTGRES_TEST_URL, "--force"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr

    import psycopg2
    import psycopg2.extras
    pg_conn = psycopg2.connect(POSTGRES_TEST_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = pg_conn.cursor()

    cur.execute("SELECT COUNT(*) AS n FROM pssi_referentiel")
    assert cur.fetchone()["n"] == 228

    cur.execute("SELECT COUNT(*) AS n FROM utilisateurs")
    assert cur.fetchone()["n"] == 1

    # Vérifie que la séquence a bien été resynchronisée : une nouvelle
    # insertion ne doit pas entrer en collision avec les ID migrés.
    cur.execute("INSERT INTO entites (nom, secteur, date_creation) VALUES (%s, %s, %s) RETURNING id",
                ("Entité post-migration", "Test", "2026-01-01"))
    new_id = cur.fetchone()["id"]
    pg_conn.commit()
    assert new_id > 0

    pg_conn.close()
