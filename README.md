# Paperless Duplicate Search

Web app to find duplicates in Paperless-ngx and compare them side-by-side before deleting.

## Requirements

- Python 3.12 (for local run) or Docker
- Paperless-ngx instance with API token

## Configuration

Set these environment variables:

- **`PAPERLESS_URL`** – Base URL of your Paperless instance (no trailing slash), e.g. `https://paperless.example.com`
- **`PAPERLESS_TOKEN`** – API token of a user with read/delete permission for documents

## Local run

```bash
cd paperless-duplicate-search

export PAPERLESS_URL="https://your-paperless-host"
export PAPERLESS_TOKEN="YOUR_API_TOKEN"

pip install -r requirements.txt
uvicorn main:app --reload
```

Then open `http://localhost:8000` in your browser.

## Docker

Build the image:

```bash
docker build -t paperless-duplicate-search .
```

Run the container:

```bash
docker run --rm -p 8000:8000 \
  -e PAPERLESS_URL="https://your-paperless-host" \
  -e PAPERLESS_TOKEN="YOUR_API_TOKEN" \
  paperless-duplicate-search
```

Then open `http://<server-ip>:8000`.

## Features

- Duplicate detection by checksum (100%) and by title + content similarity (80–100%)
- Metadata (correspondent, tags, date) shown with names; date/title/correspondent/tag differences reduce similarity score
- Filter by similarity (exact % or minimum %); chart reflects filter and stays in sync
- Side-by-side preview and “keep left / keep right” delete
- Bulk: select pairs and delete selected, or “Clean all 100% duplicates”
- UI in English with optional German (language selector)
