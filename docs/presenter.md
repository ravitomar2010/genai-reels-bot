# Presenter overlay (optional)

An optional lip-synced cartoon character, composited as a circular picture-in-picture
overlay on top of the existing reel. **Off by default** — `PRESENTER_BACKEND=none`
makes `scripts/generate_presenter.py` a complete no-op; the pipeline behaves exactly
as it did before this feature existed.

## Why this exists / what it isn't

This pipeline runs on GitHub Actions' free `ubuntu-latest` runners — no GPU, ever.
Self-hosted talking-head models (SadTalker, Hallo3, etc.) need GPU for any practical
inference speed, so they aren't viable to run *in this job*. The only backends
implemented here are cloud HTTPS APIs that do the rendering remotely — this script
never runs a model locally.

## Setup

1. Add a static character image at `assets/character/presenter.png` (or point
   `PRESENTER_CHAR_REF` at wherever you put it). **Caveat:** D-ID's talking-photo
   feature is built and tuned for real photographic faces — its behavior on a
   stylized/illustrated cartoon character is not well documented and may be less
   reliable (mouth movement quality, face detection) than on a photo. Test with
   `scripts/smoke_presenter.py` before trusting it in production.
2. Get a D-ID API key (Studio account → API keys). It's a `username:password`-shaped
   string, used as-is for HTTP Basic auth — see `docs.d-id.com/reference/basic-authentication`.
3. Add `DID_API_KEY` / `SYNC_API_KEY` (and `REPLICATE_API_TOKEN` if you plan to use that
   backend) as GitHub repo secrets. The `sync` backend also needs `ZERNIO_API_KEY` —
   see the backend comparison below for why.
4. Flip `PRESENTER_BACKEND` from `none` to `did`/`sync`/`replicate` in
   `.github/workflows/daily_reel.yml` when you're ready to enable it. It's left as
   `none` in the workflow deliberately — flip it manually.

## Env vars

| Var | Default | Notes |
|---|---|---|
| `PRESENTER_BACKEND` | `none` | `none` \| `did` \| `sync` \| `replicate` |
| `PRESENTER_CHAR_REF` | `assets/character/presenter.png` | Static character image |
| `DID_API_KEY` | *(empty)* | `username:password` string from D-ID Studio |
| `SYNC_API_KEY` | *(empty)* | From sync.so account settings |
| `REPLICATE_API_TOKEN` | *(empty)* | Only needed for the gated Replicate backend |
| `REPLICATE_LICENSE_CONFIRMED` | *(empty)* | Must be exactly `true` to enable Replicate — see License below |
| `ZERNIO_API_KEY` | *(empty)* | Only used by the `sync` backend, to host audio/image at a public URL — see below |
| `PRESENTER_CACHE_DIR` | `.cache/presenter` | Rendered clips keyed on `sha256(audio + image + backend)` |
| `PRESENTER_OVERLAY_SCALE` | `0.30` | Overlay diameter as a fraction of the 1080px frame width |

## Backend comparison (from actual testing, not just docs)

| | D-ID | Sync (`sync-3`) | Hedra |
|---|---|---|---|
| Coded in | Yes | Yes | No — schema verified live, never implemented |
| Real render tested | Yes | Yes | No — blocked on a $0 API wallet balance, never got past submission |
| Aspect ratio | Forces a square crop (512×512 in testing) | **Preserves the source image's aspect ratio** (928×1152 in testing) | Unverified |
| Watermark | **Yes, on the free/trial tier** | Free tier output is watermarked too (1 `sync-3` gen/month, 15s cap) | Unverified |
| File hosting | Has its own upload endpoints (`/images`, `/audios`) — no third party needed | **No upload endpoint** — `/v2/assets` only accepts `{url, type}` JSON, so hosting via Zernio's presign flow is genuinely required, not optional | Has its own (`/files`) |
| Body movement | Face/head only | Face/head only | Full body, per their marketing (untested here) |

Neither is flipped on by default — this is a menu, not a ranking. D-ID was simply built
first, before Sync/Hedra were researched; it isn't "the" choice.

## Swapping backends

All backends implement the same contract: `(audio_path, image_path, out_path) -> Path`,
as plain functions in `scripts/generate_presenter.py` (`_render_did`, `_render_sync`,
`_render_replicate`) — no class hierarchy, matching this repo's flat style. Adding
another backend means writing one more function with that same signature and adding
it to the `_BACKENDS` dict.

## License finding — why Replicate/SadTalker is gated

Two directly conflicting sources:
- **Upstream OpenTalker/SadTalker README** (current): *"The license has been updated to
  Apache 2.0, and we've removed the non-commercial restriction."* Commercial use permitted.
- **Replicate's own listing** (`cjwbw/sadtalker`): still explicitly states *"This
  repository can only be used for personal/research/non-commercial purposes."*

That's a real conflict on the exact platform this would call through — upstream
relicensing doesn't automatically override whatever terms govern that specific hosted
listing, and this pipeline is monetized. Rather than resolve that with more research,
the Replicate backend is **hard-gated** behind `REPLICATE_LICENSE_CONFIRMED=true` — a
separate opt-in from just picking `PRESENTER_BACKEND=replicate` — so it can never be
accidentally enabled. Confirm your own legal read before setting that flag, ideally
against a specific, currently-maintained Replicate SadTalker listing rather than the
one referenced here, which may have changed.

