#!/usr/bin/env python3
"""
Upload generated Reel to Zernio and post to Instagram.
Runs fully automated — no human steps needed.
"""

import sys, json, time, os, requests
from pathlib import Path

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

def find_latest_meta():
    """Find the latest generated reel metadata."""
    base = Path(__file__).resolve().parent.parent
    meta_path = base / "generated" / "latest_reel_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError("No latest_reel_meta.json found. Run generate_reel_v2.py first.")
    with open(meta_path) as f:
        return json.load(f)

def get_instagram_account_id():
    """Fetch the connected Instagram account ID from Zernio."""
    def _fetch():
        log("Fetching connected accounts...")
        r = requests.get(f"{ZERNIO_BASE}/accounts", headers=HEADERS, timeout=30)
        r.raise_for_status()
        accounts = r.json()
        if isinstance(accounts, dict):
            accounts = accounts.get("accounts") or accounts.get("data") or []
        for acc in accounts:
            if acc.get("platform") == "instagram":
                aid = acc.get("_id") or acc.get("id") or acc.get("accountId")
                log(f"  Found Instagram account: {aid}")
                return aid
        raise RuntimeError(f"No Instagram account connected in Zernio. Connect one at https://zernio.com")

    return _retry(_fetch, "Fetch accounts")

def upload_video(video_path: Path) -> str:
    """Upload video via Zernio presigned URL flow."""
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

def post_to_instagram(media_url: str, caption: str, account_id: str) -> str:
    def _post():
        log("Posting to Instagram...")
        body = {
            "content": caption,
            "mediaItems": [{"url": media_url, "type": "video"}],
            "platforms": [{
                "platform": "instagram",
                "accountId": account_id,
                "platformSpecificData": {
                    "contentType": "reels",
                    "shareToFeed": True,
                },
            }],
            "publishNow": True,
        }
        r = requests.post(f"{ZERNIO_BASE}/posts",
                          headers=HEADERS, json=body, timeout=60)
        r.raise_for_status()
        result = r.json()
        post_obj = result.get("post", {})
        post_id = (
            post_obj.get("_id") or post_obj.get("id")
            or result.get("id") or result.get("post_id")
            or result.get("postId") or result.get("_id")
        )
        log(f"  Post ID: {post_id}")
        return str(post_id or "ok")

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
    account_id = get_instagram_account_id()
    media_url  = upload_video(video_path)
    post_id    = post_to_instagram(media_url, meta["caption"], account_id)
    log(f"\nPosted to @agentwave.ai | Post ID: {post_id}")
    log(f"   Topic: {meta['topic_title']}")

if __name__ == "__main__":
    main()
