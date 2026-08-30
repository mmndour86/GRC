import pandas as pd
import streamlit as st

from grc_core.db import get_connection
from grc_core import auth

st.set_page_config(page_title="Administration", page_icon="🔐", layout="wide")

conn = get_connection()
user = auth.require_login(conn)
auth.render_user_badge(conn)
auth.require_role("administrateur")

st.title("🔐 Administration de la plateforme")
st.caption("Réservé au rôle administrateur — gestion des comptes et journal d'activité")

tab_users, tab_new, tab_journal = st.tabs(
    ["👥 Utilisateurs", "➕ Créer un utilisateur", "📜 Journal d'activité"]
)

# ---------------------------------------------------------------------------
# Liste des utilisateurs
# ---------------------------------------------------------------------------
with tab_users:
    utilisateurs = auth.lister_utilisateurs(conn)
    if not utilisateurs:
        st.info("Aucun utilisateur.")
    else:
        for u in utilisateurs:
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([2.2, 1.8, 1.3, 1.3, 1.4])
                c1.markdown(f"**{u['nom_complet'] or u['identifiant']}**  \n`{u['identifiant']}`")

                nouveau_role = c2.selectbox(
                    "Rôle", auth.ROLES,
                    index=auth.ROLES.index(u["role"]) if u["role"] in auth.ROLES else 0,
                    format_func=lambda r: auth.ROLE_LABELS.get(r, r),
                    key=f"role_{u['id']}",
                    disabled=(u["identifiant"] == user["identifiant"]),
                    label_visibility="collapsed",
                )
                if nouveau_role != u["role"]:
                    auth.definir_role(conn, u["id"], nouveau_role, acteur=user["identifiant"])
                    st.success(f"Rôle de « {u['identifiant']} » mis à jour → {auth.ROLE_LABELS[nouveau_role]}.")
                    st.rerun()

                c3.caption(f"Créé le {u['date_creation'] or '—'}")
                c3.caption(f"Dernière connexion : {u['derniere_connexion'] or 'jamais'}")

                if u["doit_changer_mdp"]:
                    c4.caption("🔑 Doit changer son mot de passe")
                if u["actif"]:
                    if c5.button("Désactiver", key=f"deact_{u['id']}", disabled=(u["identifiant"] == user["identifiant"])):
                        auth.definir_statut(conn, u["id"], False, acteur=user["identifiant"])
                        st.rerun()
                else:
                    st.caption("⛔ Compte désactivé")
                    if c5.button("Réactiver", key=f"react_{u['id']}"):
                        auth.definir_statut(conn, u["id"], True, acteur=user["identifiant"])
                        st.rerun()

        st.caption(
            "Vous ne pouvez pas modifier votre propre rôle ni désactiver votre propre compte "
            "(pour éviter de vous verrouiller hors de la plateforme)."
        )

# ---------------------------------------------------------------------------
# Création d'un utilisateur
# ---------------------------------------------------------------------------
with tab_new:
    st.markdown("Le mot de passe saisi ici est **temporaire** : l'utilisateur devra le changer à sa première connexion.")
    with st.form("form_new_user"):
        c1, c2 = st.columns(2)
        identifiant = c1.text_input("Identifiant de connexion")
        nom_complet = c2.text_input("Nom complet")
        role = st.selectbox("Rôle", auth.ROLES, format_func=lambda r: auth.ROLE_LABELS.get(r, r))
        mdp_propose = auth.generer_mot_de_passe_initial()
        st.text_input("Mot de passe initial (généré, modifiable)", value=mdp_propose, key="mdp_initial_new_user")
        submit = st.form_submit_button("Créer l'utilisateur", type="primary")

    if submit:
        identifiant = identifiant.strip()
        mdp = st.session_state.get("mdp_initial_new_user", mdp_propose)
        if not identifiant:
            st.error("L'identifiant est obligatoire.")
        elif len(mdp) < 8:
            st.error("Le mot de passe doit contenir au moins 8 caractères.")
        elif conn.execute("SELECT id FROM utilisateurs WHERE identifiant=?", (identifiant,)).fetchone():
            st.error(f"L'identifiant « {identifiant} » existe déjà.")
        else:
            auth.creer_utilisateur(conn, identifiant, nom_complet, mdp, role, cree_par=user["identifiant"])
            st.success(
                f"Utilisateur « {identifiant} » créé avec le rôle {auth.ROLE_LABELS[role]}. "
                f"Communiquez-lui son mot de passe initial : `{mdp}` — il devra le changer à sa "
                "première connexion. Ce mot de passe ne sera plus affiché ensuite."
            )

# ---------------------------------------------------------------------------
# Journal d'activité
# ---------------------------------------------------------------------------
with tab_journal:
    n_lignes = st.slider("Nombre d'entrées à afficher", 20, 500, 100, step=20)
    rows = conn.execute(
        "SELECT horodatage, utilisateur, action, details FROM journal_activite "
        "ORDER BY id DESC LIMIT ?",
        (n_lignes,),
    ).fetchall()
    if not rows:
        st.info("Aucune activité enregistrée pour l'instant.")
    else:
        df = pd.DataFrame([dict(r) for r in rows]).rename(columns={
            "horodatage": "Horodatage", "utilisateur": "Utilisateur",
            "action": "Action", "details": "Détails",
        })
        st.dataframe(df, hide_index=True, use_container_width=True)
