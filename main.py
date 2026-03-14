import json
import logging
import os
import asyncio
from typing import List, Dict, Any, AsyncGenerator

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import httpx
from rapidfuzz import fuzz


PAPERLESS_URL = os.getenv("PAPERLESS_URL")
PAPERLESS_TOKEN = os.getenv("PAPERLESS_TOKEN")

if not PAPERLESS_URL or not PAPERLESS_TOKEN:
    raise RuntimeError("PAPERLESS_URL und PAPERLESS_TOKEN müssen als Umgebungsvariablen gesetzt sein.")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

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

# Für Polling-Fallback (wenn Streaming gepuffert wird)
duplicate_job_state: Dict[str, Any] = {
    "status": "idle",  # idle | running | done | error
    "progress": {"message": "", "current": 0, "total": None},
    "result": None,
    "error": None,
}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    response = templates.TemplateResponse("index.html", {"request": request})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


@app.get("/api/ping")
async def ping():
    """Sofortige Antwort – zum Prüfen der Server-Erreichbarkeit."""
    return {"ok": True}


@app.get("/api/paperless-check")
async def paperless_check():
    """Prüft, ob Paperless vom Container aus erreichbar ist (kurzer Timeout)."""
    try:
        async with httpx.AsyncClient(
            base_url=PAPERLESS_URL,
            headers=HEADERS,
            timeout=10.0,
            follow_redirects=True,
        ) as client:
            resp = await client.get("/api/documents/?page_size=1")
            resp.raise_for_status()
        return {"ok": True, "message": "Paperless erreichbar"}
    except Exception as e:
        log.warning("Paperless check failed: %s", e)
        return {"ok": False, "error": str(e)}


async def fetch_all_documents() -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    log.info("Fetching documents from Paperless...")
    async with httpx.AsyncClient(
        base_url=PAPERLESS_URL,
        headers=HEADERS,
        timeout=120.0,
        follow_redirects=True,
    ) as client:
        url: str | None = "/api/documents/"
        page = 0
        while url:
            page += 1
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            docs.extend(results)
            log.info("Documents page %s: %s docs (total so far: %s)", page, len(results), len(docs))
            url = data.get("next")
    log.info("Fetched %s documents total", len(docs))
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


