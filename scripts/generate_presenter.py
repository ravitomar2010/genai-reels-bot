#!/usr/bin/env python3
"""
Optional lip-synced cartoon presenter overlay.

Cloud-only, no local model, no GPU (this pipeline runs on GitHub Actions'
free ubuntu-latest runners, which have neither). Reads the clean pre-music
voiceover + a static character image, calls a cloud talking-head API, and
writes the resulting clip's path back into latest_reel_meta.json as
"presenter_clip".

Backend is picked by PRESENTER_BACKEND, default "none" — when off, this
script is a no-op and the pipeline behaves exactly as it does today.

A presenter failure must never break the daily reel: any error here is
logged and swallowed, presenter_clip is left as None, and this script
always exits 0.
"""

import os, sys, json, hashlib, base64, subprocess, shutil, time
from pathlib import Path

import requests

BASE      = Path(__file__).resolve().parent
REPO_ROOT = BASE.parent
OUTDIR    = REPO_ROOT / "generated"
META_PATH = OUTDIR / "latest_reel_meta.json"

PRESENTER_BACKEND       = os.environ.get("PRESENTER_BACKEND", "none").lower()
PRESENTER_CHAR_REF      = os.environ.get("PRESENTER_CHAR_REF", "assets/character/presenter.png")
DID_API_KEY             = os.environ.get("DID_API_KEY", "")
REPLICATE_API_TOKEN     = os.environ.get("REPLICATE_API_TOKEN", "")
PRESENTER_CACHE_DIR     = Path(os.environ.get("PRESENTER_CACHE_DIR", ".cache/presenter"))

# Replicate/SadTalker: upstream relicensed to Apache 2.0 (non-commercial
# restriction removed per their README), but the specific Replicate listing
# (cjwbw/sadtalker) still explicitly states personal/research/non-commercial
# use only as of this writing. That's a real conflict on the exact platform
# this would call — unverified for commercial use. Gated off unless the user
# explicitly opts in, separately from just picking "replicate" as backend.
REPLICATE_LICENSE_CONFIRMED = os.environ.get("REPLICATE_LICENSE_CONFIRMED", "") == "true"


def log(msg): print(msg, flush=True)


def _resample_audio(src_path: Path, sample_rate: int = 16000) -> Path:
    """Normalize to mono PCM WAV at a conservative, broadly-compatible sample
    rate — don't assume the source format/rate is what the API wants."""
    out_path = src_path.with_suffix(".presenter16k.wav")
    cmd = ["ffmpeg", "-y", "-i", str(src_path), "-ac", "1", "-ar", str(sample_rate), str(out_path)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg resample failed: {r.stderr[-500:]}")
    return out_path


def _cache_key(audio_path: Path, image_path: Path, backend: str) -> str:
    h = hashlib.sha256()
    h.update(audio_path.read_bytes())
    h.update(image_path.read_bytes())
    h.update(backend.encode())
    return h.hexdigest()


def _cache_get(key: str):
    p = PRESENTER_CACHE_DIR / f"{key}.mp4"
    return p if p.exists() else None


def _cache_put(key: str, clip_path: Path) -> Path:
    PRESENTER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = PRESENTER_CACHE_DIR / f"{key}.mp4"
    shutil.copy2(clip_path, dest)
    return dest


def _upload_public(path: Path, content_type: str) -> str:
    """Host a local file at a public HTTPS URL via Zernio's presign flow —
    already a working dependency in this pipeline. D-ID needs source_url/
    audio_url as real URLs, it doesn't accept direct file uploads."""
    sys.path.insert(0, str(BASE))
    from zernio_client import ZERNIO_BASE, HEADERS

    r = requests.post(f"{ZERNIO_BASE}/media/presign", headers=HEADERS,
                       json={"filename": path.name, "contentType": content_type}, timeout=30)
    r.raise_for_status()
    data = r.json()
    upload_url, public_url = data["uploadUrl"], data["publicUrl"]
    with open(path, "rb") as f:
        up = requests.put(upload_url, data=f.read(), headers={"Content-Type": content_type}, timeout=120)
    up.raise_for_status()
    return public_url


def _render_did(audio_path: Path, image_path: Path, out_path: Path) -> Path:
    """D-ID /talks API — cloud HTTPS call, no GPU/model needed on our side."""
    if not DID_API_KEY:
        raise RuntimeError("DID_API_KEY not set")

    log("  Uploading audio + character image (D-ID needs public URLs, not file uploads)...")
    audio_url = _upload_public(audio_path, "audio/mpeg" if audio_path.suffix == ".mp3" else "audio/wav")
    image_url = _upload_public(image_path, "image/png")

    auth = base64.b64encode(DID_API_KEY.encode()).decode()  # key is already "user:pass"-shaped
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}

    log("  Creating D-ID talk...")
    r = requests.post(
        "https://api.d-id.com/talks",
        headers=headers,
        json={
            "source_url": image_url,
            "script": {"type": "audio", "audio_url": audio_url},
        },
        timeout=30,
    )
    r.raise_for_status()
    talk_id = r.json()["id"]

    log(f"  Polling D-ID talk {talk_id}...")
    for attempt in range(60):  # up to ~5 min at 5s intervals
        time.sleep(5)
        pr = requests.get(f"https://api.d-id.com/talks/{talk_id}", headers=headers, timeout=30)
        pr.raise_for_status()
        status = pr.json().get("status")
        if status == "done":
            result_url = pr.json()["result_url"]
            break
        if status in ("error", "rejected"):
            raise RuntimeError(f"D-ID talk failed: {pr.json()}")
    else:
        raise RuntimeError("D-ID talk timed out after ~5 minutes")

    log("  Downloading D-ID result...")
    dl = requests.get(result_url, timeout=120)
    dl.raise_for_status()
    out_path.write_bytes(dl.content)
    return out_path


