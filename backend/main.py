import asyncio
import csv
import io
import logging
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from config import GSC_PROPERTY_URL, DAILY_QUOTA_LIMIT
from database import init_db, get_db, get_daily_quota_used, run_retention_cleanup, get_all_profiles_quota
from inspection import run_inspection, progress_store
from profiles import load_profiles_from_json, get_all_profiles, preview_url_profiles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="GSC Indexation Checker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await init_db()
    await load_profiles_from_json()
    await run_retention_cleanup()
    logger.info("Database initialized and retention cleanup complete.")


# --- Models ---

class CheckRequest(BaseModel):
    urls: list[str]


class ProfileRequest(BaseModel):
    name: str
    path_pattern: str
    credentials_path: str
    token_path: str
    sort_order: int = 0


class PreviewRequest(BaseModel):
    urls: list[str]


# --- Helpers ---

def validate_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception:
        return False


def clean_url_list(raw_urls: list[str]) -> list[str]:
    """Strip whitespace, remove blanks, deduplicate, validate."""
    seen = set()
    cleaned = []
    for url in raw_urls:
        url = url.strip()
        if not url or url in seen:
            continue
        if validate_url(url):
            seen.add(url)
            cleaned.append(url)
    return cleaned


# --- Profile Endpoints ---

@app.get("/api/profiles")
async def list_profiles():
    """List all credential profiles."""
    db = await get_db()
    try:
        profiles = await get_all_profiles(db)
        return profiles
    finally:
        await db.close()


@app.post("/api/profiles")
async def create_profile(request: ProfileRequest):
    """Create a new credential profile."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO profiles (name, path_pattern, credentials_path, token_path, sort_order)
               VALUES (?, ?, ?, ?, ?)""",
            (request.name, request.path_pattern, request.credentials_path, request.token_path, request.sort_order),
        )
        profile_id = cursor.lastrowid
        await db.commit()
        return {"id": profile_id, **request.model_dump()}
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise HTTPException(status_code=409, detail=f"Profile name '{request.name}' already exists")
        raise
    finally:
        await db.close()


@app.put("/api/profiles/{profile_id}")
async def update_profile(profile_id: int, request: ProfileRequest):
    """Update an existing credential profile."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id FROM profiles WHERE id = ?", (profile_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Profile not found")

        await db.execute(
            """UPDATE profiles SET name = ?, path_pattern = ?, credentials_path = ?,
               token_path = ?, sort_order = ? WHERE id = ?""",
            (request.name, request.path_pattern, request.credentials_path, request.token_path, request.sort_order, profile_id),
        )
        await db.commit()
        return {"id": profile_id, **request.model_dump()}
    finally:
        await db.close()


@app.delete("/api/profiles/{profile_id}")
async def delete_profile(profile_id: int):
    """Delete a credential profile."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id FROM profiles WHERE id = ?", (profile_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Profile not found")

        await db.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        await db.commit()
        return {"deleted": True}
    finally:
        await db.close()


@app.post("/api/profiles/preview")
async def preview_profiles(request: PreviewRequest):
    """Preview which profile each URL maps to."""
    cleaned = clean_url_list(request.urls)
    db = await get_db()
    try:
        profiles = await get_all_profiles(db)
        return preview_url_profiles(cleaned, profiles)
    finally:
        await db.close()


# --- Check Endpoints ---

@app.post("/api/checks")
async def create_check(request: CheckRequest):
    """Submit URL list to start an inspection run."""
    urls = request.urls

    if not urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    cleaned = clean_url_list(urls)
    if not cleaned:
        raise HTTPException(status_code=400, detail="No valid URLs after validation")

    # Quota check (aggregate across all profiles)
    used = await get_daily_quota_used()
    remaining = DAILY_QUOTA_LIMIT - used
    if len(cleaned) > remaining:
        raise HTTPException(
            status_code=429,
            detail=f"Batch of {len(cleaned)} URLs exceeds remaining daily quota of {remaining}. "
                   f"Used {used}/{DAILY_QUOTA_LIMIT} today.",
        )

    # Create check record
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO checks (created_at, url_count, property_url, status) VALUES (?, ?, ?, 'running')",
            (now, len(cleaned), GSC_PROPERTY_URL),
        )
        check_id = cursor.lastrowid
        await db.commit()
    finally:
        await db.close()

    # Launch background inspection
    asyncio.create_task(run_inspection(check_id, cleaned))

    return {"check_id": check_id, "url_count": len(cleaned), "status": "running"}


