import os

import streamlit as st

from grc_core import dbengine
from grc_core.db import init_db, get_connection
from grc_core import auth

st.set_page_config(page_title="Plateforme GRC — PSSI-ES / ISO 27005", page_icon="🛡️", layout="wide")

first_time, identifiant_admin_initial = init_db()

if identifiant_admin_initial:
    # Sauvegarde locale du mot de passe initial : la seule fois où il est disponible.
    # Écrit à côté de la base SQLite réellement utilisée (et non à côté de app.py),
    # pour ne rien écrire lorsque le backend actif est PostgreSQL ou une base de
    # test isolée.
    if dbengine.backend() == "sqlite":
        admin_pwd_path = os.path.join(os.path.dirname(dbengine.SQLITE_DB_PATH), "ADMIN_INITIAL_PASSWORD.txt")
        try:
            with open(admin_pwd_path, "w", encoding="utf-8") as f:
                f.write(
                    f"Identifiant : {identifiant_admin_initial[0]}\n"
                    f"Mot de passe initial : {identifiant_admin_initial[1]}\n"
                    "Ce mot de passe doit être changé dès la première connexion (c'est imposé par "
                    "la plateforme). Supprimez ce fichier une fois le mot de passe récupéré.\n"
                )
        except OSError:
            pass
    st.session_state["_identifiant_admin_initial"] = identifiant_admin_initial

conn = get_connection()
user = auth.require_login(conn)
auth.render_user_badge(conn)

pwd_notice = st.session_state.pop("_identifiant_admin_initial", None)
if pwd_notice:
    st.warning(
        f"**Compte administrateur créé.** Identifiant : `{pwd_notice[0]}` — "
        f"mot de passe initial : `{pwd_notice[1]}` (également enregistré dans "
        "`db/ADMIN_INITIAL_PASSWORD.txt`). Ce mot de passe devra être changé dès la première "
        "connexion. Notez-le maintenant : ce message ne s'affichera plus."
    )

st.title("🛡️ Plateforme GRC — Gouvernance, Risques, Conformité")
st.caption("Conformité PSSI-ES · ISO 27001 · NIST · DORA — Gestion des risques ISO/IEC 27005")

if first_time:
    st.success(
        "Base de données initialisée avec le référentiel PSSI-ES (228 règles / 30 objectifs / "
        "11 chapitres), les évaluations ANAQ-Sup/COUD reconstituées, et une entité de démonstration."
    )

st.markdown(
    """
Cette plateforme couvre l'ensemble du périmètre défini dans la note de cadrage :

1. **Conformité PSSI-ES** — questionnaire des 228 règles, calcul automatique des scores de maturité
   (échelle CMMI 0 à 5), gestion des non-applicabilités.
2. **Mapping référentiels** — correspondance entre chaque chapitre PSSI-ES et les référentiels
   ISO 27001, NIST CSF et DORA.
3. **Registre des risques ISO/IEC 27005** — biens essentiels, biens supports, menaces/vulnérabilités,
   appréciation des risques (brut/résiduel), matrice et plan de traitement.
4. **Tableau de bord** — indicateurs de maturité, heatmap des risques, suivi du plan d'action.
5. **Génération de rapport** — export automatique d'un rapport Word/PDF sur le modèle des rapports
   ANAQ-Sup / COUD, à l'issue d'un contrôle.

Utilisez le menu de gauche pour naviguer entre les modules. Les pages d'administration
(gestion des utilisateurs, journal d'activité) sont réservées au rôle administrateur.
    """
)

st.info(
    f"Connecté en tant que **{user.get('nom_complet') or user['identifiant']}** — rôle "
    f"**{auth.ROLE_LABELS.get(user['role'], user['role'])}**."
)

if auth.is_admin():
    with st.expander("⚙️ Administration de la base de données"):
        st.caption(f"Backend actif : **{'PostgreSQL' if os.environ.get('DATABASE_URL') else 'SQLite (fichier local)'}**")
        st.warning(
            "Réinitialiser la base supprime **toutes** les entités, contrôles, réponses, risques et "
            "comptes utilisateurs déjà créés, et recharge les données de référence, les exemples "
            "reconstitués, et un nouveau compte administrateur."
        )
        if st.button("Réinitialiser complètement la base de données", type="secondary"):
            auth.log_action(conn, user["identifiant"], "reinitialisation_base", "")
            auth.logout()
            init_db(force_reseed=True)
            st.success("Base de données réinitialisée. Reconnectez-vous avec le nouveau compte administrateur.")
            st.rerun()
