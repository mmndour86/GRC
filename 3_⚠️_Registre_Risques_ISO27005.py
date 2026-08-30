import pandas as pd
import streamlit as st

from grc_core.db import (
    get_connection, ECHELLE_DICT, ECHELLE_GRAVITE, ECHELLE_VRAISEMBLANCE, SEUIL_APPETENCE,
)
from grc_core.risk_scoring import get_registre_risques, enrich_risque
from grc_core.ui_helpers import selecteur_entite
from grc_core import auth

st.set_page_config(page_title="Registre des risques ISO 27005", page_icon="⚠️", layout="wide")

conn = get_connection()
user = auth.require_login(conn)
auth.render_user_badge(conn)
can_write = auth.can_write()

st.title("⚠️ Registre des risques — ISO/IEC 27005")
if not can_write:
    st.caption("🔒 Mode lecture seule — vous ne pouvez pas modifier le registre.")

entite_id = selecteur_entite(conn, key_prefix="risk")
if not entite_id:
    st.info("Sélectionnez (ou créez) une entité pour gérer son registre des risques.")
    st.stop()

with st.expander("ℹ️ Échelles ISO/IEC 27005 utilisées"):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Besoins de sécurité (DICT) — 1 à 4**")
        for v, l in ECHELLE_DICT.items():
            st.markdown(f"- **{v}** : {l}")
    with c2:
        st.markdown("**Vraisemblance / Gravité — 1 à 4**")
        for v, l in ECHELLE_VRAISEMBLANCE.items():
            st.markdown(f"- **{v}** : {l} (vraisemblance) / {ECHELLE_GRAVITE[v]} (gravité)")
    st.markdown(
        f"**Niveau de risque = vraisemblance × gravité** (1 à 16) — Faible (1-4), Modéré (5-8), "
        f"Majeur (9-12), Critique (13-16). Seuil d'appétence au risque résiduel : **{SEUIL_APPETENCE}**."
    )

tab_be, tab_bs, tab_mv, tab_reg, tab_plan = st.tabs(
    ["Biens essentiels", "Biens supports", "Menaces & vulnérabilités", "Appréciation des risques", "Plan de traitement"]
)

# ---------------------------------------------------------------------------
# Biens essentiels
# ---------------------------------------------------------------------------
with tab_be:
    st.caption("Informations et processus métier — cotation des besoins de sécurité (DICT)")
    rows = conn.execute("SELECT * FROM risk_biens_essentiels WHERE entite_id=? ORDER BY code", (entite_id,)).fetchall()
    df = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame(
        columns=["id", "code", "nom", "description", "processus", "proprietaire", "d", "i", "c", "t", "niveau_classification", "commentaire"]
    )
    df = df.drop(columns=["entite_id"], errors="ignore")
    edited = st.data_editor(
        df, num_rows="dynamic", use_container_width=True, hide_index=True, key="be_editor",
        disabled=not can_write,
        column_config={
            "id": None,
            "d": st.column_config.NumberColumn("D", min_value=1, max_value=4),
            "i": st.column_config.NumberColumn("I", min_value=1, max_value=4),
            "c": st.column_config.NumberColumn("C", min_value=1, max_value=4),
            "t": st.column_config.NumberColumn("T", min_value=1, max_value=4),
            "niveau_classification": st.column_config.NumberColumn("Niveau classif.", min_value=1, max_value=4),
        },
    )
    if st.button("💾 Enregistrer les biens essentiels", disabled=not can_write):
        conn.execute("DELETE FROM risk_biens_essentiels WHERE entite_id=?", (entite_id,))
        for _, row in edited.iterrows():
            if pd.isna(row.get("code")) or not str(row.get("code")).strip():
                continue
            conn.execute(
                "INSERT INTO risk_biens_essentiels (entite_id, code, nom, description, processus, proprietaire, d, i, c, t, niveau_classification, commentaire) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (entite_id, row.get("code"), row.get("nom"), row.get("description"), row.get("processus"),
                 row.get("proprietaire"), row.get("d"), row.get("i"), row.get("c"), row.get("t"),
                 row.get("niveau_classification"), row.get("commentaire")),
            )
        conn.commit()
        auth.log_action(conn, user["identifiant"], "modification_biens_essentiels", f"entite_id={entite_id}")
        st.success("Biens essentiels enregistrés.")
        st.rerun()