@app.post("/api/checks/upload")
async def create_check_upload(file: UploadFile = File(...)):
    """Submit URL list via file upload."""
    content = await file.read()
    urls = content.decode("utf-8").splitlines()

    if not urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    cleaned = clean_url_list(urls)
    if not cleaned:
        raise HTTPException(status_code=400, detail="No valid URLs after validation")

    used = await get_daily_quota_used()
    remaining = DAILY_QUOTA_LIMIT - used
    if len(cleaned) > remaining:
        raise HTTPException(
            status_code=429,
            detail=f"Batch of {len(cleaned)} URLs exceeds remaining daily quota of {remaining}.",
        )

    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO checks (created_at, url_count, property_url, status) VALUES (?, ?, ?, 'running')",
            (now, len(cleaned), GSC_PROPERTY_URL),
        )
        check_id = cursor.lastrowid
        await db.commit()
    finally:
        await db.close()

    asyncio.create_task(run_inspection(check_id, cleaned))
    return {"check_id": check_id, "url_count": len(cleaned), "status": "running"}


@app.get("/api/checks")
async def list_checks():
    """List all past check runs with summary stats."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT c.id, c.created_at, c.url_count, c.property_url, c.status, c.elapsed_seconds,
                      COALESCE(SUM(CASE WHEN r.verdict = 'PASS' THEN 1 ELSE 0 END), 0) as indexed_count,
                      COALESCE(SUM(CASE WHEN r.verdict IS NOT NULL AND r.verdict != 'PASS' AND r.error IS NULL THEN 1 ELSE 0 END), 0) as not_indexed_count,
                      COALESCE(SUM(CASE WHEN r.error IS NOT NULL THEN 1 ELSE 0 END), 0) as error_count
               FROM checks c
               LEFT JOIN results r ON c.id = r.check_id
               GROUP BY c.id
               ORDER BY c.created_at DESC"""
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "created_at": row[1],
                "url_count": row[2],
                "property_url": row[3],
                "status": row[4],
                "elapsed_seconds": row[5],
                "indexed_count": row[6],
                "not_indexed_count": row[7],
                "error_count": row[8],
            }
            for row in rows
        ]
    finally:
        await db.close()


@app.get("/api/checks/{check_id}")
async def get_check(check_id: int):
    """Get check details and all results."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM checks WHERE id = ?", (check_id,))
        check = await cursor.fetchone()
        if not check:
            raise HTTPException(status_code=404, detail="Check not found")

        cursor = await db.execute(
            """SELECT r.id, u.url, r.coverage_state, r.verdict, r.last_crawl_time,
                      r.crawled_as, r.google_canonical, r.user_canonical,
                      r.referring_sitemaps, r.status_changed, r.error, u.deindex_count,
                      r.profile_id, p.name as profile_name
               FROM results r
               JOIN urls u ON r.url_id = u.id
               LEFT JOIN profiles p ON r.profile_id = p.id
               WHERE r.check_id = ?
               ORDER BY r.id""",
            (check_id,),
        )
        results = await cursor.fetchall()

        return {
            "id": check[0],
            "created_at": check[1],
            "url_count": check[2],
            "property_url": check[3],
            "status": check[4],
            "elapsed_seconds": check[5],
            "results": [
                {
                    "id": r[0],
                    "url": r[1],
                    "coverage_state": r[2],
                    "verdict": r[3],
                    "last_crawl_time": r[4],
                    "crawled_as": r[5],
                    "google_canonical": r[6],
                    "user_canonical": r[7],
                    "referring_sitemaps": r[8],
                    "status_changed": bool(r[9]),
                    "error": r[10],
                    "deindex_count": r[11],
                    "profile_id": r[12],
                    "profile_name": r[13],
                }
                for r in results
            ],
        }
    finally:
        await db.close()


@app.get("/api/checks/{check_id}/progress")
async def check_progress(check_id: int):
    """SSE stream for real-time progress updates."""

    async def event_generator():
        while True:
            progress = progress_store.get(check_id)
            if progress:
                if progress["status"] in ("completed", "error"):
                    elapsed = progress.get("elapsed_seconds", 0.0)
                else:
                    started_at = progress.get("started_at")
                    elapsed = round(time.monotonic() - started_at, 1) if started_at else 0.0
                yield {
                    "event": "progress",
                    "data": f'{{"completed": {progress["completed"]}, "total": {progress["total"]}, "status": "{progress["status"]}", "elapsed_seconds": {elapsed}}}',
                }
                if progress["status"] in ("completed", "error"):
                    break
            else:
                # Check if it's in DB already completed
                db = await get_db()
                try:
                    cursor = await db.execute("SELECT status FROM checks WHERE id = ?", (check_id,))
                    row = await cursor.fetchone()
                    if row and row[0] in ("completed", "error"):
                        yield {
                            "event": "progress",
                            "data": f'{{"completed": 0, "total": 0, "status": "{row[0]}"}}',
                        }
                        break
                finally:
                    await db.close()
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@app.get("/api/checks/{check_id}/export")
async def export_check(check_id: int):
    """Download CSV of check results."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT created_at FROM checks WHERE id = ?", (check_id,))
        check = await cursor.fetchone()
        if not check:
            raise HTTPException(status_code=404, detail="Check not found")

        cursor = await db.execute(
            """SELECT u.url, r.coverage_state, r.verdict, r.last_crawl_time,
                      r.crawled_as, r.google_canonical, r.user_canonical,
                      r.referring_sitemaps, r.status_changed, r.error, u.deindex_count,
                      p.name as profile_name
               FROM results r
               JOIN urls u ON r.url_id = u.id
               LEFT JOIN profiles p ON r.profile_id = p.id
               WHERE r.check_id = ?
               ORDER BY r.id""",
            (check_id,),
        )
        results = await cursor.fetchall()
    finally:
        await db.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "URL", "Coverage State", "Verdict", "Last Crawl Time",
        "Crawled As", "Google Canonical", "User Canonical",
        "Referring Sitemaps", "Status Changed", "Error", "Deindex Count", "Profile",
    ])
    for r in results:
        writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], bool(r[8]), r[9], r[10], r[11] or ""])

    output.seek(0)
    ts = datetime.fromisoformat(check[0]).strftime("%Y-%m-%d_%H%M")
    filename = f"indexation_check_{ts}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/urls/{url_id}/history")
