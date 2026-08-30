import pandas as pd
import streamlit as st

from grc_core.db import get_connection, nom_chapitre_affichage
from grc_core.scoring import compute_scores, NIVEAU_LABELS
from grc_core.risk_scoring import get_registre_risques, matrice_risques, synthese_portefeuille
from grc_core.ui_helpers import selecteur_entite, selecteur_controle
from grc_core import auth

st.set_page_config(page_title="Tableau de bord", page_icon="📊", layout="wide")

conn = get_connection()
user = auth.require_login(conn)
auth.render_user_badge(conn)

st.title("📊 Tableau de bord")

entite_id = selecteur_entite(conn, key_prefix="dash")
controle_id = selecteur_controle(conn, entite_id, key_prefix="dash") if entite_id else None

if not entite_id:
    st.info("Sélectionnez une entité pour afficher son tableau de bord.")
    st.stop()

tab_conf, tab_risk = st.tabs(["Conformité PSSI-ES", "Risques ISO 27005"])

# ---------------------------------------------------------------------------
with tab_conf:
    if not controle_id:
        st.info("Sélectionnez un contrôle pour afficher les indicateurs de conformité.")
    else:
        scores = compute_scores(conn, controle_id)
        g = scores["global"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Score global", f"{g['score']:.2f} / 5" if g["score"] is not None else "—")
        c2.metric("Taux de maturité", f"{g['taux_conformite']:.1f} %" if g["taux_conformite"] is not None else "—")
        c3.metric("Niveau CMMI", g["niveau_label"])
        c4.metric("Couverture de l'évaluation", f"{g['n_repondues'] + g['n_na']} / {g['n_regles']}")

        st.markdown("##### Maturité par chapitre")
        chap_df = pd.DataFrame([
            {"Chapitre": f"{n}. {nom_chapitre_affichage(n, c['nom'])}", "Score": c["score"] or 0}
            for n, c in sorted(scores["chapitres"].items())
        ]).set_index("Chapitre")
        st.bar_chart(chap_df, height=320)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("##### Répartition par niveau de maturité")
            rep = g["repartition_niveaux"]
            if rep:
                rep_df = pd.DataFrame(
                    [{"Niveau": NIVEAU_LABELS[k], "Nombre de règles": v} for k, v in rep.items()]
                ).set_index("Niveau")
                st.bar_chart(rep_df, height=280)
            else:
                st.caption("Aucune règle évaluée pour l'instant.")
        with col2:
            st.markdown("##### Chapitres les plus faibles")
            faibles = sorted(
                [(n, c) for n, c in scores["chapitres"].items() if c["score"] is not None],
                key=lambda x: x[1]["score"],
            )[:5]
            if faibles:
                st.dataframe(
                    pd.DataFrame([{"Chapitre": f"{n}. {nom_chapitre_affichage(n, c['nom'])}", "Score": c["score"]} for n, c in faibles]),
                    hide_index=True, use_container_width=True,
                )
            else:
                st.caption("Aucune donnée disponible.")

# ---------------------------------------------------------------------------
with tab_risk:
    risques = get_registre_risques(conn, entite_id)
    if not risques:
        st.info("Aucun risque enregistré pour cette entité. Utilisez le module « Registre des risques ISO27005 ».")
    else:
        synth = synthese_portefeuille(risques)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Risques recensés", len(risques))
        c2.metric("Risques critiques (résiduel)", synth["Critique"]["residuel"])
        c3.metric("Risques majeurs (résiduel)", synth["Majeur"]["residuel"])
        seuil_depasse = sum(1 for r in risques if r.get("depasse_appetence"))
        c4.metric("Dépassant le seuil d'appétence", seuil_depasse)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("##### Portefeuille de risques — brut vs résiduel")
            synth_df = pd.DataFrame([
                {"Niveau": n, "Brut": v["brut"], "Résiduel": v["residuel"]} for n, v in synth.items()
            ]).set_index("Niveau")
            st.bar_chart(synth_df, height=300)
        with col2:
            st.markdown("##### Heatmap des risques résiduels (vraisemblance × gravité)")
            mat = matrice_risques(risques, "vraisemblance_residuelle", "gravite_residuelle")
            heat_df = pd.DataFrame(mat).T
            heat_df.index.name = "Vraisemblance \\ Gravité"
            st.dataframe(heat_df.style.background_gradient(cmap="Reds", axis=None), use_container_width=True)

        st.markdown("##### Registre des risques (triés par niveau résiduel décroissant)")
        risques_tries = sorted(risques, key=lambda r: -(r["niveau_risque_residuel"] or 0))
        st.dataframe(
            pd.DataFrame(risques_tries)[[
                "code", "description_scenario", "niveau_qualitatif_brut", "niveau_qualitatif_residuel",
                "risque_acceptable", "proprietaire_risque",
            ]].rename(columns={
                "code": "ID", "description_scenario": "Scénario",
                "niveau_qualitatif_brut": "Niveau brut", "niveau_qualitatif_residuel": "Niveau résiduel",
                "risque_acceptable": "Acceptable ?", "proprietaire_risque": "Propriétaire",
            }),
            hide_index=True, use_container_width=True,
        )

        st.markdown("##### Suivi du plan de traitement")
        plan_rows = conn.execute("""
            SELECT rr.code AS risque, rt.mesure, rt.responsable, rt.echeance, rt.statut
            FROM risk_traitement rt JOIN risk_register rr ON rr.id = rt.risque_id
            WHERE rr.entite_id = ?
        """, (entite_id,)).fetchall()
        if plan_rows:
            plan_df = pd.DataFrame([dict(r) for r in plan_rows])
            st.dataframe(plan_df, hide_index=True, use_container_width=True)
            statut_counts = plan_df["statut"].value_counts()
            st.bar_chart(statut_counts)
        else:
            st.caption("Aucune mesure de traitement enregistrée.")