# ---------------------------------------------------------------------------
# Biens supports
# ---------------------------------------------------------------------------
with tab_bs:
    st.caption("Matériels, logiciels, réseaux, personnels, sites et organisation portant les biens essentiels")
    be_rows = conn.execute("SELECT id, code FROM risk_biens_essentiels WHERE entite_id=?", (entite_id,)).fetchall()
    be_codes = [r["code"] for r in be_rows]
    rows = conn.execute("""
        SELECT bs.id, bs.code, bs.nom, bs.type_bien, be.code AS bien_essentiel_code,
               bs.proprietaire, bs.localisation, bs.description
        FROM risk_biens_supports bs LEFT JOIN risk_biens_essentiels be ON be.id = bs.bien_essentiel_id
        WHERE bs.entite_id=? ORDER BY bs.code
    """, (entite_id,)).fetchall()
    df = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame(
        columns=["id", "code", "nom", "type_bien", "bien_essentiel_code", "proprietaire", "localisation", "description"]
    )
    edited = st.data_editor(
        df, num_rows="dynamic", use_container_width=True, hide_index=True, key="bs_editor",
        disabled=not can_write,
        column_config={
            "id": None,
            "bien_essentiel_code": st.column_config.SelectboxColumn("Bien essentiel associé", options=be_codes),
            "type_bien": st.column_config.SelectboxColumn(
                "Type de bien", options=["Matériel", "Logiciel", "Réseau", "Personnel", "Site", "Organisation"]
            ),
        },
    )
    if st.button("💾 Enregistrer les biens supports", disabled=not can_write):
        be_id_by_code = {r["code"]: r["id"] for r in be_rows}
        conn.execute("DELETE FROM risk_biens_supports WHERE entite_id=?", (entite_id,))
        for _, row in edited.iterrows():
            if pd.isna(row.get("code")) or not str(row.get("code")).strip():
                continue
            conn.execute(
                "INSERT INTO risk_biens_supports (entite_id, code, nom, type_bien, bien_essentiel_id, proprietaire, localisation, description) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (entite_id, row.get("code"), row.get("nom"), row.get("type_bien"),
                 be_id_by_code.get(row.get("bien_essentiel_code")), row.get("proprietaire"),
                 row.get("localisation"), row.get("description")),
            )
        conn.commit()
        auth.log_action(conn, user["identifiant"], "modification_biens_supports", f"entite_id={entite_id}")
        st.success("Biens supports enregistrés.")
        st.rerun()

# ---------------------------------------------------------------------------
# Menaces & vulnérabilités (catalogue global)
# ---------------------------------------------------------------------------
with tab_mv:
    st.caption("Catalogue de référence des sources de menaces et vulnérabilités (partagé entre entités)")
    rows = conn.execute("SELECT * FROM risk_menaces_vuln ORDER BY code").fetchall()
    df = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame(
        columns=["id", "code", "source_menace", "menace", "vulnerabilite", "type_bien_support"]
    )
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, hide_index=True, key="mv_editor",
                             disabled=not can_write, column_config={"id": None})
    if st.button("💾 Enregistrer le catalogue menaces/vulnérabilités", disabled=not can_write):
        conn.execute("DELETE FROM risk_menaces_vuln")
        for _, row in edited.iterrows():
            if pd.isna(row.get("code")) or not str(row.get("code")).strip():
                continue
            conn.execute(
                "INSERT INTO risk_menaces_vuln (code, source_menace, menace, vulnerabilite, type_bien_support) VALUES (?, ?, ?, ?, ?)",
                (row.get("code"), row.get("source_menace"), row.get("menace"), row.get("vulnerabilite"), row.get("type_bien_support")),
            )
        conn.commit()
        auth.log_action(conn, user["identifiant"], "modification_catalogue_menaces", "")
        st.success("Catalogue mis à jour.")
        st.rerun()

