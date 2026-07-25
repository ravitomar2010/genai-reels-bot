#!/usr/bin/env python3
"""Shared Zernio API helpers used by post_reel.py and post_youtube.py."""

import time, os, requests

ZERNIO_KEY  = os.environ.get("ZERNIO_API_KEY", "")
ZERNIO_BASE = "https://zernio.com/api/v1"
HEADERS     = {"Authorization": f"Bearer {ZERNIO_KEY}", "Content-Type": "application/json"}

MAX_RETRIES = 3
RETRY_DELAY = 5


def log(msg): print(msg, flush=True)


def _retry(fn, description):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn()
        except Exception as e:
            log(f"  {description} attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt == MAX_RETRIES:
                raise
            time.sleep(RETRY_DELAY * attempt)


def get_account_id(platform: str) -> str:
    """Fetch the connected account ID for a given platform (e.g. 'instagram', 'youtube') from Zernio."""
    def _fetch():
        log(f"Fetching connected {platform} account...")
        r = requests.get(f"{ZERNIO_BASE}/accounts", headers=HEADERS, timeout=30)
        r.raise_for_status()
        accounts = r.json()
        if isinstance(accounts, dict):
            accounts = accounts.get("accounts") or accounts.get("data") or []
        for acc in accounts:
            if acc.get("platform") == platform:
                aid = acc.get("_id") or acc.get("id") or acc.get("accountId")
                log(f"  Found {platform} account: {aid}")
                return aid
        raise RuntimeError(f"No {platform} account connected in Zernio. Connect one at https://zernio.com")

    return _retry(_fetch, f"Fetch {platform} account")


def upload_video(video_path) -> str:
    """Upload video via Zernio presigned URL flow. Returns the public URL."""
    from pathlib import Path
    video_path = Path(video_path)

    def _get_presigned():
        log("Getting presigned upload URL...")
        r = requests.post(f"{ZERNIO_BASE}/media/presign",
                          headers=HEADERS,
                          json={"filename": video_path.name, "contentType": "video/mp4"},
                          timeout=30)
        r.raise_for_status()
        return r.json()

    data = _retry(_get_presigned, "Get presigned URL")
    upload_url = data.get("uploadUrl")
    public_url = data.get("publicUrl")
    log(f"Uploading {video_path.name} ({video_path.stat().st_size // 1024} KB)...")

    def _upload_file():
        with open(video_path, "rb") as f:
            up = requests.put(upload_url,
                              data=f.read(),
                              headers={"Content-Type": "video/mp4"},
                              timeout=300)
        log(f"  Upload HTTP {up.status_code}")
        up.raise_for_status()

    _retry(_upload_file, "Upload file")
    log(f"Upload complete: {public_url}")
    return public_url


def upload_image(image_path) -> str:
    """Upload a JPG/PNG via Zernio presigned URL flow. Returns the public URL."""
    from pathlib import Path
    image_path = Path(image_path)
    content_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"

    def _get_presigned():
        log("Getting presigned image upload URL...")
        r = requests.post(f"{ZERNIO_BASE}/media/presign",
                          headers=HEADERS,
                          json={"filename": image_path.name, "contentType": content_type},
                          timeout=30)
        r.raise_for_status()
        return r.json()

    data = _retry(_get_presigned, "Get presigned image URL")
    upload_url = data.get("uploadUrl")
    public_url = data.get("publicUrl")
    log(f"Uploading {image_path.name} ({image_path.stat().st_size // 1024} KB)...")

    def _upload_file():
        with open(image_path, "rb") as f:
            up = requests.put(upload_url,
                              data=f.read(),
                              headers={"Content-Type": content_type},
                              timeout=60)
        log(f"  Upload HTTP {up.status_code}")
        up.raise_for_status()

    _retry(_upload_file, "Upload image")
    log(f"Image upload complete: {public_url}")
    return public_url


def create_post(body: dict) -> str:
    def _post():
        r = requests.post(f"{ZERNIO_BASE}/posts", headers=HEADERS, json=body, timeout=60)
        r.raise_for_status()
        result = r.json()
        post_obj = result.get("post", {})
        post_id = (
            post_obj.get("_id") or post_obj.get("id")
            or result.get("id") or result.get("post_id")
            or result.get("postId") or result.get("_id")
        )
        return str(post_id or "ok")

    return _retry(_post, "Create post")
