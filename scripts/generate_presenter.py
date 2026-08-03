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
from PIL import Image, ImageDraw, ImageFilter, ImageChops

BASE      = Path(__file__).resolve().parent
REPO_ROOT = BASE.parent
OUTDIR    = REPO_ROOT / "generated"
META_PATH = OUTDIR / "latest_reel_meta.json"

VIDEO_W, VIDEO_H = 1080, 1920  # must match generate_reel_v2.py's W, H

PRESENTER_BACKEND       = os.environ.get("PRESENTER_BACKEND", "none").lower()
PRESENTER_CHAR_REF      = os.environ.get("PRESENTER_CHAR_REF", "assets/character/presenter.png")
DID_API_KEY             = os.environ.get("DID_API_KEY", "")
REPLICATE_API_TOKEN     = os.environ.get("REPLICATE_API_TOKEN", "")
PRESENTER_CACHE_DIR     = Path(os.environ.get("PRESENTER_CACHE_DIR", ".cache/presenter"))
PRESENTER_OVERLAY_SCALE = float(os.environ.get("PRESENTER_OVERLAY_SCALE", "0.30"))

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


def _generate_overlay_assets(diameter: int, out_dir: Path, accent=(0, 200, 255)):
    """Circular alpha mask (for ffmpeg's alphamerge) + a decoration PNG with
    a soft drop-shadow glow and a crisp accent border ring, fully transparent
    inside the circle so the presenter video underneath shows through
    untouched once composited on top."""
    mask_path = out_dir / "presenter_mask.png"
    deco_path = out_dir / "presenter_deco.png"

    # Plain white-circle-on-black — alphamerge uses this as the alpha channel
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, diameter - 1, diameter - 1], fill=255)
    mask.convert("RGB").save(mask_path)

    pad = 20  # room for the shadow blur to extend beyond the circle
    canvas = diameter + pad * 2
    cx = cy = canvas // 2
    r = diameter // 2

    # Soft shadow, blurred, offset down slightly for depth
    shadow = Image.new("L", (canvas, canvas), 0)
    ImageDraw.Draw(shadow).ellipse(
        [cx - r - 6, cy - r - 6 + 4, cx + r + 6, cy + r + 6 + 4], fill=180)
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))

    # Zero out the shadow inside the circle radius so it only reads as a rim
    # glow outside the visible presenter footage, never over it
    hole = Image.new("L", (canvas, canvas), 255)
    ImageDraw.Draw(hole).ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
    shadow_alpha = ImageChops.multiply(shadow, hole)

    deco = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    deco.putalpha(shadow_alpha)
    ImageDraw.Draw(deco).ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*accent, 255), width=3)
    deco.save(deco_path)

    return mask_path, deco_path, pad


def _apply_overlay(base_video: Path, presenter_clip: Path, out_path: Path,
                    overlay_scale: float = 0.30) -> Path:
    """Composite the presenter clip as a circular picture-in-picture overlay
    onto the already-finished reel (Option A: one extra video re-encode,
    crf18/preset medium to keep it close to lossless — see docs/presenter.md
    for why this was chosen over re-encoding once from the PNG frames)."""
    diameter = int(VIDEO_W * overlay_scale)
    mask_path, deco_path, pad = _generate_overlay_assets(diameter, out_path.parent)

    # Bottom-right, clear of Instagram safe zones (bottom 20%, right 12%),
    # plus a small margin so it doesn't sit flush against the boundary
    margin = 24
    x = VIDEO_W - int(VIDEO_W * 0.12) - diameter - margin
    y = VIDEO_H - int(VIDEO_H * 0.20) - diameter - margin
    deco_x, deco_y = x - pad, y - pad

    filter_complex = (
        f"[1:v] scale={diameter}:{diameter}:force_original_aspect_ratio=increase,"
        f"crop={diameter}:{diameter},setsar=1 [pcrop];"
        f"[pcrop][2:v] alphamerge [pcircle];"
        f"[0:v][pcircle] overlay={x}:{y}:shortest=1 [with_video];"
        f"[with_video][3:v] overlay={deco_x}:{deco_y} [outv]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(base_video),
        "-stream_loop", "-1", "-i", str(presenter_clip),  # loop if shorter than the reel
        "-loop", "1", "-i", str(mask_path),
        "-loop", "1", "-i", str(deco_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg overlay failed: {r.stderr[-800:]}")
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

    # Stage 1: render (or reuse cached) presenter clip. Any failure here
    # leaves meta completely untouched — reel ships exactly as generate_reel_v2.py made it.
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
    except Exception as e:
        log(f"Presenter render failed, shipping reel without overlay: {e}")
        return  # meta untouched, presenter_clip stays None

    # Stage 2: composite onto the finished reel. Kept separate from stage 1 —
    # a rendered-but-uncompositable clip must still fall back to the plain
    # reel, not crash the run.
    try:
        composited_path = OUTDIR / f"reel_with_presenter_{meta['topic_id']}.mp4"
        _apply_overlay(Path(meta["video_path"]), clip_path, composited_path,
                        overlay_scale=PRESENTER_OVERLAY_SCALE)
        meta["video_path"]      = str(composited_path)
        meta["presenter_clip"]  = str(clip_path)
        with open(META_PATH, "w") as f:
            json.dump(meta, f, indent=2)
        log(f"Overlay composited: {composited_path}")
    except Exception as e:
        log(f"Overlay compositing failed, shipping reel without overlay: {e}")
        # meta["video_path"] stays the original finished reel; presenter_clip
        # stays None too — no overlay was actually baked into anything.


if __name__ == "__main__":
    main()
