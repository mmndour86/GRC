"""Tests unitaires des calculs de risque ISO/IEC 27005 (grc_core.risk_scoring)."""
from grc_core.risk_scoring import enrich_risque, matrice_risques, synthese_portefeuille
from grc_core.db import niveau_risque_qualitatif, SEUIL_APPETENCE


def test_niveau_risque_qualitatif_thresholds():
    assert niveau_risque_qualitatif(None) is None
    assert niveau_risque_qualitatif(1) == "Faible"
    assert niveau_risque_qualitatif(4) == "Faible"
    assert niveau_risque_qualitatif(5) == "Modéré"
    assert niveau_risque_qualitatif(8) == "Modéré"
    assert niveau_risque_qualitatif(9) == "Majeur"
    assert niveau_risque_qualitatif(12) == "Majeur"
    assert niveau_risque_qualitatif(13) == "Critique"
    assert niveau_risque_qualitatif(16) == "Critique"


def test_enrich_risque_calcule_niveaux_brut_et_residuel():
    r = {
        "vraisemblance_brute": 4, "gravite_brute": 4,
        "vraisemblance_residuelle": 2, "gravite_residuelle": 2,
    }
    enriched = enrich_risque(r)
    assert enriched["niveau_risque_brut"] == 16
    assert enriched["niveau_qualitatif_brut"] == "Critique"
    assert enriched["niveau_risque_residuel"] == 4
    assert enriched["niveau_qualitatif_residuel"] == "Faible"
    assert enriched["depasse_appetence"] is False


def test_enrich_risque_depasse_appetence():
    r = {
        "vraisemblance_brute": 4, "gravite_brute": 4,
        "vraisemblance_residuelle": 3, "gravite_residuelle": 3,
    }
    enriched = enrich_risque(r)
    assert enriched["niveau_risque_residuel"] == 9
    assert enriched["niveau_risque_residuel"] > SEUIL_APPETENCE
    assert enriched["depasse_appetence"] is True


def test_enrich_risque_valeurs_manquantes():
    r = {"vraisemblance_brute": None, "gravite_brute": 3,
         "vraisemblance_residuelle": None, "gravite_residuelle": None}
    enriched = enrich_risque(r)
    assert enriched["niveau_risque_brut"] is None
    assert enriched["niveau_qualitatif_brut"] is None
    assert enriched["depasse_appetence"] is None


def test_matrice_risques_compte_par_cellule():
    risques = [
        {"vraisemblance_brute": 1, "gravite_brute": 1},
        {"vraisemblance_brute": 1, "gravite_brute": 1},
        {"vraisemblance_brute": 4, "gravite_brute": 4},
        {"vraisemblance_brute": None, "gravite_brute": 2},  # ignoré (valeur manquante)
    ]
    mat = matrice_risques(risques, "vraisemblance_brute", "gravite_brute")
    assert mat[1][1] == 2
    assert mat[4][4] == 1
    assert mat[2][2] == 0
    # Toutes les cellules 1..4 x 1..4 doivent exister même à zéro.
    assert set(mat.keys()) == {1, 2, 3, 4}
    for v in mat:
        assert set(mat[v].keys()) == {1, 2, 3, 4}


def test_synthese_portefeuille_brut_vs_residuel():
    risques = [
        # brut 4x4=16 -> Critique ; résiduel 1x1=1 -> Faible
        enrich_risque({"vraisemblance_brute": 4, "gravite_brute": 4,
                        "vraisemblance_residuelle": 1, "gravite_residuelle": 1}),
        # brut 3x3=9 -> Majeur ; résiduel 2x2=4 -> Faible
        enrich_risque({"vraisemblance_brute": 3, "gravite_brute": 3,
                        "vraisemblance_residuelle": 2, "gravite_residuelle": 2}),
    ]
    synth = synthese_portefeuille(risques)
    assert synth["Critique"]["brut"] == 1
    assert synth["Majeur"]["brut"] == 1
    assert synth["Faible"]["residuel"] == 2   # les deux scénarios retombent en résiduel faible
    total_brut = sum(v["brut"] for v in synth.values())
    total_residuel = sum(v["residuel"] for v in synth.values())
    assert total_brut == 2
    assert total_residuel == 2