async def url_history(url_id: int):
    """Full check history for a single URL."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id, url, first_seen, deindex_count FROM urls WHERE id = ?", (url_id,))
        url_row = await cursor.fetchone()
        if not url_row:
            raise HTTPException(status_code=404, detail="URL not found")

        cursor = await db.execute(
            """SELECT r.id, c.created_at, r.coverage_state, r.verdict,
                      r.last_crawl_time, r.crawled_as, r.google_canonical,
                      r.user_canonical, r.referring_sitemaps, r.status_changed, r.error
               FROM results r
               JOIN checks c ON r.check_id = c.id
               WHERE r.url_id = ?
               ORDER BY c.created_at DESC""",
            (url_id,),
        )
        history = await cursor.fetchall()

        return {
            "id": url_row[0],
            "url": url_row[1],
            "first_seen": url_row[2],
            "deindex_count": url_row[3],
            "history": [
                {
                    "id": h[0],
                    "checked_at": h[1],
                    "coverage_state": h[2],
                    "verdict": h[3],
                    "last_crawl_time": h[4],
                    "crawled_as": h[5],
                    "google_canonical": h[6],
                    "user_canonical": h[7],
                    "referring_sitemaps": h[8],
                    "status_changed": bool(h[9]),
                    "error": h[10],
                }
                for h in history
            ],
        }
    finally:
        await db.close()


@app.get("/api/urls/lookup")
async def url_lookup(url: str):
    """Look up a URL by its URL string to get its ID."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id FROM urls WHERE url = ?", (url,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="URL not found")
        return {"url_id": row[0]}
    finally:
        await db.close()


@app.get("/api/quota")
async def get_quota():
    """Return remaining daily quota, with per-profile breakdown if profiles exist."""
    used = await get_daily_quota_used()
    profiles_quota = await get_all_profiles_quota()

    result = {
        "used": used,
        "limit": DAILY_QUOTA_LIMIT,
        "remaining": DAILY_QUOTA_LIMIT - used,
    }

    if profiles_quota:
        result["profiles"] = [
            {
                "profile_id": pq["profile_id"],
                "name": pq["name"],
                "used": pq["used"],
                "limit": DAILY_QUOTA_LIMIT,
                "remaining": DAILY_QUOTA_LIMIT - pq["used"],
            }
            for pq in profiles_quota
        ]
        # Total across all profiles
        result["total_used"] = sum(pq["used"] for pq in profiles_quota)
        result["total_limit"] = DAILY_QUOTA_LIMIT * len(profiles_quota)
        result["total_remaining"] = result["total_limit"] - result["total_used"]

    return result
