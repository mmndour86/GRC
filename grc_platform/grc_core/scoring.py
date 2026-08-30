"""
Calcul des scores de maturité PSSI-ES à partir des réponses saisies pour un
contrôle donné. Reproduit la logique du classeur CMMI/DCSSI/PSSI-ES transmis :
moyenne des niveaux de maturité (poids 0 à 5) par objectif, par chapitre puis
au global, en excluant les règles non applicables ou non encore renseignées.
"""
from collections import defaultdict

from grc_core.db import NIVEAU_TO_POIDS, NIVEAU_TO_CONFORMITE

NIVEAU_LABELS = {
    "AUCUN": "Aucun", "INITIAL": "Initial", "GERE": "Géré",
    "DEFINI": "Défini", "QUANTIFIE": "Quantifié", "OPTIMISE": "Optimisé",
}
NIVEAU_ORDER = ["AUCUN", "INITIAL", "GERE", "DEFINI", "QUANTIFIE", "OPTIMISE"]


def score_to_niveau_label(score):
    """Associe un score moyen (0-5) au libellé de niveau CMMI le plus proche."""
    if score is None:
        return "Non évalué"
    palier = round(score)
    palier = max(0, min(5, palier))
    return NIVEAU_LABELS[NIVEAU_ORDER[palier]]


def get_referentiel_avec_reponses(conn, controle_id):
    """Retourne la liste des 228 règles, chacune enrichie de la réponse du
    contrôle sélectionné (niveau, N/A, justification) si elle existe."""
    rows = conn.execute(
        """
        SELECT r.id AS ref_id, r.chapitre_num, r.chapitre_nom, r.objectif_num, r.objectif_texte,
               r.regle_id, r.poids_max,
               cr.niveau, cr.non_applicable, cr.justification, cr.commentaire
        FROM pssi_referentiel r
        LEFT JOIN controle_reponses cr
               ON cr.ref_id = r.id AND cr.controle_id = ?
        ORDER BY r.chapitre_num, r.objectif_num, r.regle_id
        """,
        (controle_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def compute_scores(conn, controle_id):
    """Calcule les scores par objectif, par chapitre et au global.

    Renvoie un dict avec :
      - regles: liste enrichie (voir get_referentiel_avec_reponses)
      - objectifs: {num: {texte, chapitre_num, score, n_regles, n_repondues, n_na}}
      - chapitres: {num: {nom, score, n_regles, n_repondues, n_na}}
      - global: {score, taux_conformite, niveau_label, n_regles, n_repondues, n_na,
                 repartition_niveaux: {niveau: count}}
    """
    regles = get_referentiel_avec_reponses(conn, controle_id)

    objectifs = defaultdict(lambda: {"poids": [], "n_regles": 0, "n_na": 0, "n_repondues": 0})
    chapitres = defaultdict(lambda: {"poids": [], "n_regles": 0, "n_na": 0, "n_repondues": 0})
    repartition = defaultdict(int)
    tous_poids = []
    n_na_total = 0
    n_repondues_total = 0

    for r in regles:
        obj = objectifs[r["objectif_num"]]
        chap = chapitres[r["chapitre_num"]]
        obj["texte"] = r["objectif_texte"]
        obj["chapitre_num"] = r["chapitre_num"]
        chap["nom"] = r["chapitre_nom"]
        obj["n_regles"] += 1
        chap["n_regles"] += 1

        if r["non_applicable"]:
            obj["n_na"] += 1
            chap["n_na"] += 1
            n_na_total += 1
            continue
        if not r["niveau"]:
            continue

        poids = NIVEAU_TO_POIDS.get(r["niveau"])
        obj["poids"].append(poids)
        chap["poids"].append(poids)
        tous_poids.append(poids)
        obj["n_repondues"] += 1
        chap["n_repondues"] += 1
        n_repondues_total += 1
        repartition[r["niveau"]] += 1

    def moyenne(lst):
        return round(sum(lst) / len(lst), 2) if lst else None

    objectifs_out = {}
    for num, o in objectifs.items():
        objectifs_out[num] = {
            "texte": o["texte"], "chapitre_num": o["chapitre_num"],
            "score": moyenne(o["poids"]), "n_regles": o["n_regles"],
            "n_repondues": o["n_repondues"], "n_na": o["n_na"],
        }

    chapitres_out = {}
    for num, c in chapitres.items():
        chapitres_out[num] = {
            "nom": c["nom"], "score": moyenne(c["poids"]),
            "n_regles": c["n_regles"], "n_repondues": c["n_repondues"], "n_na": c["n_na"],
        }

    score_global = moyenne(tous_poids)

    return {
        "regles": regles,
        "objectifs": objectifs_out,
        "chapitres": chapitres_out,
        "global": {
            "score": score_global,
            "taux_conformite": round(score_global / 5 * 100, 1) if score_global is not None else None,
            "niveau_label": score_to_niveau_label(score_global),
            "n_regles": len(regles),
            "n_repondues": n_repondues_total,
            "n_na": n_na_total,
            "n_non_renseignees": len(regles) - n_repondues_total - n_na_total,
            "repartition_niveaux": dict(repartition),
        },
    }


def top_chapitres_faibles(scores, n=4):
    """Retourne les n chapitres au score le plus faible (hors non évalués), triés croissant."""
    items = [(num, c) for num, c in scores["chapitres"].items() if c["score"] is not None]
    items.sort(key=lambda x: x[1]["score"])
    return items[:n]


def top_objectifs_faibles(scores, n=6):
    items = [(num, o) for num, o in scores["objectifs"].items() if o["score"] is not None]
    items.sort(key=lambda x: x[1]["score"])
    return items[:n]
