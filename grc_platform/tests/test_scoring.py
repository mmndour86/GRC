"""Tests unitaires du calcul des scores de maturité PSSI-ES (grc_core.scoring)."""
from grc_core.scoring import (
    compute_scores, score_to_niveau_label, top_chapitres_faibles, top_objectifs_faibles,
)


def test_score_to_niveau_label_bounds():
    assert score_to_niveau_label(None) == "Non évalué"
    assert score_to_niveau_label(0) == "Aucun"
    assert score_to_niveau_label(5) == "Optimisé"
    assert score_to_niveau_label(-1) == "Aucun"   # clampé
    assert score_to_niveau_label(9) == "Optimisé"  # clampé


def test_score_to_niveau_label_rounds_to_nearest():
    # 2.4 arrondit à 2 (GERE -> "Géré"), 2.6 arrondit à 3 (DEFINI -> "Défini")
    assert score_to_niveau_label(2.4) == "Géré"
    assert score_to_niveau_label(2.6) == "Défini"


def test_compute_scores_on_empty_controle(conn):
    """Un contrôle tout juste créé (aucune réponse) doit produire des scores
    None partout, mais lister bien les 228 règles du référentiel."""
    entite_id = conn.execute(
        "INSERT INTO entites (nom, secteur, date_creation) VALUES (?, ?, ?)",
        ("Entité vide", "Test", "2026-01-01"),
    ).lastrowid
    controle_id = conn.execute(
        "INSERT INTO controles (entite_id, date_controle, responsable, statut) VALUES (?, ?, ?, ?)",
        (entite_id, "2026-01-01", "Testeur", "En cours"),
    ).lastrowid
    conn.commit()

    scores = compute_scores(conn, controle_id)
    assert len(scores["regles"]) == 228
    assert scores["global"]["score"] is None
    assert scores["global"]["n_repondues"] == 0
    assert scores["global"]["n_regles"] == 228


def test_compute_scores_all_rules_optimise(conn):
    """Si toutes les règles applicables sont au niveau OPTIMISE (poids 5), le
    score global doit être exactement 5.0 et le taux de conformité 100%."""
    entite_id = conn.execute(
        "INSERT INTO entites (nom, secteur, date_creation) VALUES (?, ?, ?)",
        ("Entité parfaite", "Test", "2026-01-01"),
    ).lastrowid
    controle_id = conn.execute(
        "INSERT INTO controles (entite_id, date_controle, responsable, statut) VALUES (?, ?, ?, ?)",
        (entite_id, "2026-01-01", "Testeur", "En cours"),
    ).lastrowid
    conn.commit()

    refs = conn.execute("SELECT id FROM pssi_referentiel").fetchall()
    for r in refs:
        conn.execute(
            "INSERT INTO controle_reponses (controle_id, ref_id, niveau, non_applicable) VALUES (?, ?, 'OPTIMISE', 0)",
            (controle_id, r["id"]),
        )
    conn.commit()

    scores = compute_scores(conn, controle_id)
    assert scores["global"]["score"] == 5.0
    assert scores["global"]["taux_conformite"] == 100.0
    assert scores["global"]["n_repondues"] == 228
    assert scores["global"]["n_na"] == 0
    assert scores["global"]["niveau_label"] == "Optimisé"


def test_compute_scores_excludes_non_applicable(conn):
    """Les règles marquées non applicables ne doivent pas peser dans la moyenne,
    mais doivent bien être comptabilisées dans n_na."""
    entite_id = conn.execute(
        "INSERT INTO entites (nom, secteur, date_creation) VALUES (?, ?, ?)",
        ("Entité NA", "Test", "2026-01-01"),
    ).lastrowid
    controle_id = conn.execute(
        "INSERT INTO controles (entite_id, date_controle, responsable, statut) VALUES (?, ?, ?, ?)",
        (entite_id, "2026-01-01", "Testeur", "En cours"),
    ).lastrowid
    conn.commit()

    refs = conn.execute("SELECT id FROM pssi_referentiel ORDER BY id").fetchall()
    # Les 10 premières règles : niveau OPTIMISE (poids 5).
    for r in refs[:10]:
        conn.execute(
            "INSERT INTO controle_reponses (controle_id, ref_id, niveau, non_applicable) VALUES (?, ?, 'OPTIMISE', 0)",
            (controle_id, r["id"]),
        )
    # Les 5 suivantes : non applicables (ne doivent pas compter dans la moyenne).
    for r in refs[10:15]:
        conn.execute(
            "INSERT INTO controle_reponses (controle_id, ref_id, niveau, non_applicable) VALUES (?, ?, NULL, 1)",
            (controle_id, r["id"]),
        )
    conn.commit()

    scores = compute_scores(conn, controle_id)
    assert scores["global"]["score"] == 5.0  # uniquement les 10 OPTIMISE comptent
    assert scores["global"]["n_repondues"] == 10
    assert scores["global"]["n_na"] == 5
    assert scores["global"]["n_non_renseignees"] == 228 - 10 - 5


def test_top_chapitres_et_objectifs_faibles_tries_croissant(conn):
    entite_id = conn.execute(
        "INSERT INTO entites (nom, secteur, date_creation) VALUES (?, ?, ?)",
        ("Entité mixte", "Test", "2026-01-01"),
    ).lastrowid
    controle_id = conn.execute(
        "INSERT INTO controles (entite_id, date_controle, responsable, statut) VALUES (?, ?, ?, ?)",
        (entite_id, "2026-01-01", "Testeur", "En cours"),
    ).lastrowid
    conn.commit()

    refs = conn.execute("SELECT id FROM pssi_referentiel ORDER BY id").fetchall()
    # Une moitié à AUCUN (0), l'autre à OPTIMISE (5) : le tri croissant doit
    # placer les chapitres/objectifs à 0 en tête.
    milieu = len(refs) // 2
    for r in refs[:milieu]:
        conn.execute(
            "INSERT INTO controle_reponses (controle_id, ref_id, niveau, non_applicable) VALUES (?, ?, 'AUCUN', 0)",
            (controle_id, r["id"]),
        )
    for r in refs[milieu:]:
        conn.execute(
            "INSERT INTO controle_reponses (controle_id, ref_id, niveau, non_applicable) VALUES (?, ?, 'OPTIMISE', 0)",
            (controle_id, r["id"]),
        )
    conn.commit()

    scores = compute_scores(conn, controle_id)
    faibles_chap = top_chapitres_faibles(scores, n=3)
    faibles_obj = top_objectifs_faibles(scores, n=3)

    scores_chap = [c["score"] for _, c in faibles_chap]
    scores_obj = [o["score"] for _, o in faibles_obj]
    assert scores_chap == sorted(scores_chap)
    assert scores_obj == sorted(scores_obj)
