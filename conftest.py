"""
Fixtures partagées pour la suite de tests de la plateforme GRC.

Chaque test qui a besoin d'une base de données obtient un fichier SQLite
temporaire isolé (jamais le `db/grc.db` réel de la plateforme), amorcé avec
les données de référence via `grc_core.db.init_db()`.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import pytest

from grc_core import dbengine
from grc_core import db as db_module


@pytest.fixture()
def temp_db_path(tmp_path, monkeypatch):
    """Redirige la base SQLite vers un fichier temporaire pour la durée du test,
    et s'assure qu'aucune variable DATABASE_URL ne fait basculer vers PostgreSQL
    (sauf si le test la positionne lui-même explicitement)."""
    path = tmp_path / "test_grc.db"
    monkeypatch.setattr(dbengine, "SQLITE_DB_PATH", str(path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return str(path)


@pytest.fixture()
def seeded_db(temp_db_path):
    """Base de test amorcée (référentiel PSSI-ES, mapping, recommandations,
    entité de démonstration, entités reconstituées ANAQ-Sup/COUD, compte admin
    initial). Retourne (chemin_db, identifiant_admin_initial, mdp_admin_initial)."""
    first_time, admin_creds = db_module.init_db()
    assert first_time is True
    assert admin_creds is not None
    return temp_db_path, admin_creds[0], admin_creds[1]


@pytest.fixture()
def conn(seeded_db):
    """Connexion ouverte sur la base de test amorcée. Fermée automatiquement
    en fin de test."""
    c = dbengine.get_connection()
    yield c
    c.close()
