#!/usr/bin/env python3
"""
Pull recent post performance from Zernio and merge it into post_history.json,
so ai_content_generator.py can see which past topics/hooks actually performed
and steer future topic selection instead of flying blind.

Zernio's /v1/analytics response schema isn't fully documented per-platform,
so record/field extraction below is deliberately defensive (tries several
common key names) rather than assuming one fixed shape. If Zernio changes
field names, this degrades to "no metrics found" rather than crashing.
"""

import json
from pathlib import Path

from zernio_client import ZERNIO_KEY, log, get_account_id, get_analytics

HISTORY_PATH = Path(__file__).resolve().parent / "post_history.json"


def _first(d: dict, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return None


def _extract_post_id(record: dict):
    return (
        _first(record, "postId", "post_id", "id", "_id")
        or _first(record.get("post", {}) if isinstance(record.get("post"), dict) else {}, "id", "_id")
    )


def _extract_metrics(record: dict) -> dict:
    metrics_src = record.get("metrics") if isinstance(record.get("metrics"), dict) else record
    return {
        "views":    _first(metrics_src, "views", "viewCount", "video_views", "impressions"),
        "likes":    _first(metrics_src, "likes", "likeCount"),
        "comments": _first(metrics_src, "comments", "commentCount"),
        "shares":   _first(metrics_src, "shares", "shareCount", "reposts"),
    }


def fetch_for_platform(platform: str, history: dict):
    try:
        account_id = get_account_id(platform)
    except Exception as e:
        log(f"  Skipping {platform}: {e}")
        return

    try:
        records = get_analytics(platform=platform, account_id=account_id, limit=50)
    except Exception as e:
        log(f"  Analytics fetch failed for {platform}: {e}")
        return

    log(f"  {platform}: {len(records)} analytics records returned")
    id_field = f"{platform}_post_id"
    matched = 0
    for record in records:
        rec_id = _extract_post_id(record)
        if not rec_id:
            continue
        for entry in history["posts"]:
            if str(entry.get(id_field)) == str(rec_id):
                entry[f"{platform}_metrics"] = _extract_metrics(record)
                matched += 1
                break

    log(f"  {platform}: matched {matched} tracked post(s)")


def main():
    if not ZERNIO_KEY:
        raise EnvironmentError("ZERNIO_API_KEY secret not set in GitHub repo settings")

    if not HISTORY_PATH.exists():
        log("No post_history.json yet — nothing to fetch analytics for.")
        return

    with open(HISTORY_PATH) as f:
        history = json.load(f)

    if not history.get("posts"):
        log("post_history.json has no tracked posts yet.")
        return

    log("=== Fetching Zernio analytics ===")
    for platform in ("instagram", "youtube"):
        fetch_for_platform(platform, history)

    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)
    log(f"Saved updated metrics to {HISTORY_PATH}")


if __name__ == "__main__":
    main()
