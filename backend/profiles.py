import json
import logging
import os
from fnmatch import fnmatch
from urllib.parse import urlparse

import aiosqlite

from config import PROFILES_CONFIG_PATH
from database import get_db

logger = logging.getLogger(__name__)


async def load_profiles_from_json():
    """Read profiles.json and upsert into database on startup."""
    if not os.path.exists(PROFILES_CONFIG_PATH):
        logger.info(f"No profiles config at {PROFILES_CONFIG_PATH}, skipping seed.")
        return

    with open(PROFILES_CONFIG_PATH) as f:
        profiles = json.load(f)

    db = await get_db()
    try:
        for p in profiles:
            await db.execute(
                """INSERT INTO profiles (name, path_pattern, credentials_path, token_path, sort_order)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                       path_pattern = excluded.path_pattern,
                       credentials_path = excluded.credentials_path,
                       token_path = excluded.token_path,
                       sort_order = excluded.sort_order""",
                (p["name"], p["path_pattern"], p["credentials_path"], p["token_path"], p.get("sort_order", 0)),
            )
        await db.commit()
        logger.info(f"Seeded {len(profiles)} profiles from {PROFILES_CONFIG_PATH}")
    finally:
        await db.close()


async def get_all_profiles(db: aiosqlite.Connection) -> list[dict]:
    """Fetch all profiles from DB, sorted by sort_order."""
    cursor = await db.execute(
        "SELECT id, name, path_pattern, credentials_path, token_path, sort_order "
        "FROM profiles ORDER BY sort_order"
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "path_pattern": row[2],
            "credentials_path": row[3],
            "token_path": row[4],
            "sort_order": row[5],
        }
        for row in rows
    ]


def match_url_to_profile(url: str, profiles: list[dict]) -> dict | None:
    """Match a URL to a profile by path pattern.

    Profiles are checked in sort_order. The user must set sort_order
    so that more specific patterns (e.g. /en-in/*) come before broader
    ones (e.g. /en/*).

    Returns the matching profile dict, or None if no match.
    """
    parsed = urlparse(url)
    path = parsed.path

    for profile in profiles:
        pattern = profile["path_pattern"]
        if fnmatch(path, pattern):
            return profile

    return None


def group_urls_by_profile(urls: list[str], profiles: list[dict]) -> tuple[dict[int, list[str]], list[str]]:
    """Group URLs by their matching profile.

    Returns:
        (grouped, unmatched) where grouped is {profile_id: [urls]} and
        unmatched is a list of URLs that didn't match any profile.
    """
    grouped: dict[int, list[str]] = {}
    unmatched: list[str] = []

    for url in urls:
        profile = match_url_to_profile(url, profiles)
        if profile:
            grouped.setdefault(profile["id"], []).append(url)
        else:
            unmatched.append(url)

    return grouped, unmatched


def preview_url_profiles(urls: list[str], profiles: list[dict]) -> list[dict]:
    """Preview which profile each URL maps to (for frontend display).

    Returns list of {url, profile_id, profile_name} dicts.
    """
    result = []
    for url in urls:
        profile = match_url_to_profile(url, profiles)
        result.append({
            "url": url,
            "profile_id": profile["id"] if profile else None,
            "profile_name": profile["name"] if profile else None,
        })
    return result