def _render_replicate(audio_path: Path, image_path: Path, out_path: Path) -> Path:
    """Replicate SadTalker — GATED behind REPLICATE_LICENSE_CONFIRMED.

    Upstream OpenTalker/SadTalker relicensed to Apache 2.0 and removed the
    non-commercial restriction per their README, but the cjwbw/sadtalker
    Replicate listing still explicitly states personal/research/non-commercial
    use only. That's a direct conflict on the exact platform this calls —
    confirm your own legal read before setting REPLICATE_LICENSE_CONFIRMED=true.
    """
    if not REPLICATE_LICENSE_CONFIRMED:
        raise RuntimeError(
            "Replicate/SadTalker commercial license is unverified (see comments in "
            "generate_presenter.py and docs/presenter.md) — set "
            "REPLICATE_LICENSE_CONFIRMED=true only after you've confirmed this yourself."
        )
    if not REPLICATE_API_TOKEN:
        raise RuntimeError("REPLICATE_API_TOKEN not set")

    headers = {"Authorization": f"Bearer {REPLICATE_API_TOKEN}", "Content-Type": "application/json"}

    def _data_uri(path: Path, mime: str) -> str:
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"

    log("  Creating Replicate prediction (SadTalker)...")
    r = requests.post(
        "https://api.replicate.com/v1/predictions",
        headers=headers,
        json={
            "version": "cjwbw/sadtalker",
            "input": {
                "driven_audio": _data_uri(audio_path, "audio/wav"),
                "source_image": _data_uri(image_path, "image/png"),
            },
        },
        timeout=30,
    )
    r.raise_for_status()
    prediction = r.json()
    get_url = prediction["urls"]["get"]

    log("  Polling Replicate prediction...")
    for attempt in range(60):
        time.sleep(5)
        pr = requests.get(get_url, headers=headers, timeout=30)
        pr.raise_for_status()
        data = pr.json()
        if data["status"] == "succeeded":
            result_url = data["output"]
            break
        if data["status"] in ("failed", "canceled"):
            raise RuntimeError(f"Replicate prediction failed: {data.get('error')}")
    else:
        raise RuntimeError("Replicate prediction timed out after ~5 minutes")

    log("  Downloading Replicate result...")
    dl = requests.get(result_url, timeout=120)
    dl.raise_for_status()
    out_path.write_bytes(dl.content)
    return out_path


_BACKENDS = {"did": _render_did, "replicate": _render_replicate}


