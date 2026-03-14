import os
from typing import List, Dict, Any

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import httpx
from rapidfuzz import fuzz


PAPERLESS_URL = os.getenv("PAPERLESS_URL")
PAPERLESS_TOKEN = os.getenv("PAPERLESS_TOKEN")

if not PAPERLESS_URL or not PAPERLESS_TOKEN:
    raise RuntimeError("PAPERLESS_URL und PAPERLESS_TOKEN müssen als Umgebungsvariablen gesetzt sein.")

HEADERS = {
    "Authorization": f"Token {PAPERLESS_TOKEN}",
    "Accept": "application/json",
}

app = FastAPI()
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


async def fetch_all_documents() -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(base_url=PAPERLESS_URL, headers=HEADERS, timeout=60.0) as client:
        url: str | None = "/api/documents/"
        while url:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            docs.extend(results)
            url = data.get("next")
    return docs


def compute_similarity(text_a: str, text_b: str) -> float:
    if not text_a or not text_b:
        return 0.0
    max_len = 8000
    ta = text_a[:max_len]
    tb = text_b[:max_len]
    return float(fuzz.token_set_ratio(ta, tb))


def build_preview_path(doc_id: int) -> str:
    return f"/preview/{doc_id}"


@app.get("/api/duplicates")
async def get_duplicates():
    docs = await fetch_all_documents()

    by_checksum: Dict[str, List[Dict[str, Any]]] = {}
    for d in docs:
        checksum = d.get("checksum") or ""
        if not checksum:
            continue
        by_checksum.setdefault(checksum, []).append(d)

    duplicate_pairs: List[Dict[str, Any]] = []

    for checksum, group in by_checksum.items():
        if len(group) < 2:
            continue
        n = len(group)
        for i in range(n):
            for j in range(i + 1, n):
                a = group[i]
                b = group[j]
                duplicate_pairs.append(
                    {
                        "a": {
                            "id": a["id"],
                            "title": a.get("title") or a.get("original_filename"),
                            "created": a.get("created"),
                            "preview_url": build_preview_path(a["id"]),
                        },
                        "b": {
                            "id": b["id"],
                            "title": b.get("title") or b.get("original_filename"),
                            "created": b.get("created"),
                            "preview_url": build_preview_path(b["id"]),
                        },
                        "similarity": 100.0,
                        "reason": "same_checksum",
                    }
                )

    by_title: Dict[str, List[Dict[str, Any]]] = {}
    for d in docs:
        title = (d.get("title") or d.get("original_filename") or "").strip().lower()
        if len(title) < 5:
            continue
        by_title.setdefault(title, []).append(d)

    for title, group in by_title.items():
        if len(group) < 2:
            continue
        n = len(group)
        for i in range(n):
            for j in range(i + 1, n):
                a = group[i]
                b = group[j]
                if a.get("checksum") and b.get("checksum") and a["checksum"] == b["checksum"]:
                    continue
                sim = compute_similarity(a.get("content", ""), b.get("content", ""))
                if sim < 80.0:
                    continue
                duplicate_pairs.append(
                    {
                        "a": {
                            "id": a["id"],
                            "title": a.get("title") or a.get("original_filename"),
                            "created": a.get("created"),
                            "preview_url": build_preview_path(a["id"]),
                        },
                        "b": {
                            "id": b["id"],
                            "title": b.get("title") or b.get("original_filename"),
                            "created": b.get("created"),
                            "preview_url": build_preview_path(b["id"]),
                        },
                        "similarity": sim,
                        "reason": "similar_title_and_content",
                    }
                )

    duplicate_pairs.sort(key=lambda x: x["similarity"], reverse=True)

    return {"pairs": duplicate_pairs}


@app.get("/preview/{doc_id}")
async def proxy_preview(doc_id: int):
    async with httpx.AsyncClient(base_url=PAPERLESS_URL, headers=HEADERS, timeout=60.0) as client:
        url_preview = f"/api/documents/{doc_id}/preview/"
        try:
            resp = await client.get(url_preview)
            if resp.status_code == 200:
                media_type = resp.headers.get("content-type", "image/png")
                return StreamingResponse(resp.aiter_bytes(), media_type=media_type)
        except httpx.HTTPError:
            pass

        url_download = f"/api/documents/{doc_id}/download/"
        resp = await client.get(url_download)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Preview/Download failed")
        media_type = resp.headers.get("content-type", "application/pdf")
        return StreamingResponse(resp.aiter_bytes(), media_type=media_type)


@app.post("/api/delete")
async def delete_document(body: Dict[str, Any]):
    keep_id = body.get("keep_id")
    remove_id = body.get("remove_id")
    if not keep_id or not remove_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="keep_id und remove_id sind Pflicht",
        )

    if keep_id == remove_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="keep_id und remove_id müssen verschieden sein",
        )

    async with httpx.AsyncClient(base_url=PAPERLESS_URL, headers=HEADERS, timeout=60.0) as client:
        resp = await client.delete(f"/api/documents/{remove_id}/")
        if resp.status_code not in (204, 200):
            raise HTTPException(status_code=resp.status_code, detail=f"Fehler beim Löschen: {resp.text}")

    return JSONResponse({"status": "ok", "deleted_id": remove_id})


@app.get("/health")
async def health():
    return {"status": "ok"}

