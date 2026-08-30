import pandas as pd
import streamlit as st

from grc_core.db import get_connection
from grc_core import auth

st.set_page_config(page_title="Mapping référentiels", page_icon="🔗", layout="wide")

conn = get_connection()
user = auth.require_login(conn)
auth.render_user_badge(conn)
can_write = auth.can_write()

st.title("🔗 Correspondance multi-référentiels")
st.caption("PSSI-ES ↔ ISO/IEC 27001 ↔ NIST CSF ↔ DORA")

st.info(
    "Cette table de correspondance est établie **au niveau des 11 chapitres PSSI-ES** — c'est une "
    "proposition initiale destinée à être validée et affinée avec vos équipes conformité. Elle permet "
    "de visualiser la couverture croisée des référentiels sans dupliquer un questionnaire complet pour "
    "chacun d'eux, conformément au cadrage retenu pour ce prototype."
)

rows = conn.execute("SELECT * FROM referentiel_mapping ORDER BY chapitre_num").fetchall()
df = pd.DataFrame([dict(r) for r in rows])
df = df.rename(columns={
    "chapitre_num": "N° chapitre", "chapitre_nom": "Chapitre PSSI-ES",
    "iso27001": "ISO/IEC 27001", "nist_csf": "NIST CSF", "dora": "DORA",
})

colonnes_verrouillees = ["N° chapitre", "Chapitre PSSI-ES"] if can_write else list(df.columns)
edited = st.data_editor(
    df, use_container_width=True, hide_index=True, num_rows="fixed",
    disabled=colonnes_verrouillees,
    key="mapping_editor",
)

if st.button("💾 Enregistrer les modifications de la table de correspondance", disabled=not can_write):
    for _, row in edited.iterrows():
        conn.execute(
            "UPDATE referentiel_mapping SET iso27001=?, nist_csf=?, dora=? WHERE chapitre_num=?",
            (row["ISO/IEC 27001"], row["NIST CSF"], row["DORA"], int(row["N° chapitre"])),
        )
    conn.commit()
    auth.log_action(conn, user["identifiant"], "modification_mapping", "")
    st.success("Table de correspondance mise à jour. Les rapports générés utiliseront désormais cette version.")

st.divider()
st.subheader("Couverture par référentiel")
n_chap = len(df)
c1, c2, c3 = st.columns(3)
c1.metric("Chapitres PSSI-ES cartographiés vers ISO 27001", f"{df['ISO/IEC 27001'].notna().sum()} / {n_chap}")
c2.metric("Chapitres PSSI-ES cartographiés vers NIST CSF", f"{df['NIST CSF'].notna().sum()} / {n_chap}")
c3.metric("Chapitres PSSI-ES cartographiés vers DORA", f"{df['DORA'].notna().sum()} / {n_chap}")
