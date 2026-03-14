# Paperless Duplicate Search

Kleine Webanwendung, um Duplikate in Paperless-ng/Paperless-ngx zu finden und vor dem Löschen nebeneinander zu vergleichen.

## Voraussetzungen

- Python 3.12 (für lokalen Start) oder Docker
- Paperless-Instanz mit API-Token

## Konfiguration

Folgende Umgebungsvariablen müssen gesetzt sein:

- `PAPERLESS_URL` – Basis-URL deiner Paperless-Instanz (ohne Slash am Ende), z. B. `https://paperless.example.com`
- `PAPERLESS_TOKEN` – API-Token eines Benutzers mit Lesens-/Löschrechten für Dokumente

## Lokaler Start

```bash
cd paperless-duplicate-search

export PAPERLESS_URL="https://dein-paperless-host"
export PAPERLESS_TOKEN="DEIN_API_TOKEN"

pip install -r requirements.txt
uvicorn main:app --reload
```

Danach im Browser: `http://localhost:8000`

## Docker

Image bauen:

```bash
docker build -t paperless-duplicate-search .
```

Container starten:

```bash
docker run --rm -p 8000:8000 \
  -e PAPERLESS_URL="https://dein-paperless-host" \
  -e PAPERLESS_TOKEN="DEIN_API_TOKEN" \
  paperless-duplicate-search
```

Dann im Browser: `http://<server-ip>:8000`

