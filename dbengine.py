"""
Couche d'abstraction base de données : permet à la plateforme de fonctionner
indifféremment sur SQLite (par défaut, zéro configuration) ou sur PostgreSQL
(recommandé en production, multi-utilisateurs).

Le reste du code applicatif écrit ses requêtes avec le style de paramètres
SQLite (`?`) et appelle `conn.execute(sql, params)` comme sur un objet
sqlite3.Connection standard. Cette couche traduit silencieusement vers la
syntaxe psycopg2 (`%s`) quand la variable d'environnement DATABASE_URL pointe
vers PostgreSQL, et émule `cursor.lastrowid` (non supporté nativement par
psycopg2) via `SELECT lastval()`.

Sélection du backend :
- DATABASE_URL absente ou vide  -> SQLite, fichier db/grc.db (comportement
  historique du prototype, aucune dépendance supplémentaire requise).
- DATABASE_URL commençant par "postgres://" ou "postgresql://" -> PostgreSQL
  via psycopg2 (nécessite `pip install psycopg2-binary`).
"""
import os
import re
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_DB_PATH = os.path.join(BASE_DIR, "db", "grc.db")

_PLACEHOLDER_RE = re.compile(r"\?")


def backend():
    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith("postgres://") or url.startswith("postgresql://"):
        return "postgres"
    return "sqlite"


def _to_pg_sql(sql):
    return _PLACEHOLDER_RE.sub("%s", sql)


class _PgCursorWrapper:
    """Fait ressembler un curseur psycopg2 à un curseur sqlite3 : mêmes
    méthodes fetchone/fetchall/fetchmany, et un attribut `lastrowid` calculé
    via SELECT lastval() juste après un INSERT dans une table à colonne SERIAL."""

    def __init__(self, real_cursor):
        self._cur = real_cursor
        self.lastrowid = None

    def execute(self, sql, params=()):
        pg_sql = _to_pg_sql(sql)
        self._cur.execute(pg_sql, tuple(params) if params else None)
        if pg_sql.strip().upper().startswith("INSERT"):
            try:
                self._cur.execute("SELECT lastval()")
                self.lastrowid = self._cur.fetchone()["lastval"]
            except Exception:
                # Table sans colonne SERIAL (aucune séquence appelée) : pas de lastrowid.
                self.lastrowid = None
        return self

    def executemany(self, sql, seq_of_params):
        pg_sql = _to_pg_sql(sql)
        self._cur.executemany(pg_sql, [tuple(p) for p in seq_of_params])
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size=None):
        return self._cur.fetchmany(size) if size is not None else self._cur.fetchmany()

    def __iter__(self):
        return iter(self._cur)


class _PgConnWrapper:
    """Fait ressembler une connexion psycopg2 à une connexion sqlite3 pour le
    sous-ensemble d'API utilisé par le reste de l'application :
    conn.execute(...), conn.executemany(...), conn.executescript(...),
    conn.commit(), conn.close()."""

    def __init__(self, real_conn):
        self._conn = real_conn

    def execute(self, sql, params=()):
        cur = _PgCursorWrapper(self._conn.cursor())
        return cur.execute(sql, params)

    def executemany(self, sql, seq_of_params):
        cur = _PgCursorWrapper(self._conn.cursor())
        return cur.executemany(sql, seq_of_params)

    def executescript(self, sql):
        # Le protocole simple de PostgreSQL exécute nativement plusieurs
        # instructions séparées par des points-virgules en un seul appel.
        cur = self._conn.cursor()
        cur.execute(sql)
        return cur

    def cursor(self):
        return _PgCursorWrapper(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_connection():
    """Retourne une connexion — SQLite par défaut, PostgreSQL si DATABASE_URL
    est définie. L'objet retourné expose la même API dans les deux cas."""
    if backend() == "postgres":
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError as e:
            raise RuntimeError(
                "DATABASE_URL pointe vers PostgreSQL mais le paquet 'psycopg2-binary' "
                "n'est pas installé. Exécutez : pip install psycopg2-binary"
            ) from e
        url = os.environ["DATABASE_URL"]
        real_conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
        return _PgConnWrapper(real_conn)

    os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def adapt_schema_for_postgres(sqlite_schema_sql):
    """Convertit le schéma DDL écrit en syntaxe SQLite vers une syntaxe
    compatible PostgreSQL. Les deux moteurs partagent la quasi-totalité de la
    syntaxe DDL utilisée ici ; seule la clé primaire auto-incrémentée diffère."""
    return sqlite_schema_sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")


def sqlite_db_exists():
    return os.path.exists(SQLITE_DB_PATH)