# ---------------------------------------------------------------------------
# Appréciation des risques
# ---------------------------------------------------------------------------
with tab_reg:
    st.caption("Registre des scénarios de risque — cotation brute et résiduelle (ISO/IEC 27005)")
    be_rows = conn.execute("SELECT id, code FROM risk_biens_essentiels WHERE entite_id=?", (entite_id,)).fetchall()
    bs_rows = conn.execute("SELECT id, code FROM risk_biens_supports WHERE entite_id=?", (entite_id,)).fetchall()
    be_codes, bs_codes = [r["code"] for r in be_rows], [r["code"] for r in bs_rows]

    risques = get_registre_risques(conn, entite_id)
    df = pd.DataFrame(risques) if risques else pd.DataFrame(columns=[
        "id", "code", "bien_essentiel_nom", "bien_support_nom", "critere_dict", "source_menace", "menace",
        "vulnerabilite", "description_scenario", "vraisemblance_brute", "gravite_brute", "mesures_existantes",
        "vraisemblance_residuelle", "gravite_residuelle", "risque_acceptable", "proprietaire_risque",
    ])
    display_cols = [
        "code", "description_scenario", "critere_dict", "source_menace", "menace", "vulnerabilite",
        "vraisemblance_brute", "gravite_brute", "niveau_risque_brut", "niveau_qualitatif_brut",
        "mesures_existantes", "vraisemblance_residuelle", "gravite_residuelle",
        "niveau_risque_residuel", "niveau_qualitatif_residuel", "risque_acceptable", "proprietaire_risque",
    ]
    for c in display_cols:
        if c not in df.columns:
            df[c] = None
    st.dataframe(
        df[display_cols].rename(columns={
            "code": "ID", "description_scenario": "Scénario", "critere_dict": "Critère DICT",
            "source_menace": "Source", "menace": "Menace", "vulnerabilite": "Vulnérabilité",
            "vraisemblance_brute": "V. brute", "gravite_brute": "G. brute",
            "niveau_risque_brut": "Niv. brut", "niveau_qualitatif_brut": "Qualif. brut",
            "mesures_existantes": "Mesures existantes",
            "vraisemblance_residuelle": "V. résiduelle", "gravite_residuelle": "G. résiduelle",
            "niveau_risque_residuel": "Niv. résiduel", "niveau_qualitatif_residuel": "Qualif. résiduel",
            "risque_acceptable": "Acceptable ?", "proprietaire_risque": "Propriétaire",
        }),
        use_container_width=True, hide_index=True,
    )

    st.markdown("##### ➕ Ajouter un scénario de risque")
    if not can_write:
        st.caption("🔒 Mode lecture seule — l'ajout de risque est réservé aux rôles auditeur/administrateur.")
    with st.form("nouveau_risque"):
        c1, c2, c3 = st.columns(3)
        code = c1.text_input("Code (ex. R-03)")
        be_code = c2.selectbox("Bien essentiel concerné", ["—"] + be_codes)
        bs_code = c3.selectbox("Bien support concerné", ["—"] + bs_codes)
        critere = c1.selectbox("Critère DICT affecté", ["Disponibilité", "Intégrité", "Confidentialité", "Traçabilité"])
        source = c2.text_input("Source de menace")
        menace = c3.text_input("Menace")
        vuln = st.text_input("Vulnérabilité exploitée")
        desc = st.text_area("Description du scénario de risque")
        c4, c5, c6, c7 = st.columns(4)
        v_brute = c4.selectbox("Vraisemblance brute", [1, 2, 3, 4])
        g_brute = c5.selectbox("Gravité brute", [1, 2, 3, 4])
        v_res = c6.selectbox("Vraisemblance résiduelle", [1, 2, 3, 4])
        g_res = c7.selectbox("Gravité résiduelle", [1, 2, 3, 4])
        mesures = st.text_area("Mesures de sécurité existantes / prévues")
        c8, c9 = st.columns(2)
        acceptable = c8.selectbox("Risque acceptable ?", ["Oui", "Non"])
        proprietaire = c9.text_input("Propriétaire du risque")

        if st.form_submit_button("Ajouter le risque", disabled=not can_write):
            be_id_map = {r["code"]: r["id"] for r in be_rows}
            bs_id_map = {r["code"]: r["id"] for r in bs_rows}
            conn.execute(
                "INSERT INTO risk_register (entite_id, code, bien_essentiel_id, bien_support_id, critere_dict, "
                "source_menace, menace, vulnerabilite, description_scenario, vraisemblance_brute, gravite_brute, "
                "mesures_existantes, vraisemblance_residuelle, gravite_residuelle, risque_acceptable, proprietaire_risque) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (entite_id, code, be_id_map.get(be_code), bs_id_map.get(bs_code), critere, source, menace, vuln,
                 desc, v_brute, g_brute, mesures, v_res, g_res, acceptable, proprietaire),
            )
            conn.commit()
            auth.log_action(conn, user["identifiant"], "ajout_risque", f"entite_id={entite_id} code={code}")
            st.success(f"Risque {code} ajouté.")
            st.rerun()

