import os
import shutil
import subprocess
import tempfile

import streamlit as st

from grc_core.db import get_connection
from grc_core.scoring import compute_scores
from grc_core.report_generator import generer_rapport
from grc_core.ui_helpers import selecteur_entite, selecteur_controle
from grc_core import auth

st.set_page_config(page_title="Génération de rapport", page_icon="📄", layout="wide")

conn = get_connection()
user = auth.require_login(conn)
auth.render_user_badge(conn)

st.title("📄 Génération automatique du rapport de contrôle")
st.caption("Rapport structuré sur le modèle des rapports ANAQ-Sup / COUD fournis en exemple")

entite_id = selecteur_entite(conn, key_prefix="rep")
controle_id = selecteur_controle(conn, entite_id, key_prefix="rep") if entite_id else None

if not controle_id:
    st.info("Sélectionnez une entité et un contrôle pour générer son rapport.")
    st.stop()

source_donnees = conn.execute("SELECT source_donnees FROM controles WHERE id=?", (controle_id,)).fetchone()["source_donnees"]
if source_donnees == "reconstitution":
    st.warning(
        "🔄 Ce contrôle reconstitue une évaluation DCSSI déjà publiée. Le rapport généré portera un "
        "bandeau signalant que le détail règle par règle est une approximation (voir le module "
        "Conformité PSSI-ES pour le corriger si vous disposez des données d'origine)."
    )

scores = compute_scores(conn, controle_id)
g = scores["global"]

st.markdown("##### Aperçu avant génération")
c1, c2, c3 = st.columns(3)
c1.metric("Score global", f"{g['score']:.2f} / 5" if g["score"] is not None else "—")
c2.metric("Niveau CMMI", g["niveau_label"])
c3.metric("Couverture", f"{g['n_repondues'] + g['n_na']} / {g['n_regles']} règles traitées")

if g["n_non_renseignees"] > 0:
    st.warning(
        f"{g['n_non_renseignees']} règle(s) ne sont pas encore renseignées. Le rapport peut être généré "
        "à tout moment (contrôle partiel), mais sera plus représentatif une fois le questionnaire complété."
    )

st.divider()

if st.button("🚀 Générer le rapport", type="primary"):
    with st.spinner("Génération du rapport en cours..."):
        entite = conn.execute("SELECT nom FROM entites WHERE id=?", (entite_id,)).fetchone()
        nom_fichier = f"Rapport_Evaluation_PSSI-ES_{entite['nom'].replace(' ', '_')}"
        tmpdir = tempfile.mkdtemp()
        docx_path = os.path.join(tmpdir, f"{nom_fichier}.docx")

        try:
            generer_rapport(conn, controle_id, docx_path)
            st.session_state["dernier_rapport_docx"] = docx_path
            st.session_state["dernier_rapport_nom"] = nom_fichier

            # Tentative de conversion PDF (nécessite LibreOffice/soffice installé)
            pdf_path = None
            soffice_bin = shutil.which("soffice") or shutil.which("libreoffice")
            if soffice_bin:
                subprocess.run(
                    [soffice_bin, "--headless", "--convert-to", "pdf", "--outdir", tmpdir, docx_path],
                    check=True, capture_output=True, timeout=120,
                )
                candidate = os.path.join(tmpdir, f"{nom_fichier}.pdf")
                if os.path.exists(candidate):
                    pdf_path = candidate
            st.session_state["dernier_rapport_pdf"] = pdf_path

            auth.log_action(conn, user["identifiant"], "generation_rapport",
                             f"entite_id={entite_id} controle_id={controle_id}")
            st.success("Rapport généré avec succès.")
        except Exception as e:
            st.error(f"Erreur lors de la génération du rapport : {e}")

if st.session_state.get("dernier_rapport_docx") and os.path.exists(st.session_state["dernier_rapport_docx"]):
    st.divider()
    st.markdown("##### Télécharger le rapport")
    col1, col2 = st.columns(2)
    with open(st.session_state["dernier_rapport_docx"], "rb") as f:
        col1.download_button(
            "⬇️ Télécharger en Word (.docx)", f,
            file_name=f"{st.session_state['dernier_rapport_nom']}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    if st.session_state.get("dernier_rapport_pdf"):
        with open(st.session_state["dernier_rapport_pdf"], "rb") as f:
            col2.download_button(
                "⬇️ Télécharger en PDF", f,
                file_name=f"{st.session_state['dernier_rapport_nom']}.pdf",
                mime="application/pdf",
            )
    else:
        col2.caption(
            "Export PDF indisponible sur ce poste (LibreOffice non détecté). Ouvrez le fichier Word "
            "et utilisez « Enregistrer sous » → PDF, ou installez LibreOffice pour activer l'export "
            "PDF automatique."
        )

st.divider()
with st.expander("ℹ️ Contenu du rapport généré"):
    st.markdown(
        """
Le rapport reprend la structure des modèles ANAQ-Sup / COUD fournis :

- Page de garde et sommaire (champ table des matières à mettre à jour dans Word) ;
- Résumé exécutif : constat central généré automatiquement à partir des chapitres les plus faibles/forts,
  chiffres clés et priorités d'action ;
- Contexte, objectifs de la mission et méthodologie ;
- Synthèse des résultats globaux (graphiques + tableaux par chapitre et par objectif) ;
- Constats détaillés par chapitre, avec correspondance ISO 27001 / NIST CSF / DORA ;
- Plan d'action de mise en œuvre priorisé sur les objectifs les plus faibles ;
- Annexe de synthèse des risques ISO/IEC 27005 si un registre des risques existe pour l'entité ;
- Conclusion.

**À propos des recommandations** : seul l'objectif 1 reprend une recommandation *officielle* issue de
votre classeur Excel. Les recommandations des 29 autres objectifs sont des **propositions générées par
la plateforme**, clairement étiquetées comme telles dans le rapport (« proposée, à valider »). Faites-les
valider par vos équipes conformité avant toute diffusion officielle.
        """
    )
