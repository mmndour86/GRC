"""
Authentification, rôles et journal d'activité pour la plateforme GRC.

Trois rôles :
- administrateur : accès complet, y compris la gestion des utilisateurs ;
- auditeur       : peut consulter et modifier (contrôles, risques, mapping) ;
- lecture_seule  : consultation uniquement, aucune action d'écriture.

Le mot de passe n'est jamais stocké en clair : hachage PBKDF2-HMAC-SHA256
(200 000 itérations) avec un sel aléatoire par utilisateur.
"""
import hashlib
import os
import secrets
from datetime import datetime

import streamlit as st

ROLES = ["administrateur", "auditeur", "lecture_seule"]
ROLES_ECRITURE = {"administrateur", "auditeur"}
ROLE_LABELS = {
    "administrateur": "Administrateur",
    "auditeur": "Auditeur (lecture/écriture)",
    "lecture_seule": "Lecture seule",
}

PBKDF2_ITERATIONS = 200_000


def hash_password(password, sel_hex=None):
    sel_hex = sel_hex or secrets.token_hex(16)
    sel = bytes.fromhex(sel_hex)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), sel, PBKDF2_ITERATIONS)
    return h.hex(), sel_hex


def verify_password(password, hash_hex, sel_hex):
    candidate, _ = hash_password(password, sel_hex)
    return secrets.compare_digest(candidate, hash_hex)


def generer_mot_de_passe_initial():
    """Génère un mot de passe lisible et raisonnablement fort (ex: 'trocolat-47-fibule')."""
    mots = ["trocolat", "baobab", "sirocco", "fibule", "kantan", "lampion", "saveur",
            "girofle", "moringa", "teranga", "fatick", "nianing", "ndar", "kedougou"]
    a, b = secrets.choice(mots), secrets.choice(mots)
    n = secrets.randbelow(90) + 10
    return f"{a}-{n}-{b}"


def log_action(conn, utilisateur, action, details=""):
    conn.execute(
        "INSERT INTO journal_activite (horodatage, utilisateur, action, details) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), utilisateur, action, details),
    )
    conn.commit()


def seed_admin_par_defaut(conn):
    """Crée le compte administrateur initial avec un mot de passe généré
    aléatoirement, à changer obligatoirement à la première connexion.
    Retourne (identifiant, mot_de_passe_en_clair) — la seule fois où le mot
    de passe en clair est disponible."""
    identifiant = "admin"
    mdp = generer_mot_de_passe_initial()
    h, sel = hash_password(mdp)
    conn.execute(
        "INSERT INTO utilisateurs (identifiant, nom_complet, mot_de_passe_hash, sel, role, actif, "
        "doit_changer_mdp, date_creation) VALUES (?, ?, ?, ?, ?, 1, 1, ?)",
        (identifiant, "Administrateur", h, sel, "administrateur", datetime.now().isoformat(timespec="seconds")),
    )
    log_action(conn, "système", "creation_compte", f"Compte administrateur initial '{identifiant}' créé.")
    return identifiant, mdp


def authentifier(conn, identifiant, mot_de_passe):
    row = conn.execute(
        "SELECT * FROM utilisateurs WHERE identifiant = ?", (identifiant,)
    ).fetchone()
    if row is None or not row["actif"]:
        log_action(conn, identifiant, "connexion_echouee", "Identifiant inconnu ou compte désactivé.")
        return None
    if not verify_password(mot_de_passe, row["mot_de_passe_hash"], row["sel"]):
        log_action(conn, identifiant, "connexion_echouee", "Mot de passe incorrect.")
        return None
    conn.execute(
        "UPDATE utilisateurs SET derniere_connexion = ? WHERE id = ?",
        (datetime.now().isoformat(timespec="seconds"), row["id"]),
    )
    conn.commit()
    log_action(conn, identifiant, "connexion_reussie", "")
    return dict(row)


