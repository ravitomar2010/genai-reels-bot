#!/usr/bin/env python3
"""
Upload generated Reel to Zernio and post to Instagram.
Runs fully automated — no human steps needed.
"""

import sys, json, time, os, glob, requests
from pathlib import Path

ZERNIO_KEY  = os.environ.get("ZERNIO_API_KEY", "")
ZERNIO_BASE = "https://api.zernio.com/v1"
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

def find_latest_meta():
    """Find the latest generated reel metadata."""
    base = Path(__file__).resolve().parent.parent
    meta_path = base / "generated" / "latest_reel_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError("No latest_reel_meta.json found. Run generate_reel_v2.py first.")
    with open(meta_path) as f:
        return json.load(f)

def upload_video(video_path: Path) -> str:
    def _get_upload_link():
        log("Getting upload link...")
        r = requests.post(f"{ZERNIO_BASE}/media/generate-upload-link",
                          headers=HEADERS, json={}, timeout=30)
        r.raise_for_status()
        return r.json()

    data  = _retry(_get_upload_link, "Get upload link")
    token = data.get("token")
    url   = data.get("upload_url") or data.get("url")
    log(f"Uploading {video_path.name} ({video_path.stat().st_size//1024} KB)...")

    def _upload_file():
        with open(video_path, "rb") as f:
            up = requests.post(url, files={"file": (video_path.name, f, "video/mp4")}, timeout=120)
        log(f"Upload HTTP {up.status_code}")
        up.raise_for_status()

    _retry(_upload_file, "Upload file")

    for i in range(10):
        time.sleep(5)
        s = requests.get(f"{ZERNIO_BASE}/media/check-upload-status",
                         headers=HEADERS, params={"token": token}, timeout=30)
        s.raise_for_status()
        sd = s.json()
        log(f"  Status check {i+1}: {sd.get('status','?')}")
        urls = sd.get("media_urls") or sd.get("urls") or []
        if urls:
            log(f"Upload complete: {urls[0]}")
            return urls[0]
        if sd.get("status") == "failed":
            raise RuntimeError(f"Upload failed: {sd}")

    raise TimeoutError("Upload timed out after 50s")

def post_to_instagram(media_url: str, caption: str) -> str:
    def _post():
        log("Posting to Instagram...")
        r = requests.post(
            f"{ZERNIO_BASE}/posts",
            headers=HEADERS,
            json={"platform": "instagram", "content": caption,
                  "media_urls": media_url, "publish_now": True},
            timeout=60
        )
        r.raise_for_status()
        result = r.json()
        log(f"Response: {result}")
        post_id = result.get("id") or result.get("post_id") or result.get("postId")
        if not post_id and not result.get("success"):
            raise RuntimeError(f"Post failed: {result}")
        return str(post_id)

    return _retry(_post, "Post to Instagram")

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
    media_url = upload_video(video_path)
    post_id   = post_to_instagram(media_url, meta["caption"])
    log(f"\nPosted to @agentwave.ai | Post ID: {post_id}")
    log(f"   Topic: {meta['topic_title']}")

if __name__ == "__main__":
    main()
