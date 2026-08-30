"""
Calculs liés au registre des risques ISO/IEC 27005 :
niveau de risque = vraisemblance x gravité (échelle 1-4 x 1-4 => 1-16),
et classification qualitative (Faible / Modéré / Majeur / Critique).
"""
from grc_core.db import niveau_risque_qualitatif, SEUIL_APPETENCE


def enrich_risque(r):
    """Ajoute les niveaux de risque brut/résiduel (valeur + libellé qualitatif)
    à un enregistrement du registre des risques (dict ou sqlite3.Row)."""
    r = dict(r)
    vb, gb = r.get("vraisemblance_brute"), r.get("gravite_brute")
    vr, gr = r.get("vraisemblance_residuelle"), r.get("gravite_residuelle")

    r["niveau_risque_brut"] = vb * gb if (vb and gb) else None
    r["niveau_qualitatif_brut"] = niveau_risque_qualitatif(r["niveau_risque_brut"])

    r["niveau_risque_residuel"] = vr * gr if (vr and gr) else None
    r["niveau_qualitatif_residuel"] = niveau_risque_qualitatif(r["niveau_risque_residuel"])

    if r["niveau_risque_residuel"] is not None:
        r["depasse_appetence"] = r["niveau_risque_residuel"] > SEUIL_APPETENCE
    else:
        r["depasse_appetence"] = None
    return r


def get_registre_risques(conn, entite_id):
    rows = conn.execute(
        """
        SELECT rr.*, be.nom AS bien_essentiel_nom, bs.nom AS bien_support_nom
        FROM risk_register rr
        LEFT JOIN risk_biens_essentiels be ON be.id = rr.bien_essentiel_id
        LEFT JOIN risk_biens_supports bs ON bs.id = rr.bien_support_id
        WHERE rr.entite_id = ?
        ORDER BY rr.code
        """,
        (entite_id,),
    ).fetchall()
    return [enrich_risque(r) for r in rows]


def matrice_risques(risques, champ_vraisemblance="vraisemblance_brute", champ_gravite="gravite_brute"):
    """Construit une matrice 4x4 {vraisemblance: {gravite: count}} pour la heatmap."""
    matrice = {v: {g: 0 for g in range(1, 5)} for v in range(1, 5)}
    for r in risques:
        v, g = r.get(champ_vraisemblance), r.get(champ_gravite)
        if v and g:
            matrice[v][g] += 1
    return matrice


def synthese_portefeuille(risques):
    niveaux = ["Faible", "Modéré", "Majeur", "Critique"]
    out = {n: {"brut": 0, "residuel": 0} for n in niveaux}
    for r in risques:
        if r["niveau_qualitatif_brut"]:
            out[r["niveau_qualitatif_brut"]]["brut"] += 1
        if r["niveau_qualitatif_residuel"]:
            out[r["niveau_qualitatif_residuel"]]["residuel"] += 1
    return out
