import os
import asyncio
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

bulk_delete_state: Dict[str, Any] = {
    "running": False,
    "current_group": 0,
    "total_groups": 0,
    "deleted_count": 0,
}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


async def fetch_all_documents() -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(
        base_url=PAPERLESS_URL,
        headers=HEADERS,
        timeout=60.0,
        follow_redirects=True,
    ) as client:
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
                            "correspondent": a.get("correspondent"),
                            "tags": a.get("tags", []),
                            "preview_url": build_preview_path(a["id"]),
                        },
                        "b": {
                            "id": b["id"],
                            "title": b.get("title") or b.get("original_filename"),
                            "created": b.get("created"),
                            "correspondent": b.get("correspondent"),
                            "tags": b.get("tags", []),
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
                            "correspondent": a.get("correspondent"),
                            "tags": a.get("tags", []),
                            "preview_url": build_preview_path(a["id"]),
                        },
                        "b": {
                            "id": b["id"],
                            "title": b.get("title") or b.get("original_filename"),
                            "created": b.get("created"),
                            "correspondent": b.get("correspondent"),
                            "tags": b.get("tags", []),
                            "preview_url": build_preview_path(b["id"]),
                        },
                        "similarity": sim,
                        "reason": "similar_title_and_content",
                    }
                )

    duplicate_pairs.sort(key=lambda x: x["similarity"], reverse=True)

    similarity_counts: Dict[int, int] = {}
    for pair in duplicate_pairs:
        s = int(round(pair["similarity"]))
        similarity_counts[s] = similarity_counts.get(s, 0) + 1

    return {
        "pairs": duplicate_pairs,
        "similarity_counts": similarity_counts,
        "total_pairs": len(duplicate_pairs),
    }


async def _run_bulk_delete_perfect_duplicates() -> None:
    bulk_delete_state["running"] = True
    bulk_delete_state["current_group"] = 0
    bulk_delete_state["total_groups"] = 0
    bulk_delete_state["deleted_count"] = 0

    docs = await fetch_all_documents()

    deleted_ids: list[int] = []
    groups_processed = 0

    # Index für schnellen Zugriff
    docs_by_id: Dict[int, Dict[str, Any]] = {d["id"]: d for d in docs if "id" in d}

    # 1) 100%-Paare (similar_title_and_content) finden
    by_title: Dict[str, List[Dict[str, Any]]] = {}
    for d in docs:
        title = (d.get("title") or d.get("original_filename") or "").strip().lower()
        if len(title) < 5:
            continue
        by_title.setdefault(title, []).append(d)

    # Graph der 100%-Duplikate aufbauen
    adjacency: Dict[int, set[int]] = {}

    for title, group in by_title.items():
        if len(group) < 2:
            continue
        n = len(group)
        for i in range(n):
            for j in range(i + 1, n):
                a = group[i]
                b = group[j]
                # Inhalte vergleichen
                sim = compute_similarity(a.get("content", ""), b.get("content", ""))
                if int(round(sim)) != 100:
                    continue

                ida = a["id"]
                idb = b["id"]
                adjacency.setdefault(ida, set()).add(idb)
                adjacency.setdefault(idb, set()).add(ida)

    # 2) Verbundkomponenten im Graphen finden
    visited: set[int] = set()
    components: List[List[int]] = []

    for node in adjacency.keys():
        if node in visited:
            continue
        stack = [node]
        comp: List[int] = []
        visited.add(node)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nei in adjacency.get(cur, ()):
                if nei not in visited:
                    visited.add(nei)
                    stack.append(nei)
        if len(comp) > 1:
            components.append(comp)

    bulk_delete_state["total_groups"] = len(components)

    async with httpx.AsyncClient(
        base_url=PAPERLESS_URL,
        headers=HEADERS,
        timeout=60.0,
        follow_redirects=True,
    ) as client:
        for idx, comp in enumerate(components, start=1):
            groups_processed += 1
            bulk_delete_state["current_group"] = idx

            # Innerhalb der Komponente ein Dokument behalten, Rest löschen
            sorted_ids = sorted(
                comp,
                key=lambda doc_id: (
                    (docs_by_id.get(doc_id, {}).get("created") or ""),
                    doc_id,
                ),
            )
            to_keep_id = sorted_ids[0]
            to_delete_ids = sorted_ids[1:]

            for doc_id in to_delete_ids:
                resp = await client.delete(f"/api/documents/{doc_id}/")
                if resp.status_code in (200, 204):
                    deleted_ids.append(doc_id)
                    bulk_delete_state["deleted_count"] += 1
                else:
                    raise HTTPException(
                        status_code=resp.status_code,
                        detail=f"Fehler beim Löschen von Dokument {doc_id}: {resp.text}",
                    )

    bulk_delete_state["running"] = False
    bulk_delete_state["last_result"] = {
        "status": "ok",
        "deleted_ids": deleted_ids,
        "deleted_count": len(deleted_ids),
        "groups_processed": groups_processed,
    }


@app.post("/api/delete-perfect-duplicates")
async def delete_perfect_duplicates():
    """
    Startet den asynchronen Bereinigungslauf im Hintergrund.
    """
    if bulk_delete_state.get("running"):
        raise HTTPException(status_code=409, detail="Bereinigung läuft bereits.")

    asyncio.create_task(_run_bulk_delete_perfect_duplicates())
    return {"status": "started"}


@app.get("/api/delete-perfect-duplicates/status")
async def delete_perfect_duplicates_status():
    """
    Liefert den aktuellen Fortschritt des Bereinigungslaufs.
    """
    return bulk_delete_state


@app.get("/preview/{doc_id}")
async def proxy_preview(doc_id: int):
    async with httpx.AsyncClient(
        base_url=PAPERLESS_URL,
        headers=HEADERS,
        timeout=60.0,
        follow_redirects=True,
    ) as client:
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

    async with httpx.AsyncClient(
        base_url=PAPERLESS_URL,
        headers=HEADERS,
        timeout=60.0,
        follow_redirects=True,
    ) as client:
        resp = await client.delete(f"/api/documents/{remove_id}/")
        if resp.status_code not in (204, 200):
            raise HTTPException(status_code=resp.status_code, detail=f"Fehler beim Löschen: {resp.text}")

    return JSONResponse({"status": "ok", "deleted_id": remove_id})


@app.post("/api/bulk-delete")
async def bulk_delete(body: Dict[str, Any]):
    """
    Löscht explizit ausgewählte Dokumente.
    Erwartet JSON:
    { "ids": [1, 2, 3, ...] }
    """
    ids = body.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ids muss eine nicht-leere Liste von IDs sein",
        )

    unique_ids = sorted(set(int(i) for i in ids))
    deleted_ids: list[int] = []

    async with httpx.AsyncClient(
        base_url=PAPERLESS_URL,
        headers=HEADERS,
        timeout=60.0,
        follow_redirects=True,
    ) as client:
        for doc_id in unique_ids:
            resp = await client.delete(f"/api/documents/{doc_id}/")
            if resp.status_code in (200, 204, 404):
                # 404 ignorieren, falls schon weg
                deleted_ids.append(doc_id)
            else:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Fehler beim Löschen von Dokument {doc_id}: {resp.text}",
                )

    return {"status": "ok", "deleted_ids": deleted_ids, "deleted_count": len(deleted_ids)}


@app.get("/health")
async def health():
    return {"status": "ok"}

