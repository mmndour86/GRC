import streamlit as st

from grc_core.db import get_connection, NIVEAU_TO_POIDS, nom_chapitre_affichage
from grc_core.scoring import compute_scores, NIVEAU_LABELS
from grc_core.ui_helpers import selecteur_entite, selecteur_controle
from grc_core import auth

st.set_page_config(page_title="Conformité PSSI-ES", page_icon="📋", layout="wide")

conn = get_connection()
user = auth.require_login(conn)
auth.render_user_badge(conn)
can_write = auth.can_write()

st.title("📋 Module de conformité PSSI-ES")
st.caption("Questionnaire des 228 règles — 30 objectifs — 11 chapitres")
if not can_write:
    st.caption("🔒 Mode lecture seule — vous ne pouvez pas modifier les réponses.")

entite_id = selecteur_entite(conn, key_prefix="pssi")
controle_id = selecteur_controle(conn, entite_id, key_prefix="pssi") if entite_id else None

if not controle_id:
    st.info("Sélectionnez (ou créez) une entité puis un contrôle pour accéder au questionnaire.")
    st.stop()

source_donnees = conn.execute("SELECT source_donnees FROM controles WHERE id=?", (controle_id,)).fetchone()["source_donnees"]
if source_donnees == "reconstitution":
    st.warning(
        "🔄 Ce contrôle reconstitue une évaluation DCSSI déjà publiée pour cette entité, à partir des "
        "scores moyens par objectif du rapport d'origine. Le niveau affiché pour chaque règle "
        "individuelle est une approximation — modifiez librement les réponses ci-dessous si vous "
        "disposez des données réelles règle par règle."
    )

scores = compute_scores(conn, controle_id)
g = scores["global"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Score global", f"{g['score']:.2f} / 5" if g["score"] is not None else "—")
c2.metric("Taux de maturité", f"{g['taux_conformite']:.1f} %" if g["taux_conformite"] is not None else "—")
c3.metric("Niveau CMMI", g["niveau_label"])
c4.metric("Règles évaluées", f"{g['n_repondues']} / {g['n_regles']}")

st.divider()

chapitres = sorted(set(r["chapitre_num"] for r in scores["regles"]))
tabs = st.tabs([f"Ch.{n}" for n in chapitres])

NIVEAU_OPTIONS = ["— Non renseigné —"] + list(NIVEAU_LABELS.values())
LABEL_TO_CODE = {v: k for k, v in NIVEAU_LABELS.items()}

for tab, chap_num in zip(tabs, chapitres):
    with tab:
        regles_chap = [r for r in scores["regles"] if r["chapitre_num"] == chap_num]
        chap_nom = nom_chapitre_affichage(chap_num, regles_chap[0]["chapitre_nom"])
        chap_score = scores["chapitres"][chap_num]["score"]
        score_txt = f"{chap_score:.2f}/5" if chap_score is not None else "non évalué"
        st.subheader(f"{chap_num}. {chap_nom} — maturité : {score_txt}")

        objectifs_chap = sorted(set(r["objectif_num"] for r in regles_chap))
        for onum in objectifs_chap:
            regles_obj = [r for r in regles_chap if r["objectif_num"] == onum]
            obj_score = scores["objectifs"][onum]["score"]
            obj_score_txt = f"{obj_score:.2f}/5" if obj_score is not None else "non évalué"
            with st.expander(f"Objectif {onum} — {regles_obj[0]['objectif_texte'][:110]}... ({obj_score_txt})"):
                for r in regles_obj:
                    cols = st.columns([1.2, 2, 1, 3])
                    cols[0].markdown(f"**{r['regle_id']}**")

                    niveau_actuel = NIVEAU_LABELS.get(r["niveau"], "— Non renseigné —") if r["niveau"] else "— Non renseigné —"
                    non_app_actuel = bool(r["non_applicable"])

                    with cols[1]:
                        niveau_choisi = st.selectbox(
                            "Niveau de maturité", NIVEAU_OPTIONS,
                            index=NIVEAU_OPTIONS.index(niveau_actuel) if niveau_actuel in NIVEAU_OPTIONS else 0,
                            key=f"niv_{controle_id}_{r['ref_id']}", label_visibility="collapsed",
                            disabled=non_app_actuel or not can_write,
                        )
                    with cols[2]:
                        non_applicable = st.checkbox(
                            "N/A", value=non_app_actuel, key=f"na_{controle_id}_{r['ref_id']}",
                            disabled=not can_write,
                        )
                    with cols[3]:
                        justification = st.text_input(
                            "Justification / commentaire", value=r["justification"] or r["commentaire"] or "",
                            key=f"just_{controle_id}_{r['ref_id']}", label_visibility="collapsed",
                            placeholder="Justificatif de non-applicabilité ou commentaire",
                            disabled=not can_write,
                        )

                    niveau_code = LABEL_TO_CODE.get(niveau_choisi) if niveau_choisi != "— Non renseigné —" else None

                    if can_write and ((niveau_code != r["niveau"]) or (non_applicable != non_app_actuel) or (justification != (r["justification"] or r["commentaire"] or ""))):
                        conn.execute(
                            """
                            INSERT INTO controle_reponses (controle_id, ref_id, niveau, non_applicable, justification)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(controle_id, ref_id) DO UPDATE SET
                                niveau=excluded.niveau, non_applicable=excluded.non_applicable, justification=excluded.justification
                            """,
                            (controle_id, r["ref_id"], niveau_code, int(non_applicable), justification),
                        )
                        conn.commit()
                        auth.log_action(conn, user["identifiant"], "modification_reponse",
                                         f"controle_id={controle_id} regle={r['regle_id']}")
                        st.rerun()

st.divider()
statut = st.selectbox(
    "Statut du contrôle",
    ["En cours", "Terminé"],
    index=["En cours", "Terminé"].index(
        conn.execute("SELECT statut FROM controles WHERE id=?", (controle_id,)).fetchone()["statut"]
    ),
    disabled=not can_write,
)
if st.button("Enregistrer le statut du contrôle", disabled=not can_write):
    conn.execute("UPDATE controles SET statut=? WHERE id=?", (statut, controle_id))
    conn.commit()
    auth.log_action(conn, user["identifiant"], "modification_statut_controle", f"controle_id={controle_id} statut={statut}")
    st.success("Statut mis à jour.")
