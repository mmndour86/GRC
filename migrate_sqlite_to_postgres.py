#!/usr/bin/env python3
"""
Migration des données de la plateforme GRC depuis SQLite (prototype) vers
PostgreSQL (production).

Usage :
    python3 scripts/migrate_sqlite_to_postgres.py \\
        --sqlite-path db/grc.db \\
        --postgres-url postgresql://grc_user:motdepasse@localhost:5432/grc_db

Si --postgres-url est omis, la variable d'environnement DATABASE_URL est
utilisée. Si --sqlite-path est omis, le fichier par défaut de la plateforme
(db/grc.db) est utilisé.

Le script :
1. crée le schéma dans PostgreSQL s'il n'existe pas déjà (mêmes tables que
   SQLite, avec SERIAL à la place de INTEGER PRIMARY KEY AUTOINCREMENT) ;
2. copie toutes les données table par table, dans l'ordre des dépendances
   (clés étrangères), en conservant les identifiants d'origine ;
3. resynchronise les séquences PostgreSQL (nextval) sur la valeur maximale
   des identifiants copiés, pour que les prochaines insertions ne rentrent
   pas en collision avec les lignes migrées.

Le script est idempotent-safe par défaut : il refuse de continuer si des
tables cibles contiennent déjà des données, sauf si --force est précisé
(auquel cas les tables cibles sont vidées avant la copie, dans l'ordre
inverse des dépendances).
"""
import argparse
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from grc_core import dbengine  # noqa: E402
from grc_core.db import SCHEMA  # noqa: E402

# Ordre de copie respectant les contraintes de clé étrangère.
TABLE_ORDER = [
    "utilisateurs",
    "journal_activite",
    "pssi_referentiel",
    "referentiel_mapping",
    "recommandations",
    "entites",
    "controles",
    "controle_reponses",
    "risk_biens_essentiels",
    "risk_biens_supports",
    "risk_menaces_vuln",
    "risk_register",
    "risk_traitement",
]

# Tables avec un identifiant auto-incrémenté « id » (SERIAL côté PostgreSQL) —
# leur séquence doit être resynchronisée après une copie qui préserve les ID
# d'origine. referentiel_mapping (clé = chapitre_num) et recommandations
# (clé = objectif_num) n'en ont pas.
TABLES_AVEC_SEQUENCE_ID = [t for t in TABLE_ORDER if t not in ("referentiel_mapping", "recommandations")]


def parse_args():
    p = argparse.ArgumentParser(description="Migration SQLite -> PostgreSQL de la plateforme GRC")
    p.add_argument("--sqlite-path", default=dbengine.SQLITE_DB_PATH,
                    help="Chemin du fichier SQLite source (par défaut : db/grc.db de la plateforme)")
    p.add_argument("--postgres-url", default=os.environ.get("DATABASE_URL"),
                    help="URL PostgreSQL cible (par défaut : variable d'environnement DATABASE_URL)")
    p.add_argument("--force", action="store_true",
                    help="Vide les tables cibles avant la copie si elles contiennent déjà des données")
    return p.parse_args()


def get_sqlite_conn(path):
    if not os.path.exists(path):
        print(f"Erreur : fichier SQLite introuvable : {path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_pg_conn(url):
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("Erreur : le paquet 'psycopg2-binary' n'est pas installé. "
              "Exécutez : pip install psycopg2-binary", file=sys.stderr)
        sys.exit(1)
    if not url:
        print("Erreur : aucune URL PostgreSQL fournie (--postgres-url ou variable DATABASE_URL).",
              file=sys.stderr)
        sys.exit(1)
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)


def ensure_schema(pg_conn):
    pg_schema = dbengine.adapt_schema_for_postgres(SCHEMA)
    cur = pg_conn.cursor()
    cur.execute(pg_schema)
    pg_conn.commit()
    print("Schéma PostgreSQL vérifié / créé.")


def table_columns(sqlite_conn, table):
    cur = sqlite_conn.execute(f"PRAGMA table_info({table})")
    return [row["name"] for row in cur.fetchall()]


def count_rows_pg(pg_conn, table):
    cur = pg_conn.cursor()
    cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
    return cur.fetchone()["n"]


def wipe_target(pg_conn):
    cur = pg_conn.cursor()
    for table in reversed(TABLE_ORDER):
        cur.execute(f"DELETE FROM {table}")
    pg_conn.commit()
    print("Tables cibles PostgreSQL vidées (--force).")


def copy_table(sqlite_conn, pg_conn, table):
    columns = table_columns(sqlite_conn, table)
    rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        print(f"  {table:<24} : 0 ligne (rien à copier)")
        return 0

    placeholders = ", ".join(["%s"] * len(columns))
    col_list = ", ".join(columns)
    insert_sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    cur = pg_conn.cursor()
    values = [tuple(row[c] for c in columns) for row in rows]
    cur.executemany(insert_sql, values)
    pg_conn.commit()
    print(f"  {table:<24} : {len(rows)} ligne(s) copiée(s)")
    return len(rows)


def resync_sequence(pg_conn, table):
    cur = pg_conn.cursor()
    cur.execute(
        "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
        "COALESCE((SELECT MAX(id) FROM " + table + "), 1), "
        "(SELECT MAX(id) IS NOT NULL FROM " + table + "))",
        (table,),
    )
    pg_conn.commit()


def main():
    args = parse_args()

    print(f"Source SQLite   : {args.sqlite_path}")
    print(f"Cible PostgreSQL : {args.postgres_url}")
    print()

    sqlite_conn = get_sqlite_conn(args.sqlite_path)
    pg_conn = get_pg_conn(args.postgres_url)

    ensure_schema(pg_conn)

    total_existant = sum(count_rows_pg(pg_conn, t) for t in TABLE_ORDER)
    if total_existant > 0:
        if not args.force:
            print(
                f"\nErreur : la base PostgreSQL cible contient déjà {total_existant} ligne(s) au total. "
                "Relancez avec --force pour vider les tables cibles avant la copie, ou pointez vers une "
                "base PostgreSQL vide.",
                file=sys.stderr,
            )
            sys.exit(1)
        wipe_target(pg_conn)

    print("\nCopie des données :")
    total_copie = 0
    for table in TABLE_ORDER:
        total_copie += copy_table(sqlite_conn, pg_conn, table)

    print("\nResynchronisation des séquences PostgreSQL...")
    for table in TABLES_AVEC_SEQUENCE_ID:
        resync_sequence(pg_conn, table)

    sqlite_conn.close()
    pg_conn.close()

    print(f"\nMigration terminée : {total_copie} ligne(s) copiée(s) au total.")
    print(
        "Pensez à définir la variable d'environnement DATABASE_URL avant de lancer la plateforme "
        "en production, pour qu'elle utilise désormais PostgreSQL :\n"
        f"  export DATABASE_URL=\"{args.postgres_url}\""
    )


if __name__ == "__main__":
    main()