## Design decisions

**Loop, not freeze-frame, when the presenter clip is shorter than the reel.** The
overlay ffmpeg pass uses `-stream_loop -1` on the presenter clip input combined with
`overlay=...:shortest=1`, so it loops seamlessly from the start until the main video
ends. A frozen last frame (often mid-expression) reads as more obviously broken than
a loop seam.

**One extra re-encode, not zero.** `build_video()` in `generate_reel_v2.py` finishes
the reel completely (frames → silent MP4 → mux voice/music, `-c:v copy`) before
`generate_presenter.py` even starts — it's a separate, later workflow step, so it
can't hold both the finished video and a presenter clip that doesn't exist yet at
that point. Two options were considered:

- **(A, chosen)** Overlay onto the *finished* MP4 in `generate_presenter.py`, forcing
  one additional video re-encode (audio stays `-c:a copy`, no audio loss). Mitigated
  with `-crf 18 -preset medium` — appreciably higher quality than pass 1's `-crf 22`,
  since this is a second generation on top of an already-compressed source.
- **(B, rejected)** Keep the PNG frame directory + silent MP4 around, encode video
  *once* from frames + overlay in `generate_presenter.py` instead. Better quality, but
  couples the two scripts through on-disk frame state and means the reel isn't
  "finished" until the presenter step runs — which breaks the graceful-failure
  guarantee unless pass 1's output is separately preserved as a fallback anyway,
  undermining the reason to do it.

Instagram/YouTube re-encode on upload regardless, so the marginal quality loss from
one extra local generation is not the dominant factor either way.

**No third-party file hosting — D-ID hosts its own inputs.** D-ID's `/talks` endpoint
needs `source_url`/`audio_url` as fetchable URLs, not direct uploads, which raised a
real question: host them where? An earlier version of this reused Zernio's (already a
dependency in this pipeline, for posting) `/media/presign` flow to stage the character
image and voiceover audio at a public URL for D-ID to fetch. That worked, but it was
wrong: Zernio's own docs describe that flow as "temporary storage for 7 days until a
post using them publishes" — a mechanism for staging content Zernio itself is about to
post, not a general-purpose file host, and reusing it for an unrelated third party's
fetch is exactly the kind of dependency that quietly breaks if that endpoint's terms
tighten later. It also meant an unannounced external service holding the daily
voiceover and character asset, which should be a deliberate choice, not an
implementation detail.

D-ID has its own upload endpoints — `POST /images` and `POST /audios`, both
multipart/form-data, both returning a D-ID-hosted `url` (images: 24-48h retention;
audio: D-ID transcodes to 16kHz WAV itself, 6MB max — our ~35-40s clips run
~1.2-1.4MB, comfortably under that). Using these instead removes Zernio from the
presenter path entirely: one less moving part, and nothing of yours sits on a
third-party server for this feature to work.

## Failure handling

Every failure mode (missing config, API error, timeout, overlay compositing failure)
is caught, logged, and swallowed — the script always exits 0 and the reel ships
without an overlay. The workflow step also runs with `continue-on-error: true` as a
second layer of the same guarantee. There are two independent failure boundaries:
rendering the presenter clip, and compositing it onto the reel — a clip that renders
successfully but fails to composite still ships the plain reel, not a broken video.

## Verifying without spending anything

`python3 scripts/generate_presenter.py --dry-run` validates all config (backend
choice, required env vars, character file exists, ffmpeg on PATH, meta.json/voiceover
present) **without calling any API**. Run this after any config change before letting
the real workflow hit it.

`python3 scripts/smoke_presenter.py --audio <sample.mp3> --image <char.png> --backend did`
makes one real API call against a sample file, outside the daily pipeline — useful for
checking a new character image or backend before trusting it in production. This does
bill whatever that backend charges for one render.

## Cost / latency per reel

**D-ID:**
- Latency: their own docs describe short talking-photo renders as typically
  10-30 seconds; `generate_presenter.py` polls for up to ~5 minutes before giving up
  and falling back to no overlay.
- Cost: Lite tier is roughly $4.70-5.90/month for 10 minutes of generated video
  included. At ~30-40s of narration/day × 30 days ≈ 15-20 minutes/month, daily use
  would exceed the Lite tier's included minutes — check current tier limits and
  overage pricing before enabling this daily.

**Sync (`sync-3`):**
- Latency: took several minutes in live testing (not the 10-30s D-ID claims) —
  `generate_presenter.py` polls for up to ~15 minutes before giving up.
- Cost: usage-based, not credits — Hobbyist $5/mo + ~$0.107-0.133/sec for `sync-3`
  specifically (cheaper models exist but need an existing video, ruled out for this
  pipeline). A 30s reel ≈ $3.20-4/render; daily for a month ≈ $96-120 + the $5 fee —
  meaningfully pricier than D-ID at daily volume. Free tier: 1 `sync-3` generation/month,
  15s cap, watermarked — enough for one sanity check, not for evaluating daily use.

Every unchanged re-run costs nothing extra on either backend — the sha256 cache means
the same audio+image+backend combination is never re-rendered or re-billed.