def creer_utilisateur(conn, identifiant, nom_complet, mot_de_passe, role, cree_par="système"):
    h, sel = hash_password(mot_de_passe)
    conn.execute(
        "INSERT INTO utilisateurs (identifiant, nom_complet, mot_de_passe_hash, sel, role, actif, "
        "doit_changer_mdp, date_creation) VALUES (?, ?, ?, ?, ?, 1, 1, ?)",
        (identifiant, nom_complet, h, sel, role, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    log_action(conn, cree_par, "creation_utilisateur", f"Utilisateur '{identifiant}' créé avec le rôle {role}.")


def changer_mot_de_passe(conn, user_id, nouveau_mdp, identifiant_pour_journal=""):
    h, sel = hash_password(nouveau_mdp)
    conn.execute(
        "UPDATE utilisateurs SET mot_de_passe_hash = ?, sel = ?, doit_changer_mdp = 0 WHERE id = ?",
        (h, sel, user_id),
    )
    conn.commit()
    log_action(conn, identifiant_pour_journal, "changement_mot_de_passe", "")


def definir_statut(conn, user_id, actif, acteur="système"):
    conn.execute("UPDATE utilisateurs SET actif = ? WHERE id = ?", (int(actif), user_id))
    conn.commit()
    log_action(conn, acteur, "modification_statut_utilisateur", f"user_id={user_id} actif={actif}")


def definir_role(conn, user_id, role, acteur="système"):
    conn.execute("UPDATE utilisateurs SET role = ? WHERE id = ?", (role, user_id))
    conn.commit()
    log_action(conn, acteur, "modification_role_utilisateur", f"user_id={user_id} role={role}")


def lister_utilisateurs(conn):
    rows = conn.execute(
        "SELECT id, identifiant, nom_complet, role, actif, doit_changer_mdp, date_creation, derniere_connexion "
        "FROM utilisateurs ORDER BY identifiant"
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Intégration Streamlit : session, garde d'accès par page, rôle courant
# ---------------------------------------------------------------------------

def current_user():
    return st.session_state.get("grc_user")


def is_logged_in():
    return current_user() is not None


def can_write():
    user = current_user()
    return bool(user and user["role"] in ROLES_ECRITURE)


def is_admin():
    user = current_user()
    return bool(user and user["role"] == "administrateur")


def logout():
    st.session_state.pop("grc_user", None)


def _login_form(conn):
    st.title("🛡️ Plateforme GRC — Connexion")
    st.caption("Conformité PSSI-ES · ISO 27001 · NIST · DORA — Gestion des risques ISO/IEC 27005")
    with st.form("login_form"):
        identifiant = st.text_input("Identifiant")
        mot_de_passe = st.text_input("Mot de passe", type="password")
        submit = st.form_submit_button("Se connecter", type="primary")
    if submit:
        user = authentifier(conn, identifiant.strip(), mot_de_passe)
        if user:
            st.session_state["grc_user"] = user
            st.rerun()
        else:
            st.error("Identifiant ou mot de passe incorrect.")
    st.stop()


def _forcer_changement_mdp(conn, user):
    st.title("🔑 Changement de mot de passe requis")
    st.info(
        "Pour des raisons de sécurité, vous devez définir un nouveau mot de passe avant de continuer."
    )
    with st.form("change_pwd_form"):
        mdp1 = st.text_input("Nouveau mot de passe", type="password")
        mdp2 = st.text_input("Confirmer le nouveau mot de passe", type="password")
        submit = st.form_submit_button("Valider", type="primary")
    if submit:
        if len(mdp1) < 8:
            st.error("Le mot de passe doit contenir au moins 8 caractères.")
        elif mdp1 != mdp2:
            st.error("Les deux mots de passe ne correspondent pas.")
        else:
            changer_mot_de_passe(conn, user["id"], mdp1, identifiant_pour_journal=user["identifiant"])
            user = dict(user)
            user["doit_changer_mdp"] = 0
            st.session_state["grc_user"] = user
            st.success("Mot de passe mis à jour.")
            st.rerun()
    st.stop()


def require_login(conn):
    """À appeler en tout début de chaque page. Affiche l'écran de connexion
    si nécessaire (et stoppe l'exécution de la page), sinon retourne
    l'utilisateur connecté."""
    user = current_user()
    if user is None:
        _login_form(conn)
    if user and user.get("doit_changer_mdp"):
        _forcer_changement_mdp(conn, user)
    return user


def require_role(*roles):
    """Stoppe la page avec un message d'erreur si l'utilisateur courant n'a
    pas l'un des rôles indiqués. À utiliser après require_login()."""
    user = current_user()
    if user is None or user["role"] not in roles:
        st.error("⛔ Vous n'avez pas les droits nécessaires pour accéder à cette page.")
        st.stop()


def render_user_badge(conn):
    """Affiche dans la barre latérale l'utilisateur connecté et un bouton de déconnexion."""
    user = current_user()
    if not user:
        return
    with st.sidebar:
        st.markdown(f"**{user.get('nom_complet') or user['identifiant']}**")
        st.caption(ROLE_LABELS.get(user["role"], user["role"]))
        if st.button("Se déconnecter", key="btn_logout"):
            log_action(conn, user["identifiant"], "deconnexion", "")
            logout()
            st.rerun()