def _check_config(meta=None):
    """Validate config/inputs without calling any API. Returns a list of
    problems (empty = ready to run). Used by both --dry-run and main()."""
    problems = []

    if PRESENTER_BACKEND == "none":
        return ["PRESENTER_BACKEND=none (this is fine — presenter is off)"]

    if PRESENTER_BACKEND not in _BACKENDS:
        problems.append(f"Unknown PRESENTER_BACKEND={PRESENTER_BACKEND!r}, "
                         f"valid values: none, {', '.join(_BACKENDS)}")
        return problems

    if shutil.which("ffmpeg") is None:
        problems.append("ffmpeg not found on PATH (needed to resample audio and composite overlay)")

    char_ref = Path(PRESENTER_CHAR_REF)
    if not char_ref.exists():
        problems.append(f"PRESENTER_CHAR_REF not found at {char_ref}")

    if PRESENTER_BACKEND == "did" and not DID_API_KEY:
        problems.append("PRESENTER_BACKEND=did but DID_API_KEY is not set")
    if PRESENTER_BACKEND == "replicate":
        if not REPLICATE_LICENSE_CONFIRMED:
            problems.append("PRESENTER_BACKEND=replicate but REPLICATE_LICENSE_CONFIRMED "
                             "is not 'true' (see license note in this file / docs/presenter.md)")
        if not REPLICATE_API_TOKEN:
            problems.append("PRESENTER_BACKEND=replicate but REPLICATE_API_TOKEN is not set")

    if PRESENTER_BACKEND == "did":
        try:
            sys.path.insert(0, str(BASE))
            from zernio_client import ZERNIO_KEY
            if not ZERNIO_KEY:
                problems.append("D-ID backend needs Zernio to host audio/image URLs, "
                                 "but ZERNIO_API_KEY is not set")
        except ImportError:
            problems.append("Could not import zernio_client.py")

    if meta is not None:
        voiceover_path = meta.get("voiceover_path")
        if not voiceover_path or not Path(voiceover_path).exists():
            problems.append("No voiceover_path in latest_reel_meta.json (or file missing)")
        video_path = meta.get("video_path")
        if not video_path or not Path(video_path).exists():
            problems.append("No video_path in latest_reel_meta.json (or file missing)")
    else:
        if not META_PATH.exists():
            problems.append(f"{META_PATH} does not exist yet — run generate_reel_v2.py first")

    return problems


def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        meta = None
        if META_PATH.exists():
            with open(META_PATH) as f:
                meta = json.load(f)
        problems = _check_config(meta)
        log(f"--dry-run: PRESENTER_BACKEND={PRESENTER_BACKEND!r}")
        if not problems:
            log("  Config OK — ready to render (no API call made in dry-run mode).")
        else:
            for p in problems:
                log(f"  - {p}")
        return

    if PRESENTER_BACKEND == "none":
        log("PRESENTER_BACKEND=none — skipping presenter, pipeline unchanged.")
        return

    if PRESENTER_BACKEND not in _BACKENDS:
        log(f"Unknown PRESENTER_BACKEND={PRESENTER_BACKEND!r} — skipping presenter. "
            f"Valid values: none, {', '.join(_BACKENDS)}")
        return

    if not META_PATH.exists():
        log("No latest_reel_meta.json found — skipping presenter.")
        return

    with open(META_PATH) as f:
        meta = json.load(f)

    voiceover_path = meta.get("voiceover_path")
    if not voiceover_path or not Path(voiceover_path).exists():
        log("No voiceover_path in meta (or file missing) — skipping presenter.")
        return

    char_ref = Path(PRESENTER_CHAR_REF)
    if not char_ref.exists():
        log(f"PRESENTER_CHAR_REF not found at {char_ref} — skipping presenter. "
            f"Add a static character PNG there, or point PRESENTER_CHAR_REF at one.")
        return

    # Render (or reuse cached) presenter clip. Any failure here leaves meta
    # completely untouched — reel ships exactly as generate_reel_v2.py made it.
    # NOTE: this is the pre-overlay version — presenter_clip is recorded but
    # nothing composites it onto the reel yet. That's the next commit.
    try:
        resampled = _resample_audio(Path(voiceover_path))
        key = _cache_key(resampled, char_ref, PRESENTER_BACKEND)

        cached = _cache_get(key)
        if cached:
            log(f"Cache hit — reusing {cached}, no API call made.")
            clip_path = cached
        else:
            log(f"Cache miss — rendering via {PRESENTER_BACKEND}...")
            raw_out = OUTDIR / f"presenter_{meta['topic_id']}.mp4"
            _BACKENDS[PRESENTER_BACKEND](resampled, char_ref, raw_out)
            clip_path = _cache_put(key, raw_out)
            log(f"Cached result at {clip_path}")

        meta["presenter_clip"] = str(clip_path)
        with open(META_PATH, "w") as f:
            json.dump(meta, f, indent=2)
        log(f"presenter_clip set: {clip_path}")
    except Exception as e:
        log(f"Presenter render failed, shipping reel without overlay: {e}")
        # presenter_clip stays None — do not modify meta, do not raise.


if __name__ == "__main__":
    main()
