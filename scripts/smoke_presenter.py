#!/usr/bin/env python3
"""
Standalone smoke test for the presenter backends — run locally against one
sample audio file + character image, no pipeline/meta.json involved. Makes
a real API call (this is NOT a --dry-run) and costs whatever that backend
bills for one render.

Usage:
    python3 scripts/smoke_presenter.py --audio path/to/audio.mp3 --image path/to/char.png [--backend did|replicate] [--out out.mp4]

Backend defaults to $PRESENTER_BACKEND if --backend isn't passed. Reads the
same env vars as generate_presenter.py (DID_API_KEY, REPLICATE_API_TOKEN,
REPLICATE_LICENSE_CONFIRMED). D-ID hosts its own inputs via its /images and
/audios upload endpoints — no third-party hosting dependency.
"""

import sys, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_presenter as gp


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audio", required=True, type=Path)
    ap.add_argument("--image", required=True, type=Path)
    ap.add_argument("--backend", choices=["did", "replicate"], default=gp.PRESENTER_BACKEND)
    ap.add_argument("--out", type=Path, default=Path("smoke_presenter_out.mp4"))
    ap.add_argument("--skip-overlay", action="store_true",
                     help="Only render the talking-head clip, don't composite it onto anything")
    ap.add_argument("--base-video", type=Path,
                     help="If compositing, the video to overlay onto (required unless --skip-overlay)")
    args = ap.parse_args()

    if args.backend not in gp._BACKENDS:
        sys.exit(f"Unknown backend {args.backend!r} — valid: {', '.join(gp._BACKENDS)}")
    if not args.audio.exists():
        sys.exit(f"Audio file not found: {args.audio}")
    if not args.image.exists():
        sys.exit(f"Image file not found: {args.image}")

    gp.log(f"Resampling audio...")
    resampled = gp._resample_audio(args.audio)

    gp.log(f"Rendering via {args.backend} (real API call, this will bill)...")
    clip_path = args.out if args.skip_overlay else args.out.with_suffix(".presenter_clip.mp4")
    gp._BACKENDS[args.backend](resampled, args.image, clip_path)
    gp.log(f"Presenter clip: {clip_path}")

    if args.skip_overlay:
        return

    if not args.base_video or not args.base_video.exists():
        sys.exit("--base-video is required (and must exist) unless --skip-overlay is passed")

    gp.log("Compositing overlay onto base video...")
    gp._apply_overlay(args.base_video, clip_path, args.out, overlay_scale=gp.PRESENTER_OVERLAY_SCALE)
    gp.log(f"Done: {args.out}")


if __name__ == "__main__":
    main()
