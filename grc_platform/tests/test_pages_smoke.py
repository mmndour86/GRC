"""Tests bout-en-bout des pages Streamlit via AppTest (sans navigateur réel) :
- chaque page doit être protégée par l'écran de connexion tant que personne
  n'est authentifié ;
- le parcours de connexion complet (identifiant/mot de passe -> changement de
  mot de passe obligatoire -> accès à l'application) doit fonctionner ;
- le contrôle d'accès par rôle (lecture seule / auditeur / administrateur)
  doit se comporter comme attendu sur les pages sensibles.
"""
import glob
import os

import pytest
from streamlit.testing.v1 import AppTest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ALL_APP_FILES = ["app.py"] + sorted(
    glob.glob(os.path.join(BASE_DIR, "pages", "*.py"))
)


def _apptest_for(path, temp_db_path):
    """Construit un AppTest pour le fichier donné, avec un timeout généreux
    (certaines pages calculent des scores sur 228 règles + génèrent des
    graphiques matplotlib)."""
    at = AppTest.from_file(path if os.path.isabs(path) else os.path.join(BASE_DIR, path))
    return at


@pytest.mark.parametrize("page_path", ALL_APP_FILES)
def test_page_shows_login_when_not_authenticated(page_path, temp_db_path):
    at = _apptest_for(page_path, temp_db_path)
    at.run(timeout=30)
    assert not at.exception
    titres = [t.value for t in at.title]
    assert any("Connexion" in t for t in titres), f"{page_path} devrait afficher l'écran de connexion"


def test_login_flow_and_forced_password_change(seeded_db):
    _, identifiant, mdp_initial = seeded_db
    at = AppTest.from_file(os.path.join(BASE_DIR, "app.py"))
    at.run(timeout=30)

    at.text_input[0].set_value(identifiant)
    at.text_input[1].set_value(mdp_initial)
    at.button[0].click().run(timeout=30)
    assert not at.exception
    assert any("Changement de mot de passe" in t.value for t in at.title)

    at.text_input[0].set_value("NouveauMotDePasse123")
    at.text_input[1].set_value("NouveauMotDePasse123")
    at.button[0].click().run(timeout=30)
    assert not at.exception
    assert any("Plateforme GRC" in t.value for t in at.title)
    assert any("Administrateur" in i.value for i in at.info)


def test_login_flow_rejects_wrong_password(seeded_db):
    _, identifiant, _ = seeded_db
    at = AppTest.from_file(os.path.join(BASE_DIR, "app.py"))
    at.run(timeout=30)
    at.text_input[0].set_value(identifiant)
    at.text_input[1].set_value("mot_de_passe_incorrect")
    at.button[0].click().run(timeout=30)
    assert not at.exception
    assert any("incorrect" in e.value.lower() for e in at.error)


@pytest.mark.parametrize("page_path", ALL_APP_FILES)
def test_page_loads_without_error_for_admin(page_path, seeded_db):
    admin_user = {
        "id": 1, "identifiant": "admin", "nom_complet": "Administrateur",
        "role": "administrateur", "actif": 1, "doit_changer_mdp": 0,
    }
    at = _apptest_for(page_path, seeded_db[0])
    at.session_state["grc_user"] = admin_user
    at.run(timeout=30)
    assert not at.exception, f"{page_path} a levé une exception pour un administrateur connecté"


def test_lecture_seule_role_hides_write_actions_page1(seeded_db):
    lecteur = {
        "id": 99, "identifiant": "lecteur", "nom_complet": "Lecteur Test",
        "role": "lecture_seule", "actif": 1, "doit_changer_mdp": 0,
    }
    at = AppTest.from_file(os.path.join(BASE_DIR, "pages", "1_📋_Conformite_PSSI_ES.py"))
    at.session_state["grc_user"] = lecteur
    at.run(timeout=30)
    assert not at.exception
    assert any("lecture seule" in c.value.lower() for c in at.caption)


def test_administration_page_blocked_for_non_admin(seeded_db):
    auditeur = {
        "id": 42, "identifiant": "auditeur1", "nom_complet": "Auditeur Test",
        "role": "auditeur", "actif": 1, "doit_changer_mdp": 0,
    }
    at = AppTest.from_file(os.path.join(BASE_DIR, "pages", "6_🔐_Administration.py"))
    at.session_state["grc_user"] = auditeur
    at.run(timeout=30)
    assert not at.exception
    assert any("droits nécessaires" in e.value for e in at.error)


def test_administration_page_accessible_for_admin(seeded_db):
    admin_user = {
        "id": 1, "identifiant": "admin", "nom_complet": "Administrateur",
        "role": "administrateur", "actif": 1, "doit_changer_mdp": 0,
    }
    at = AppTest.from_file(os.path.join(BASE_DIR, "pages", "6_🔐_Administration.py"))
    at.session_state["grc_user"] = admin_user
    at.run(timeout=30)
    assert not at.exception
    assert not at.error
    titres = [t.value for t in at.title]
    assert any("Administration" in t for t in titres)


def test_reponse_pssi_es_bloquee_en_lecture_seule(seeded_db):
    """Un utilisateur en lecture seule ne doit pas pouvoir modifier une réponse
    du questionnaire PSSI-ES : les widgets doivent être désactivés."""
    lecteur = {
        "id": 99, "identifiant": "lecteur", "nom_complet": "Lecteur Test",
        "role": "lecture_seule", "actif": 1, "doit_changer_mdp": 0,
    }
    at = AppTest.from_file(os.path.join(BASE_DIR, "pages", "1_📋_Conformite_PSSI_ES.py"))
    at.session_state["grc_user"] = lecteur
    at.run(timeout=30)
    assert not at.exception

    # Sélectionne l'entité de démonstration puis son contrôle, si les sélecteurs existent.
    selectbox_entite = next((s for s in at.selectbox if s.key and s.key.endswith("_ent_sel")), None)
    if selectbox_entite is None:
        pytest.skip("Sélecteur d'entité introuvable sur cette exécution de page.")
    selectbox_entite.set_value(next(o for o in selectbox_entite.options if "démonstration" in o.lower()))
    at.run(timeout=30)

    selectbox_controle = next((s for s in at.selectbox if s.key and s.key.endswith("_ctrl_sel")), None)
    if selectbox_controle is None or len(selectbox_controle.options) <= 1:
        pytest.skip("Aucun contrôle disponible pour l'entité de démonstration.")
    selectbox_controle.set_value(selectbox_controle.options[1])
    at.run(timeout=30)

    niveau_selects = [s for s in at.selectbox if s.key and s.key.startswith("niv_")]
    assert niveau_selects, "Aucun sélecteur de niveau de maturité trouvé sur la page"
    assert all(s.disabled for s in niveau_selects), (
        "Les sélecteurs de niveau doivent être désactivés en mode lecture seule"
    )
