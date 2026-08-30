"""Tests unitaires de l'authentification et de la gestion des comptes (grc_core.auth)."""
import pytest

from grc_core import auth


def test_hash_password_deterministic_with_same_salt():
    h1, sel = auth.hash_password("MotDePasse123")
    h2, _ = auth.hash_password("MotDePasse123", sel_hex=sel)
    assert h1 == h2


def test_hash_password_different_salts_by_default():
    h1, sel1 = auth.hash_password("MotDePasse123")
    h2, sel2 = auth.hash_password("MotDePasse123")
    assert sel1 != sel2
    assert h1 != h2  # sels différents => hachages différents pour le même mot de passe


def test_verify_password_correct_and_incorrect():
    h, sel = auth.hash_password("SuperSecret1")
    assert auth.verify_password("SuperSecret1", h, sel) is True
    assert auth.verify_password("MauvaisMotDePasse", h, sel) is False


def test_generer_mot_de_passe_initial_format():
    mdp = auth.generer_mot_de_passe_initial()
    parts = mdp.split("-")
    assert len(parts) == 3
    assert parts[1].isdigit()
    assert 10 <= int(parts[1]) <= 99


def test_seed_admin_par_defaut_creates_admin_role(conn):
    # Le fixture `conn` amorce déjà la base (via seeded_db), qui appelle
    # seed_admin_par_defaut en interne à la création. On vérifie son résultat ici.
    row = conn.execute("SELECT * FROM utilisateurs WHERE identifiant='admin'").fetchone()
    assert row is not None
    assert row["role"] == "administrateur"
    assert row["actif"] == 1
    assert row["doit_changer_mdp"] == 1


def test_authentifier_succes(seeded_db):
    _, identifiant, mdp = seeded_db
    import grc_core.dbengine as dbengine
    c = dbengine.get_connection()
    user = auth.authentifier(c, identifiant, mdp)
    assert user is not None
    assert user["identifiant"] == identifiant
    c.close()


def test_authentifier_mauvais_mot_de_passe(seeded_db):
    _, identifiant, _ = seeded_db
    import grc_core.dbengine as dbengine
    c = dbengine.get_connection()
    user = auth.authentifier(c, identifiant, "mot_de_passe_incorrect")
    assert user is None
    c.close()


def test_authentifier_identifiant_inconnu(conn):
    assert auth.authentifier(conn, "utilisateur_inexistant", "peu importe") is None


def test_authentifier_compte_desactive(conn):
    auth.creer_utilisateur(conn, "bob", "Bob Test", "MotDePasse123", "auditeur")
    row = conn.execute("SELECT id FROM utilisateurs WHERE identifiant='bob'").fetchone()
    auth.definir_statut(conn, row["id"], False, acteur="admin")
    assert auth.authentifier(conn, "bob", "MotDePasse123") is None


def test_creer_utilisateur_et_lister(conn):
    auth.creer_utilisateur(conn, "alice", "Alice Test", "MotDePasse123", "lecture_seule")
    utilisateurs = auth.lister_utilisateurs(conn)
    identifiants = [u["identifiant"] for u in utilisateurs]
    assert "alice" in identifiants
    alice = next(u for u in utilisateurs if u["identifiant"] == "alice")
    assert alice["role"] == "lecture_seule"
    assert alice["doit_changer_mdp"] == 1


def test_changer_mot_de_passe(conn):
    auth.creer_utilisateur(conn, "carole", "Carole Test", "AncienMdp123", "auditeur")
    user_row = conn.execute("SELECT id FROM utilisateurs WHERE identifiant='carole'").fetchone()
    auth.changer_mot_de_passe(conn, user_row["id"], "NouveauMdp456", identifiant_pour_journal="carole")

    assert auth.authentifier(conn, "carole", "AncienMdp123") is None
    user = auth.authentifier(conn, "carole", "NouveauMdp456")
    assert user is not None
    assert user["doit_changer_mdp"] == 0


def test_definir_role(conn):
    auth.creer_utilisateur(conn, "david", "David Test", "MotDePasse123", "lecture_seule")
    user_row = conn.execute("SELECT id FROM utilisateurs WHERE identifiant='david'").fetchone()
    auth.definir_role(conn, user_row["id"], "administrateur", acteur="admin")
    updated = conn.execute("SELECT role FROM utilisateurs WHERE id=?", (user_row["id"],)).fetchone()
    assert updated["role"] == "administrateur"


def test_log_action_ecrit_dans_le_journal(conn):
    n_avant = conn.execute("SELECT COUNT(*) AS n FROM journal_activite").fetchone()["n"]
    auth.log_action(conn, "testeur", "action_de_test", "détails de test")
    n_apres = conn.execute("SELECT COUNT(*) AS n FROM journal_activite").fetchone()["n"]
    assert n_apres == n_avant + 1
    derniere = conn.execute("SELECT * FROM journal_activite ORDER BY id DESC LIMIT 1").fetchone()
    assert derniere["utilisateur"] == "testeur"
    assert derniere["action"] == "action_de_test"


def test_authentifier_logs_echec_et_succes(conn):
    auth.creer_utilisateur(conn, "eve", "Eve Test", "MotDePasse123", "auditeur")
    auth.authentifier(conn, "eve", "mauvais_mdp")
    auth.authentifier(conn, "eve", "MotDePasse123")
    actions = [r["action"] for r in conn.execute(
        "SELECT action FROM journal_activite WHERE utilisateur='eve' ORDER BY id"
    ).fetchall()]
    assert "connexion_echouee" in actions
    assert "connexion_reussie" in actions


# ---------------------------------------------------------------------------
# Helpers Streamlit (can_write / is_admin / current_user) : testés sans
# session Streamlit réelle, en simulant st.session_state avec un dict.
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_session_state(monkeypatch):
    state = {}
    monkeypatch.setattr(auth.st, "session_state", state)
    return state


def test_can_write_par_role(fake_session_state):
    fake_session_state["grc_user"] = {"identifiant": "x", "role": "administrateur"}
    assert auth.can_write() is True
    fake_session_state["grc_user"] = {"identifiant": "x", "role": "auditeur"}
    assert auth.can_write() is True
    fake_session_state["grc_user"] = {"identifiant": "x", "role": "lecture_seule"}
    assert auth.can_write() is False


def test_is_admin_par_role(fake_session_state):
    fake_session_state["grc_user"] = {"identifiant": "x", "role": "administrateur"}
    assert auth.is_admin() is True
    fake_session_state["grc_user"] = {"identifiant": "x", "role": "auditeur"}
    assert auth.is_admin() is False


def test_current_user_none_when_logged_out(fake_session_state):
    assert auth.current_user() is None
    assert auth.is_logged_in() is False
    assert auth.can_write() is False