# ---------------------------------------------------------------------------
# Plan de traitement
# ---------------------------------------------------------------------------
with tab_plan:
    st.caption("Suivi des mesures de traitement associées aux risques du registre")
    risques = conn.execute("SELECT id, code FROM risk_register WHERE entite_id=?", (entite_id,)).fetchall()
    risque_codes = {r["code"]: r["id"] for r in risques}
    rows = conn.execute("""
        SELECT rt.id, rr.code AS risque_code, rt.strategie, rt.mesure, rt.type_mesure, rt.responsable,
               rt.echeance, rt.cout_estime, rt.statut
        FROM risk_traitement rt JOIN risk_register rr ON rr.id = rt.risque_id
        WHERE rr.entite_id = ? ORDER BY rr.code
    """, (entite_id,)).fetchall()
    df = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame(columns=[
        "id", "risque_code", "strategie", "mesure", "type_mesure", "responsable", "echeance", "cout_estime", "statut"
    ])
    edited = st.data_editor(
        df, num_rows="dynamic", use_container_width=True, hide_index=True, key="plan_editor",
        disabled=not can_write,
        column_config={
            "id": None,
            "risque_code": st.column_config.SelectboxColumn("Risque", options=list(risque_codes.keys())),
            "strategie": st.column_config.SelectboxColumn("Stratégie", options=["Éviter", "Réduire", "Transférer", "Accepter"]),
            "statut": st.column_config.SelectboxColumn("Statut", options=["À planifier", "En cours", "Réalisé", "Abandonné"]),
            "cout_estime": st.column_config.NumberColumn("Coût estimé (FCFA)"),
        },
    )
    if st.button("💾 Enregistrer le plan de traitement", disabled=not can_write):
        conn.execute(
            "DELETE FROM risk_traitement WHERE risque_id IN (SELECT id FROM risk_register WHERE entite_id=?)",
            (entite_id,),
        )
        for _, row in edited.iterrows():
            rid = risque_codes.get(row.get("risque_code"))
            if rid is None:
                continue
            conn.execute(
                "INSERT INTO risk_traitement (risque_id, strategie, mesure, type_mesure, responsable, echeance, cout_estime, statut) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (rid, row.get("strategie"), row.get("mesure"), row.get("type_mesure"), row.get("responsable"),
                 row.get("echeance"), row.get("cout_estime"), row.get("statut")),
            )
        conn.commit()
        auth.log_action(conn, user["identifiant"], "modification_plan_traitement", f"entite_id={entite_id}")
        st.success("Plan de traitement enregistré.")
        st.rerun()
