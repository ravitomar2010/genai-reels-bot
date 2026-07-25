#!/usr/bin/env python3
"""
Upload the same generated Reel to Zernio and post it as a YouTube Short.
Reuses the video rendered by generate_reel_v2.py (1080x1920, well under
YouTube's 3-minute Shorts threshold) — no separate render needed.
"""

import json
from pathlib import Path

from zernio_client import ZERNIO_KEY, log, get_account_id, upload_video, upload_image, create_post


def find_latest_meta():
    base = Path(__file__).resolve().parent.parent
    meta_path = base / "generated" / "latest_reel_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError("No latest_reel_meta.json found. Run generate_reel_v2.py first.")
    with open(meta_path) as f:
        return json.load(f)


def post_to_youtube(media_url: str, meta: dict, account_id: str, thumbnail_url: str = None) -> str:
    log("Posting to YouTube (Shorts)...")

    title       = (meta.get("youtube_title") or meta["topic_title"])[:100]
    description = meta.get("youtube_description") or meta["caption"]
    hashtags    = meta.get("youtube_hashtags") or ""
    tags        = meta.get("youtube_tags") or []

    content = description.strip()
    if hashtags and hashtags not in content:
        content += f"\n\n{hashtags}"

    media_item = {"url": media_url, "type": "video"}
    if thumbnail_url:
        media_item["thumbnail"] = thumbnail_url

    platform_data = {
        "title": title,
        "visibility": "public",
        "madeForKids": False,
        "categoryId": "28",              # Science & Technology
        "containsSyntheticMedia": True,   # AI-generated voice + visuals — disclose per YouTube policy
        "tags": tags,
    }
    first_comment = meta.get("engagement_comment")
    if first_comment:
        platform_data["firstComment"] = first_comment

    body = {
        "content": content[:5000],
        "mediaItems": [media_item],
        "platforms": [{
            "platform": "youtube",
            "accountId": account_id,
            "platformSpecificData": platform_data,
        }],
        "publishNow": True,
    }
    post_id = create_post(body)
    log(f"  Post ID: {post_id}")
    return post_id


def main():
    if not ZERNIO_KEY:
        raise EnvironmentError("ZERNIO_API_KEY secret not set in GitHub repo settings")

    meta       = find_latest_meta()
    video_path = Path(meta["video_path"])
    if not video_path.exists():
        repo_root  = Path(__file__).resolve().parent.parent
        video_path = repo_root / "generated" / video_path.name

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    log(f"Topic: {meta['topic_title']} (#{meta['topic_id']})")
    account_id = get_account_id("youtube")
    media_url  = upload_video(video_path)

    thumbnail_url = None
    thumb_path = Path(meta["thumbnail_path"]) if meta.get("thumbnail_path") else None
    if thumb_path and thumb_path.exists():
        try:
            thumbnail_url = upload_image(thumb_path)
        except Exception as e:
            log(f"  Thumbnail upload failed, continuing without it: {e}")

    post_id = post_to_youtube(media_url, meta, account_id, thumbnail_url)
    log(f"\nPosted to YouTube Shorts | Post ID: {post_id}")
    log(f"   Topic: {meta['topic_title']}")


if __name__ == "__main__":
    main()