def _yield_line(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


async def stream_duplicates() -> AsyncGenerator[str, None]:
    """Yields NDJSON: progress events, then one result event."""
    try:
        yield _yield_line({"event": "progress", "phase": "fetch", "message": "Lade Dokumente von Paperless…", "current": 0, "total": None})
        log.info("Duplicates: fetching documents...")
        docs = await fetch_all_documents()
        yield _yield_line({"event": "progress", "phase": "fetch", "message": f"{len(docs)} Dokumente geladen", "current": len(docs), "total": len(docs)})

        yield _yield_line({"event": "progress", "phase": "checksum", "message": "Suche Duplikate nach Checksum…", "current": 0, "total": None})
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
                    a, b = group[i], group[j]
                    duplicate_pairs.append({
                        "a": {"id": a["id"], "title": a.get("title") or a.get("original_filename"), "created": a.get("created"), "correspondent": a.get("correspondent"), "tags": a.get("tags", []), "preview_url": build_preview_path(a["id"])},
                        "b": {"id": b["id"], "title": b.get("title") or b.get("original_filename"), "created": b.get("created"), "correspondent": b.get("correspondent"), "tags": b.get("tags", []), "preview_url": build_preview_path(b["id"])},
                        "similarity": 100.0,
                        "reason": "same_checksum",
                    })
        log.info("Checksum duplicates: %s pairs", len(duplicate_pairs))
        yield _yield_line({"event": "progress", "phase": "checksum", "message": f"{len(duplicate_pairs)} 100%%-Duplikate (Checksum)", "current": len(duplicate_pairs), "total": None})

        yield _yield_line({"event": "progress", "phase": "title", "message": "Gruppiere nach Titel…", "current": 0, "total": None})
        by_title: Dict[str, List[Dict[str, Any]]] = {}
        for d in docs:
            title = (d.get("title") or d.get("original_filename") or "").strip().lower()
            if len(title) < 5:
                continue
            by_title.setdefault(title, []).append(d)

        title_groups = [(t, g) for t, g in by_title.items() if len(g) >= 2]
        total_compare = sum(len(g) * (len(g) - 1) // 2 for _, g in title_groups)
        yield _yield_line({"event": "progress", "phase": "compare", "message": f"Vergleiche Inhalt von {total_compare} Kandidaten-Paaren…", "current": 0, "total": total_compare})

        done = 0
        for title, group in title_groups:
            n = len(group)
            for i in range(n):
                for j in range(i + 1, n):
                    a, b = group[i], group[j]
                    if a.get("checksum") and b.get("checksum") and a["checksum"] == b["checksum"]:
                        done += 1
                        continue
                    sim = compute_similarity(a.get("content", ""), b.get("content", ""))
                    done += 1
                    if done % 50 == 0 or done == total_compare:
                        yield _yield_line({"event": "progress", "phase": "compare", "message": f"Verglichen: {done}/{total_compare}", "current": done, "total": total_compare})
                    if sim < 80.0:
                        continue
                    duplicate_pairs.append({
                        "a": {"id": a["id"], "title": a.get("title") or a.get("original_filename"), "created": a.get("created"), "correspondent": a.get("correspondent"), "tags": a.get("tags", []), "preview_url": build_preview_path(a["id"])},
                        "b": {"id": b["id"], "title": b.get("title") or b.get("original_filename"), "created": b.get("created"), "correspondent": b.get("correspondent"), "tags": b.get("tags", []), "preview_url": build_preview_path(b["id"])},
                        "similarity": sim,
                        "reason": "similar_title_and_content",
                    })

        duplicate_pairs.sort(key=lambda x: x["similarity"], reverse=True)
        similarity_counts: Dict[int, int] = {}
        for pair in duplicate_pairs:
            s = int(round(pair["similarity"]))
            similarity_counts[s] = similarity_counts.get(s, 0) + 1

        log.info("Total duplicate pairs: %s", len(duplicate_pairs))
        result = {"pairs": duplicate_pairs, "similarity_counts": similarity_counts, "total_pairs": len(duplicate_pairs)}
        yield _yield_line({"event": "result", "data": result})
    except Exception as e:
        log.exception("Error in stream_duplicates")
        yield _yield_line({"event": "error", "message": str(e)})


@app.get("/api/duplicates")
async def get_duplicates():
    return StreamingResponse(
        stream_duplicates(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _set_progress(message: str, current: int, total: int | None) -> None:
    duplicate_job_state["progress"] = {"message": message, "current": current, "total": total}


async def _run_duplicate_job() -> None:
    """Läuft im Hintergrund; schreibt Fortschritt in duplicate_job_state."""
    duplicate_job_state["status"] = "running"
    duplicate_job_state["result"] = None
    duplicate_job_state["error"] = None
    try:
        _set_progress("Lade Dokumente von Paperless…", 0, None)
        log.info("Duplicates (job): fetching documents...")
        docs = await fetch_all_documents()
        _set_progress(f"{len(docs)} Dokumente geladen", len(docs), len(docs))

        _set_progress("Suche Duplikate nach Checksum…", 0, None)
        by_checksum: Dict[str, List[Dict[str, Any]]] = {}
        for d in docs:
            c = d.get("checksum") or ""
            if c:
                by_checksum.setdefault(c, []).append(d)
        duplicate_pairs: List[Dict[str, Any]] = []
        for checksum, group in by_checksum.items():
            if len(group) < 2:
                continue
            n = len(group)
            for i in range(n):
                for j in range(i + 1, n):
                    a, b = group[i], group[j]
                    duplicate_pairs.append({
                        "a": {"id": a["id"], "title": a.get("title") or a.get("original_filename"), "created": a.get("created"), "correspondent": a.get("correspondent"), "tags": a.get("tags", []), "preview_url": build_preview_path(a["id"])},
                        "b": {"id": b["id"], "title": b.get("title") or b.get("original_filename"), "created": b.get("created"), "correspondent": b.get("correspondent"), "tags": b.get("tags", []), "preview_url": build_preview_path(b["id"])},
                        "similarity": 100.0,
                        "reason": "same_checksum",
                    })
        _set_progress(f"{len(duplicate_pairs)} 100%-Duplikate (Checksum)", len(duplicate_pairs), None)

        _set_progress("Gruppiere nach Titel…", 0, None)
        by_title: Dict[str, List[Dict[str, Any]]] = {}
        for d in docs:
            title = (d.get("title") or d.get("original_filename") or "").strip().lower()
            if len(title) >= 5:
                by_title.setdefault(title, []).append(d)
        title_groups = [(t, g) for t, g in by_title.items() if len(g) >= 2]
        total_compare = sum(len(g) * (len(g) - 1) // 2 for _, g in title_groups)
        _set_progress(f"Vergleiche Inhalt von {total_compare} Kandidaten-Paaren…", 0, total_compare)

        done = 0
        for title, group in title_groups:
            n = len(group)
            for i in range(n):
                for j in range(i + 1, n):
                    a, b = group[i], group[j]
                    if a.get("checksum") and b.get("checksum") and a["checksum"] == b["checksum"]:
                        done += 1
                        continue
                    sim = compute_similarity(a.get("content", ""), b.get("content", ""))
                    done += 1
                    if done % 50 == 0 or done == total_compare:
                        _set_progress(f"Verglichen: {done}/{total_compare}", done, total_compare)
                    if sim >= 80.0:
                        duplicate_pairs.append({
                            "a": {"id": a["id"], "title": a.get("title") or a.get("original_filename"), "created": a.get("created"), "correspondent": a.get("correspondent"), "tags": a.get("tags", []), "preview_url": build_preview_path(a["id"])},
                            "b": {"id": b["id"], "title": b.get("title") or b.get("original_filename"), "created": b.get("created"), "correspondent": b.get("correspondent"), "tags": b.get("tags", []), "preview_url": build_preview_path(b["id"])},
                            "similarity": sim,
                            "reason": "similar_title_and_content",
                        })
        duplicate_pairs.sort(key=lambda x: x["similarity"], reverse=True)
        similarity_counts: Dict[int, int] = {}
        for pair in duplicate_pairs:
            s = int(round(pair["similarity"]))
            similarity_counts[s] = similarity_counts.get(s, 0) + 1
        result = {"pairs": duplicate_pairs, "similarity_counts": similarity_counts, "total_pairs": len(duplicate_pairs)}
        duplicate_job_state["result"] = result
        duplicate_job_state["status"] = "done"
        _set_progress("Fertig.", 1, 1)
        log.info("Duplicate job done: %s pairs", len(duplicate_pairs))
    except Exception as e:
        log.exception("Duplicate job error")
        duplicate_job_state["status"] = "error"
        duplicate_job_state["error"] = str(e)
        duplicate_job_state["result"] = None


@app.post("/api/duplicates/start")
async def start_duplicate_job():
    """Startet die Duplikat-Suche im Hintergrund (für Polling-Fallback)."""
    if duplicate_job_state["status"] == "running":
        raise HTTPException(status_code=409, detail="Job läuft bereits.")
    duplicate_job_state["status"] = "idle"
    duplicate_job_state["result"] = None
    duplicate_job_state["error"] = None
    asyncio.create_task(_run_duplicate_job())
    return JSONResponse({"status": "started"}, status_code=202)


@app.get("/api/duplicates/status")
async def duplicate_job_status():
    """Fortschritt und Ergebnis der Duplikat-Suche (für Polling)."""
    return duplicate_job_state


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

