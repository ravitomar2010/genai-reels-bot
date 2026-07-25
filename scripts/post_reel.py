#!/usr/bin/env python3
"""
Upload generated Reel to Zernio and post to Instagram.
Runs fully automated — no human steps needed.
"""

import json
from pathlib import Path

from zernio_client import ZERNIO_KEY, log, get_account_id, upload_video, upload_image, create_post


def find_latest_meta():
    """Find the latest generated reel metadata."""
    base = Path(__file__).resolve().parent.parent
    meta_path = base / "generated" / "latest_reel_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError("No latest_reel_meta.json found. Run generate_reel_v2.py first.")
    with open(meta_path) as f:
        return json.load(f)


def post_to_instagram(media_url: str, caption: str, account_id: str,
                       thumbnail_url: str = None, first_comment: str = None) -> str:
    log("Posting to Instagram...")
    platform_data = {
        "contentType": "reels",
        "shareToFeed": True,
        "isAiGenerated": True,   # requests the Instagram "AI Generated" label
    }
    if thumbnail_url:
        platform_data["instagramThumbnail"] = thumbnail_url
    if first_comment:
        platform_data["firstComment"] = first_comment

    body = {
        "content": caption,
        "mediaItems": [{"url": media_url, "type": "video"}],
        "platforms": [{
            "platform": "instagram",
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
    account_id = get_account_id("instagram")
    media_url  = upload_video(video_path)

    thumbnail_url = None
    thumb_path = Path(meta["thumbnail_path"]) if meta.get("thumbnail_path") else None
    if thumb_path and thumb_path.exists():
        try:
            thumbnail_url = upload_image(thumb_path)
        except Exception as e:
            log(f"  Thumbnail upload failed, continuing without it: {e}")

    post_id = post_to_instagram(media_url, meta["caption"], account_id,
                                 thumbnail_url, meta.get("engagement_comment"))
    log(f"\nPosted to @agentwave.ai | Post ID: {post_id}")
    log(f"   Topic: {meta['topic_title']}")


if __name__ == "__main__":
    main()
