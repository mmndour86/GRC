# Image de production pour la plateforme GRC (Streamlit).
# Inclut LibreOffice headless pour l'export PDF automatique des rapports.
FROM python:3.11-slim

# LibreOffice (export PDF) + polices de base pour un rendu correct des rapports.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice \
        fonts-dejavu \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Le dossier db/ contient la base SQLite par défaut et le fichier du mot de
# passe administrateur initial : à monter en volume pour persister entre
# redéploiements (voir docker-compose.yml).
RUN mkdir -p /app/db

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
