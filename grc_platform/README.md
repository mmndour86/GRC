# Plateforme GRC — PSSI-ES · ISO 27001 · NIST · DORA · ISO/IEC 27005

Prototype web fonctionnel de plateforme GRC (Gouvernance, Risques, Conformité), construit à partir :

- du modèle CMMI/DCSSI d'évaluation de la PSSI-ES (228 règles, 30 objectifs, 11 chapitres) ;
- du registre des risques anglophone *Risk Register Template for Information Security v1.0* (inspiration pour le tableau de bord) ;
- du référentiel d'appréciation des risques ISO/IEC 27005 (biens essentiels, biens supports, DICT, menaces/vulnérabilités, appréciation, plan de traitement) ;
- des rapports d'évaluation ANAQ-Sup et COUD, dont la structure est reproduite automatiquement par le générateur de rapport.

## Déploiement le plus simple : cloud entièrement géré (Render)

Si vous ne disposez ni d'un serveur, ni d'un nom de domaine, et que vous voulez une plateforme accessible sur
Internet sans rien administrer (pas de commande à taper sur un serveur, pas de certificat à gérer), le plus
simple est un hébergeur "cloud managé" comme [Render](https://render.com/). Un fichier `render.yaml` est
fourni : il décrit à Render qu'il faut créer le service web (à partir du `Dockerfile`) et sa base PostgreSQL,
et les relier automatiquement — vous n'avez que quelques clics à faire, aucune ligne de commande.

1. **Créez un compte GitHub** (gratuit) si vous n'en avez pas, sur [github.com](https://github.com/).
2. Créez un nouveau dépôt (bouton « New repository »), puis utilisez « **uploading an existing file** » /
   « Add file → Upload files » sur la page du dépôt pour glisser-déposer tout le contenu du dossier
   `grc_platform` (celui que vous avez reçu) — cela ne nécessite pas d'installer Git.
3. Créez un compte sur [render.com](https://render.com/) (gratuit, connexion possible directement avec votre
   compte GitHub).
4. Dans le tableau de bord Render : **New +** → **Blueprint**, puis sélectionnez le dépôt GitHub que vous
   venez de créer. Render détecte le fichier `render.yaml` et propose de créer les deux ressources (le
   service web et la base PostgreSQL) en un clic sur **Apply**.
5. Patientez quelques minutes pendant la construction (l'installation de LibreOffice dans l'image prend un
   peu de temps). Render fournit ensuite une adresse du type `https://grc-platform.onrender.com` —
   **accessible immédiatement depuis Internet, en HTTPS, sans aucun nom de domaine à acheter.**
6. Ouvrez cette adresse : le mot de passe administrateur initial s'affiche **une seule fois** à l'écran
   (bandeau jaune). Notez-le tout de suite — sur ce mode de déploiement (base PostgreSQL), il n'est pas
   sauvegardé dans un fichier, uniquement dans la base. Changez-le immédiatement comme demandé, puis créez
   les comptes des utilisateurs réels depuis la page 🔐 Administration.

**Coût** : ce mode de déploiement n'est pas gratuit en usage réel — le plan gratuit de Render supprime la
base PostgreSQL au bout de 30 jours (adapté à un essai, pas à une utilisation durable). Le premier palier
payant revient à environ 13 $/mois au total (≈ 7 $/mois pour le service web + ≈ 6 $/mois pour la base
PostgreSQL), sans engagement, facturé à l'usage. Un nom de domaine personnalisé (ex. `grc.votre-organisation.org`
au lieu de `onrender.com`) peut être ajouté plus tard depuis les paramètres du service, si vous en achetez un
(chez [Namecheap](https://www.namecheap.com/), OVH, Gandi... généralement 10 à 20 $/an pour un `.com`) —
ce n'est pas nécessaire pour que la plateforme soit utilisable sur Internet.

**Alternative moins chère, plus autonome** : louer un petit serveur (VPS) chez un hébergeur comme Hetzner,
DigitalOcean ou Scaleway (généralement 4 à 7 €/mois) et utiliser le `Dockerfile`/`docker-compose.yml`/Caddy
déjà fournis dans ce projet (voir les sections « Déploiement avec Docker » et « Exposition sur Internet »
ci-dessous) — un peu moins cher sur la durée, mais demande de savoir se connecter en SSH à un serveur et
taper quelques commandes.

## Installation

Prérequis : Python 3.10 ou supérieur.

```bash
cd grc_platform
python -m venv .venv
source .venv/bin/activate   # sous Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

**Export PDF automatique du rapport (optionnel)** : installez [LibreOffice](https://www.libreoffice.org/) pour que
le bouton « Télécharger en PDF » du module de génération de rapport fonctionne. Sans LibreOffice, le rapport
reste disponible au format Word, exportable en PDF manuellement (Word → Enregistrer sous → PDF).

## Lancement

```bash
streamlit run app.py
```

L'application s'ouvre dans votre navigateur (par défaut `http://localhost:8501`). Au tout premier lancement,
un compte **administrateur** est créé automatiquement avec un mot de passe généré aléatoirement, affiché
une seule fois à l'écran et enregistré dans `db/ADMIN_INITIAL_PASSWORD.txt` (à supprimer une fois récupéré).
Ce mot de passe doit être changé dès la première connexion.

La base de données SQLite (`db/grc.db`) est créée et amorcée automatiquement au premier lancement avec :

- le référentiel complet des 228 règles PSSI-ES ;
- la table de correspondance ISO 27001 / NIST CSF / DORA (proposition initiale, éditable) ;
- une « Entité de démonstration » avec un contrôle d'exemple pré-rempli et quelques risques ISO 27005
  d'illustration, pour explorer immédiatement chaque module ;
- **ANAQ-Sup** et **COUD**, avec un contrôle reconstituant les évaluations DCSSI déjà publiées pour ces
  deux entités (rapports fournis en exemple), pour disposer immédiatement de deux jeux de données réels
  et contrastés (score global 2,40/5 pour l'un, 0,95/5 pour l'autre) et pouvoir régénérer leur rapport
  depuis la plateforme.

  ⚠️ **Ces deux jeux de données sont une reconstitution, pas les réponses d'origine.** Les rapports Word
  ANAQ-Sup/COUD fournis ne conservent que les scores moyens par objectif (30 valeurs), pas la réponse
  donnée à chacune des 228 règles. La plateforme recalcule un niveau plausible par règle de façon à
  reproduire fidèlement les scores par objectif, par chapitre et le score global publiés dans les rapports
  d'origine (écart de quelques centièmes tout au plus), mais le niveau affiché pour une règle précise n'est
  pas nécessairement celui réellement déclaré à l'époque. Chaque contrôle reconstitué porte un bandeau
  d'avertissement dans l'interface et dans les rapports générés, et reste entièrement modifiable dans le
  module Conformité PSSI-ES si vous disposez des réponses réelles.

## Modules

| Page | Contenu |
|---|---|
| Accueil | Présentation, administration de la base de données |
| 📋 Conformité PSSI-ES | Questionnaire des 228 règles, saisie du niveau de maturité, calcul automatique des scores |
| 🔗 Mapping référentiels | Table de correspondance PSSI-ES ↔ ISO 27001 ↔ NIST CSF ↔ DORA, éditable |
| ⚠️ Registre des risques ISO 27005 | Biens essentiels/supports, catalogue menaces-vulnérabilités, appréciation des risques, plan de traitement |
| 📊 Tableau de bord | Indicateurs de maturité, heatmap des risques, suivi du plan d'action |
| 📄 Génération de rapport | Génération automatique du rapport Word/PDF sur le modèle ANAQ-Sup / COUD |
| 🔐 Administration | Gestion des comptes utilisateurs et journal d'activité (réservé au rôle administrateur) |

## Authentification et rôles

La plateforme intègre une authentification propre (aucun service externe requis) : mots de passe hachés en
PBKDF2-HMAC-SHA256 (200 000 itérations, sel aléatoire par utilisateur), jamais stockés en clair. Trois rôles :

| Rôle | Droits |
|---|---|
| **administrateur** | Accès complet, y compris la gestion des comptes utilisateurs et le journal d'activité |
| **auditeur** | Consultation et modification (contrôles, risques, mapping) |
| **lecture_seule** | Consultation uniquement, aucune action d'écriture |

Le compte administrateur initial est créé automatiquement au premier lancement (voir « Lancement »
ci-dessus). Un administrateur peut ensuite créer d'autres comptes depuis la page **🔐 Administration**, avec
un mot de passe temporaire que l'utilisateur devra changer à sa première connexion. Toutes les actions de
création/modification/connexion sont journalisées (table `journal_activite`, consultable depuis la même
page).

## Passage en production : PostgreSQL

Par défaut, la plateforme utilise SQLite (fichier `db/grc.db`) : suffisant pour un usage mono-poste ou une
démonstration. Pour un usage multi-utilisateurs concurrent, migrez vers PostgreSQL :

1. Créez une base et un utilisateur PostgreSQL dédiés, par exemple :
   ```bash
   sudo -u postgres psql -c "CREATE USER grc_user WITH PASSWORD 'choisissez_un_mot_de_passe_fort';"
   sudo -u postgres psql -c "CREATE DATABASE grc_db OWNER grc_user;"
   ```
2. Si vous avez déjà des données dans `db/grc.db` (contrôles, entités, comptes utilisateurs saisis depuis le
   prototype), migrez-les avec le script fourni :
   ```bash
   python3 scripts/migrate_sqlite_to_postgres.py \
       --sqlite-path db/grc.db \
       --postgres-url postgresql://grc_user:motdepasse@localhost:5432/grc_db
   ```
   Le script crée le schéma dans PostgreSQL, copie toutes les tables dans l'ordre des dépendances en
   conservant les identifiants d'origine, et resynchronise les séquences. Il est possible de le relancer avec
   `--force` pour écraser une base cible déjà peuplée (utile en environnement de test).
3. Démarrez la plateforme avec la variable d'environnement `DATABASE_URL` positionnée :
   ```bash
   export DATABASE_URL="postgresql://grc_user:motdepasse@localhost:5432/grc_db"
   streamlit run app.py
   ```
   Toute la couche d'accès aux données (`grc_core/dbengine.py`) bascule alors automatiquement sur
   PostgreSQL — aucune autre configuration n'est nécessaire. Sans `DATABASE_URL`, la plateforme continue
   d'utiliser SQLite normalement (utile pour du développement local ou une démonstration ponctuelle).

**Sauvegardes** : en PostgreSQL, utilisez `pg_dump` régulièrement (ex. via une tâche planifiée) :
```bash
pg_dump "postgresql://grc_user:motdepasse@localhost:5432/grc_db" > sauvegarde_$(date +%Y%m%d).sql
```
En SQLite, une simple copie du fichier `db/grc.db` (base arrêtée, ou via `sqlite3 db/grc.db ".backup fichier.db"`
pour une copie à chaud) suffit.

## Déploiement avec Docker

Un `Dockerfile` et un `docker-compose.yml` sont fournis pour un déploiement en une commande, avec PostgreSQL
comme base de données (voir plus haut) et LibreOffice préinstallé (export PDF des rapports opérationnel dès
le démarrage) :

```bash
cp .env.example .env
# éditez .env et choisissez un mot de passe PostgreSQL fort (POSTGRES_PASSWORD)
docker compose up -d --build
```

L'application est alors accessible sur `http://localhost:8501` (port modifiable via `GRC_PORT` dans `.env`).
Le service `app` attend que PostgreSQL soit prêt (`healthcheck`) avant de démarrer. Les données PostgreSQL
sont conservées dans un volume Docker nommé (`grc_postgres_data`) qui survit aux redémarrages et
reconstructions du conteneur ; sauvegardez-le comme indiqué ci-dessus (`pg_dump`, exécutable soit depuis le
conteneur `postgres` via `docker compose exec postgres pg_dump ...`, soit depuis l'hôte si le port 5432 est
exposé).

Pour migrer des données existantes (`db/grc.db` local) vers l'instance PostgreSQL du conteneur, lancez le
script de migration en pointant vers le port publié par le service `postgres` (ajoutez temporairement
`ports: ["5432:5432"]` au service `postgres` dans `docker-compose.yml`, ou exécutez le script depuis un
conteneur sur le même réseau Docker).

> **Remarque sur la construction de l'image** : le `Dockerfile` part de `python:3.11-slim` (Docker Hub) et
> installe LibreOffice via `apt-get` — un accès réseau standard à Docker Hub et aux dépôts Debian est donc
> nécessaire au moment du `docker compose build`. Si votre réseau d'entreprise passe par un registre miroir
> ou un proxy, adaptez l'image de base et les dépôts `apt` en conséquence.

## Exposition sur Internet (HTTPS automatique)

Le déploiement ci-dessus convient à un accès depuis le réseau interne (`http://<ip-du-serveur>:8501`). Pour
rendre la plateforme accessible depuis Internet, il ne faut **jamais exposer le port 8501 directement** (pas
de chiffrement, pas de nom de domaine) : une surcouche `docker-compose.https.yml` ajoute un reverse proxy
[Caddy](https://caddyserver.com/) qui obtient et renouvelle automatiquement un certificat HTTPS
(Let's Encrypt), sans configuration manuelle de certificat.

Prérequis : un serveur avec une adresse IP publique, et un nom de domaine (ou sous-domaine) dont
l'enregistrement DNS de type A pointe déjà vers cette IP — Caddy ne peut valider le certificat que si ce
DNS est en place *avant* le premier démarrage.

```bash
cp .env.example .env
# éditez .env : mot de passe PostgreSQL fort (POSTGRES_PASSWORD) et nom de domaine (DOMAIN)
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --build
```

La plateforme est alors accessible sur `https://<DOMAIN>` (ports 80/443 uniquement — 80 sert à la validation
du certificat et redirige automatiquement vers 443). Le port 8501 n'est plus publié sur l'hôte, seul Caddy
l'atteint via le réseau Docker interne.

Sur le serveur, seuls les ports **80 et 443** doivent être ouverts dans le pare-feu vers l'extérieur (443
suffirait seul si vous acceptez de gérer le renouvellement de certificat autrement, mais 80 est nécessaire à
la validation automatique Let's Encrypt — laissez les deux ouverts). Le port 5432 (PostgreSQL) ne doit **en
aucun cas** être exposé publiquement ; il ne l'est pas par défaut dans `docker-compose.yml`.

L'authentification intégrée à la plateforme (voir plus haut) reste indispensable même derrière HTTPS : le
chiffrement protège le trajet réseau, mais c'est la connexion par compte qui protège l'accès aux données.
Créez les comptes des utilisateurs réels depuis la page 🔐 Administration avant de communiquer l'URL, et
changez sans attendre le mot de passe administrateur initial.

## Suite de tests automatisés

Une suite de tests `pytest` couvre la base de données (amorçage, double backend SQLite/PostgreSQL),
l'authentification et les rôles, les calculs de scoring PSSI-ES et ISO/IEC 27005, la génération de rapport,
ainsi que les pages Streamlit elles-mêmes (via `streamlit.testing.v1.AppTest` : écran de connexion,
parcours de connexion complet, contrôle d'accès par rôle).

```bash
pip install pytest
pytest tests/ -v
```

Chaque test qui a besoin d'une base de données utilise un fichier SQLite temporaire isolé (jamais
`db/grc.db`) : la suite est donc sans danger à exécuter, y compris sur un poste où la plateforme est déjà
utilisée. Le test de migration PostgreSQL (`tests/test_migration.py`) est ignoré par défaut ; pour l'activer,
pointez la variable `GRC_TEST_POSTGRES_URL` vers une base PostgreSQL de test vide (voir l'en-tête de ce
fichier pour la marche à suivre).

## Limites de ce prototype et pistes d'évolution

- **Mapping des référentiels** : établi au niveau des 11 chapitres PSSI-ES à titre de proposition initiale ;
  à valider avec vos équipes conformité, ou à affiner au niveau de chaque règle si nécessaire.
- **Catalogue de recommandations** : le fichier `data/recommandations.json` couvre désormais les 30
  objectifs PSSI-ES. Seul l'objectif 1 reprend la recommandation *officielle* présente dans le classeur
  Excel transmis ; les recommandations des objectifs 2 à 30 sont des **propositions générées par la
  plateforme** à partir du libellé de chaque objectif et des bonnes pratiques usuelles (ISO 27001, NIST).
  Les rapports générés indiquent systématiquement cette origine (« officielle DCSSI » vs « proposée, à
  valider »). Faites relire et valider ces propositions par vos équipes conformité — idéalement en les
  remplaçant progressivement par les recommandations réellement adoptées par la DCSSI — avant toute
  diffusion officielle d'un rapport.
- **Référentiels ISO 27001 / NIST / DORA en propre** : si vous souhaitez à terme un questionnaire de
  contrôles indépendant pour chacun de ces référentiels (et non plus un simple mapping), la structure de
  `pssi_referentiel` / `controle_reponses` peut être dupliquée par référentiel.
- **Déploiement réseau** : `streamlit run app.py` sert l'application en HTTP simple, adapté à un usage sur
  réseau interne de confiance. Pour une exposition plus large, placez la plateforme derrière un reverse
  proxy HTTPS (nginx, Caddy…).
