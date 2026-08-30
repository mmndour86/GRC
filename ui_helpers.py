"""Fonctions d'interface partagées entre les pages Streamlit (sélecteurs
d'entité / de contrôle, création rapide)."""
from datetime import date

import streamlit as st

from grc_core import auth


def selecteur_entite(conn, key_prefix=""):
    entites = conn.execute("SELECT id, nom, secteur FROM entites ORDER BY nom").fetchall()
    options = {f"{e['nom']} ({e['secteur'] or 'secteur non renseigné'})": e["id"] for e in entites}
    can_write = auth.can_write()

    col1, col2 = st.columns([3, 1])
    with col1:
        choix = st.selectbox("Entité", ["— Sélectionner —"] + list(options.keys()), key=f"{key_prefix}_ent_sel")
    with col2:
        with st.popover("➕ Nouvelle entité", disabled=not can_write):
            nom = st.text_input("Nom de l'entité", key=f"{key_prefix}_new_ent_nom")
            secteur = st.text_input("Secteur", key=f"{key_prefix}_new_ent_secteur")
            if st.button("Créer", key=f"{key_prefix}_new_ent_btn") and nom:
                conn.execute(
                    "INSERT INTO entites (nom, secteur, date_creation) VALUES (?, ?, ?)",
                    (nom, secteur, str(date.today())),
                )
                conn.commit()
                user = auth.current_user()
                auth.log_action(conn, user["identifiant"] if user else "?", "creation_entite", nom)
                st.success(f"Entité « {nom} » créée.")
                st.rerun()

    if choix == "— Sélectionner —":
        return None
    return options[choix]


def selecteur_controle(conn, entite_id, key_prefix=""):
    if entite_id is None:
        return None
    can_write = auth.can_write()
    controles = conn.execute(
        "SELECT id, date_controle, responsable, statut, source_donnees FROM controles WHERE entite_id = ? ORDER BY date_controle DESC",
        (entite_id,),
    ).fetchall()
    options = {}
    for c in controles:
        tag = " 🔄 reconstitution" if c["source_donnees"] == "reconstitution" else ""
        options[f"{c['date_controle']} — {c['responsable'] or 'sans responsable'} ({c['statut']}){tag}"] = c["id"]

    col1, col2 = st.columns([3, 1])
    with col1:
        choix = st.selectbox("Contrôle", ["— Sélectionner —"] + list(options.keys()), key=f"{key_prefix}_ctrl_sel")
    with col2:
        with st.popover("➕ Nouveau contrôle", disabled=not can_write):
            responsable = st.text_input("Responsable du contrôle", key=f"{key_prefix}_new_ctrl_resp")
            if st.button("Créer", key=f"{key_prefix}_new_ctrl_btn"):
                conn.execute(
                    "INSERT INTO controles (entite_id, date_controle, responsable, statut) VALUES (?, ?, ?, ?)",
                    (entite_id, str(date.today()), responsable, "En cours"),
                )
                conn.commit()
                user = auth.current_user()
                auth.log_action(conn, user["identifiant"] if user else "?", "creation_controle",
                                 f"entite_id={entite_id} responsable={responsable}")
                st.success("Contrôle créé.")
                st.rerun()

    if choix == "— Sélectionner —":
        return None
    return options[choix]
